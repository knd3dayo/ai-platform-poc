import os
import asyncio
import time
import io
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv
from pydantic import SecretStr

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.runnables import Runnable
from langchain_core.messages import AIMessage, SystemMessage

from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode

def _get_executor_base_url() -> str:
    """Cline Executor Service のベースURLを取得する。

    - コンテナ内では docker-compose の extra_hosts により host.docker.internal が使える
    - ホスト実行なら localhost を使う
    """
    return os.getenv("CLINE_EXECUTOR_BASE_URL", "http://host.docker.internal:8000")


def _poll_status(task_id: str, timeout_sec: int) -> Dict[str, Any]:
    """Cline Executor Service の /status をポーリングして完了を待つ（同期関数）"""
    base_url = _get_executor_base_url().rstrip("/")
    deadline = time.time() + timeout_sec

    while True:
        res = requests.get(f"{base_url}/status/{task_id}", timeout=10)
        res.raise_for_status()
        status_data = res.json()
        status = status_data.get("status")

        if status in ["completed", "failed", "timeout", "cancelled"]:
            return status_data

        if time.time() > deadline:
            # Executor側のtimeoutとは別に、Supervisor側の待機も打ち切れるようにしておく
            raise TimeoutError(f"Timed out while waiting executor task completion: task_id={task_id}")

        time.sleep(1.0)


def _should_exclude_path(rel_posix: str) -> bool:
    """ZIP化対象から除外するパスかどうかを判定する（ディレクトリ相対のPOSIXパス）"""
    # 先頭セグメントで除外（プロジェクト直下の .git や node_modules 等を想定）
    first = rel_posix.split("/", 1)[0]
    if first in {".git", ".venv", "venv", "node_modules", ".mypy_cache", ".pytest_cache"}:
        return True

    # どこに居ても除外したいディレクトリ名
    if "/__pycache__/" in f"/{rel_posix}/":
        return True

    # よくある大容量/不要ファイル
    if rel_posix.endswith(".pyc"):
        return True

    return False


