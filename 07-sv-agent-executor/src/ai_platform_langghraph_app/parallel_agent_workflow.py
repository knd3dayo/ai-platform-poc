import os
import asyncio
import time
import io
import zipfile
import base64
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple

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
    # NOTE:
    # - 環境変数が指定されていれば最優先
    # - 未指定の場合は、実行環境がコンテナ内かどうかでデフォルトを分岐する
    #   - コンテナ内: host.docker.internal
    #   - ホスト: localhost
    env = os.getenv("CLINE_EXECUTOR_BASE_URL")
    if env:
        return env

    # ざっくりコンテナ判定
    in_container = os.path.exists("/.dockerenv")
    return "http://host.docker.internal:8000" if in_container else "http://localhost:8000"


def _poll_status(task_id: str, timeout_sec: int) -> Dict[str, Any]:
    """Cline Executor Service の /status をポーリングして完了を待つ（同期関数）"""
    base_url = _get_executor_base_url().rstrip("/")
    deadline = time.time() + timeout_sec

    while True:
        # NOTE: executor 側が running 中でも stdout/stderr を返せるようになったため tail を付与
        #       （executor 側デフォルトも 200 だが明示しておく）
        res = requests.get(f"{base_url}/status/{task_id}", params={"tail": 200}, timeout=10)
        res.raise_for_status()
        status_data = res.json()
        status = status_data.get("status")

        if status in ["completed", "failed", "timeout", "cancelled"]:
            return status_data

        if time.time() > deadline:
            # Executor側のtimeoutとは別に、Supervisor側の待機も打ち切れるようにしておく
            raise TimeoutError(f"Timed out while waiting executor task completion: task_id={task_id}")

        time.sleep(1.0)


def _download_artifacts_zip_bytes(task_id: str) -> bytes:
    """Cline Executor Service の成果物ZIPをダウンロードして bytes で返す（同期関数）"""
    base_url = _get_executor_base_url().rstrip("/")
    res = requests.get(f"{base_url}/artifacts/{task_id}/zip", timeout=60)
    res.raise_for_status()
    return res.content


def _is_probably_text_file(path: str) -> bool:
    ext = Path(path).suffix.lower()
    return ext in {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".log"}


def _inspect_zip_bytes(
    zip_bytes: bytes,
    *,
    max_preview_files: int = 50,
    max_preview_chars_per_file: int = 2000,
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """ZIP(bytes)の内容を簡易的に検査して返す。

    Returns:
        (file_list, text_previews)

    - file_list: [{"path": str, "size": int}, ...]
    - text_previews: {"path": "先頭N文字...", ...}

    NOTE:
        Supervisor が成果物の中身を確認して次の実行計画を立て直せるよう、
        LLMに渡しやすい形（一覧＋テキストプレビュー）に整形する。
    """
    file_list: List[Dict[str, Any]] = []
    text_previews: Dict[str, str] = {}

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        infos = zf.infolist()
        for info in infos:
            if info.is_dir():
                continue
            file_list.append({"path": info.filename, "size": info.file_size})

        # テキストっぽいファイルだけ、先頭をプレビューする
        preview_count = 0
        for info in infos:
            if preview_count >= max_preview_files:
                break
            if info.is_dir():
                continue
            if not _is_probably_text_file(info.filename):
                continue

            try:
                raw = zf.read(info.filename)
                txt = raw.decode("utf-8", errors="replace")
                text_previews[info.filename] = txt[:max_preview_chars_per_file]
                preview_count += 1
            except Exception:
                # プレビュー不能（バイナリ/壊れ等）はスキップ
                continue

    return file_list, text_previews


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

        # 完了後に成果物ZIPを取得して返す。
        # NOTE: base64 でクライアントへ返すのは PoC 用の便法。
        #       ファイルサイズが大きいとレスポンス肥大・メモリ圧迫・転送コスト増となり不向き。
        #       将来的にはシステム全体で成果物置き場（S3/Box等）を構築し、URL参照（署名付きURL等）で
        #       受け渡す方式を検討する。
        zip_bytes = _download_artifacts_zip_bytes(task_id)
        zip_b64 = base64.b64encode(zip_bytes).decode("ascii")
        file_list, text_previews = _inspect_zip_bytes(zip_bytes)

        return {
            "task_id": task_id,
            **final_status,
            "artifacts_zip_bytes": len(zip_bytes),
            "artifacts_zip_base64": zip_b64,
            "artifacts_zip_file_list": file_list,
            "artifacts_zip_text_previews": text_previews,
        }

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

            zip_bytes = _download_artifacts_zip_bytes(task_id)
            zip_b64 = base64.b64encode(zip_bytes).decode("ascii")
            file_list, text_previews = _inspect_zip_bytes(zip_bytes)

            return {
                "task_id": task_id,
                **final_status,
                "artifacts_zip_bytes": len(zip_bytes),
                "artifacts_zip_base64": zip_b64,
                "artifacts_zip_file_list": file_list,
                "artifacts_zip_text_previews": text_previews,
            }
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

        # NOTE: PoC では「コンテナ内実行」と「ホスト実行」が混在する。
        #       - docker-compose 内: http://litellm:4000/v1
        #       - ホスト実行:       http://localhost:4000/v1
        #       環境変数 BASE_URL があれば最優先する。
        base_url = os.getenv("BASE_URL")
        in_container = os.path.exists("/.dockerenv")
        if not base_url:
            base_url = "http://litellm:4000/v1" if in_container else "http://localhost:4000/v1"
        else:
            # ホスト実行なのに docker-compose のサービス名 (litellm) を向いている場合は localhost に補正
            if (not in_container) and ("//litellm:" in base_url):
                base_url = base_url.replace("//litellm:", "//localhost:")
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
                "- ツール結果の stdout/stderr を必ず確認し、失敗時は原因を踏まえて実行計画を立て直してください。\n"
                "- ツール結果に成果物ZIPが含まれる場合（artifacts_zip_file_list / artifacts_zip_text_previews / artifacts_zip_base64）、\n"
                "  まず中身を確認し、それに応じて必要なら追加のツール呼び出しで実行計画を立て直してください。\n"
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