def _zip_dir_to_bytes(dir_path: str) -> bytes:
    """ディレクトリをZIP化してbytesで返す（同期関数）

    - .git/.venv/node_modules/__pycache__ などはデフォルトで除外
    """
    base = Path(dir_path)
    if not base.exists() or not base.is_dir():
        raise ValueError(f"dir_path must be an existing directory: {dir_path}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in base.rglob("*"):
            if p.is_file():
                # ZIP内のパスはディレクトリ相対
                arcname = p.relative_to(base).as_posix()
                if _should_exclude_path(arcname):
                    continue
                zf.write(p, arcname=arcname)
    return buf.getvalue()


@tool
async def run_cline_executor(
    prompt: str,
    initial_files: Optional[Dict[str, str]] = None,
    timeout: int = 300,
) -> Dict[str, Any]:
    """Executor Service(コーディングエージェント実行API) を呼び出して結果を返す。

    呼び出し:
    1) POST /execute で task_id を取得
    2) GET /status/{task_id} を完了までポーリング
    3) completed/failed/timeout 等の最終結果を返す

    並列実行に耐えるよう、HTTP呼び出しは asyncio.to_thread() でスレッド実行する。
    """

    def _run() -> Dict[str, Any]:
        base_url = _get_executor_base_url().rstrip("/")
        payload: Dict[str, Any] = {"prompt": prompt, "timeout": timeout}
        if initial_files:
            payload["initial_files"] = initial_files

        res = requests.post(f"{base_url}/execute", json=payload, timeout=30)
        res.raise_for_status()
        task_id = res.json()["task_id"]
        final_status = _poll_status(task_id, timeout_sec=timeout + 30)
        return {"task_id": task_id, **final_status}

    return await asyncio.to_thread(_run)


@tool
async def run_cline_executor_zip(
    prompt: str,
    dir_path: Optional[str] = None,
    zip_path: Optional[str] = None,
    timeout: int = 600,
) -> Dict[str, Any]:
    """Executor Service の /execute/zip を使い、関連ファイル一式をアップロードして実行する。

    `dir_path` または `zip_path` のどちらか一方を指定する。

    処理の流れ:
    1) dir_path の場合はディレクトリをZIP化（zip_path の場合はそのまま読む）
    2) multipart/form-data で POST /execute/zip
    3) GET /status/{task_id} を完了までポーリング
    """

    if (dir_path is None and zip_path is None) or (dir_path is not None and zip_path is not None):
        raise ValueError("Specify exactly one of dir_path or zip_path")

    def _run() -> Dict[str, Any]:
        base_url = _get_executor_base_url().rstrip("/")

        if dir_path is not None:
            zip_bytes = _zip_dir_to_bytes(dir_path)
            file_tuple = ("project.zip", io.BytesIO(zip_bytes), "application/zip")
        else:
            p = Path(zip_path)  # type: ignore[arg-type]
            if not p.exists() or not p.is_file():
                raise ValueError(f"zip_path must be an existing zip file: {zip_path}")
            file_tuple = (p.name, p.open("rb"), "application/zip")

        data = {"prompt": prompt, "timeout": str(timeout)}
        files = {"file": file_tuple}
        try:
            res = requests.post(f"{base_url}/execute/zip", data=data, files=files, timeout=60)
            res.raise_for_status()
            task_id = res.json()["task_id"]
            final_status = _poll_status(task_id, timeout_sec=timeout + 30)
            return {"task_id": task_id, **final_status}
        finally:
            # zip_path の場合だけファイルハンドルを閉じる
            if zip_path is not None:
                try:
                    file_tuple[1].close()  # type: ignore[union-attr]
                except Exception:
                    pass

    return await asyncio.to_thread(_run)


tools = [run_cline_executor, run_cline_executor_zip]
tool_node = ToolNode(tools)

# ==========================================
# 2. Supervisor（LLM）の設定
# ==========================================

class LLMUtils:
    @staticmethod
    def create_llm() -> Runnable:
        """LLMのインスタンスを生成する関数（必要に応じてカスタマイズ）"""
        # .envファイルから環境変数を読み込む
        load_dotenv()
        params = {
            "model": os.getenv("MODEL", "gpt-4o"),
            "api_key": SecretStr(os.getenv("LITELLM_MASTER_KEY", "")),
        }   
        base_url = os.getenv("BASE_URL")
        if base_url:
            params["base_url"] = base_url
        llm = ChatOpenAI(
            **params
            )
        llm_with_tools = llm.bind_tools(tools)
        return llm_with_tools

class ParallelAgentWorkflow:
    """
    LLMが複数のタスクを並行して処理するワークフローの例
    ツールでExecuter Service(コーディングエージェントを実行するAPI)を呼び出す.
    SuperVisor Agentは、ユーザーの指示を受け取り、実行計画を立て、必要に応じてツールを呼び出す役割を担います。
    ツールは並列で呼び出し、実行結果をSupervisorに返します。
    Supervisorは全てのタスクが完了するまで待機し、最終的な応答を生成します。
    各タスクの結果を確認して、ユーザーが求める最終回答が得られるように、必要に応じて追加のツール呼び出しやLLMへの問い合わせを行います。
    """

    @staticmethod
    def supervisor_agent(state: MessagesState):
        """Supervisor Agent: 計画を立て、必要ならツール呼び出しを生成する。

        - ユーザー指示をタスク分解し、複数の tool call を *同一のAIメッセージ内* に生成させる
        - ToolNode はそれらの tool call を（可能な範囲で）並列実行し、結果をメッセージとして state に追加する
        - Supervisor はツール結果を見て最終回答を生成。必要なら追加の tool call を生成してループする
        """

        llm = LLMUtils.create_llm()

        sys_prompt = SystemMessage(
            content=(
                "あなたはSupervisor Agentです。ユーザーの指示を達成するために実行計画を立て、"
                "必要に応じて `run_cline_executor` / `run_cline_executor_zip` ツールを呼び出してください。\n"
                "- 指示が複数の独立タスクに分解できる場合は、可能な限り *複数のツール呼び出しを同時に* 生成してください。\n"
                "- `run_cline_executor` は時間のかかる処理です。並列実行して構いません。\n"
                "- 次のような場合は `run_cline_executor_zip` を優先してください: \n"
                "  - 『プロジェクト全体』『リポジトリ全体』『複数ファイル』『依存関係を見て』など、広いコンテキストが必要な依頼\n"
                "  - バグ調査で原因箇所が不明、ログ/設定/複数モジュールの確認が必要\n"
                "  - リファクタ、横断的な修正（型修正、import整理、設定変更など）\n"
                "- `run_cline_executor` は少数ファイルへのピンポイント指示向きです（initial_files で必要最小限の入力を渡す）。\n"
                "- ツール結果（stdout/stderr/artifacts）を確認し、ユーザーが求める最終回答を日本語でまとめてください。\n"
                "- 不足があれば追加でツールを呼び出し、完了するまで繰り返してください。"
            )
        )

        messages_with_sys = [sys_prompt] + state["messages"]
        response = llm.invoke(messages_with_sys)
        return {"messages": [response]}

    @staticmethod
    def should_continue(state: MessagesState):
        """次の遷移先を決定するルーティング関数"""
        last_message = state["messages"][-1]
        if isinstance(last_message, AIMessage) and last_message.tool_calls:        
            return "tools" # ツール呼び出しがあればtoolsノードへ
        return END         # なければ会話終了

    def create_graph(self):
        # ==========================================
        # 3. グラフの構築
        # ==========================================
        workflow = StateGraph(MessagesState)

        workflow.add_node("agent", self.supervisor_agent)
        workflow.add_node("tools", tool_node)

        workflow.add_edge(START, "agent")
        workflow.add_conditional_edges("agent", self.should_continue)
        workflow.add_edge("tools", "agent")

        return workflow

