import os
import time
import io
import zipfile
import base64
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple, Deque
import json
import base64
import os
import threading
import traceback
from collections import deque

import requests


from langchain_core.tools import tool
from langchain_core.messages import AIMessage, SystemMessage

from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage
from langgraph.graph import MessagesState

from ..model.models import ServerConfig, Job, jobs_lock, jobs
from ..core.utils import JobUtils, LLMUtils

def _extract_tool_payloads_from_messages(messages: List[Any]) -> List[Dict[str, Any]]:
    """LangGraph の state.messages から tool 実行結果っぽいものを抽出する（PoC）。

    ToolNode の結果は ToolMessage として入ることが多い。
    - msg.type == "tool" かつ msg.content が JSON 文字列の場合は dict にデコードする。
    """
    payloads: List[Dict[str, Any]] = []
    for msg in messages:
        msg_type = getattr(msg, "type", None)
        if msg_type != "tool":
            continue
        content = getattr(msg, "content", None)
        if not isinstance(content, str):
            continue
        try:
            val = json.loads(content)
            if isinstance(val, dict):
                payloads.append(val)
        except Exception:
            continue
    return payloads


def _run_workflow_in_background(thread_id: str, message: str, input_zip_path: Optional[str]) -> None:
    """parallel_agent_workflow をバックグラウンドで実行し、jobs に途中経過/結果を格納する。"""

    with jobs_lock:
        jobs[thread_id] = Job(
            thread_id=thread_id,
            status="running",
            progress={
                "started_at": time.time(),
                "latest_message": None,
                "last_tool": None,
                "stdout": None,
                "stderr": None,
                "server_logs": deque(maxlen=200),
            },
        )

    try:

        wf = ParallelAgentWorkflow()
        graph = wf.create_graph().compile()
        server_config = ServerConfig.load_from_env()

        # parallel_agent_workflow 側のデフォルト分岐と合わせる
        llm_base_url = server_config.llm_base_url 
        executor_base_url = server_config.executor_base_url

        # ユーザーがZIPを渡してきた場合は、Supervisor がツール呼び出しで使えるようパスを明示する。
        # run_cline_executor_zip は zip_path を受け取れるので、実ファイルパスを案内すれば良い。
        user_message = message
        if input_zip_path:
            user_message += (
                "\n\n[入力ZIP]\n"
                "ユーザーがZIPファイルをアップロードしました。必要なら `run_cline_executor_zip` を使い、"
                "次の zip_path を指定して処理してください。\n"
                f"zip_path: {input_zip_path}\n"
            )

        state: MessagesState = {"messages": [HumanMessage(content=user_message)]}

        with jobs_lock:
            job = jobs.get(thread_id)
            if job:
                JobUtils.append_server_log(job, "LangGraph stream started")
                JobUtils.append_server_log(job, f"llm_base_url={llm_base_url}")
                JobUtils.append_server_log(job, f"executor_base_url={executor_base_url}")
                job.progress["llm_base_url"] = llm_base_url
                job.progress["executor_base_url"] = executor_base_url

        for event in graph.stream(state, stream_mode="values"):
            # event は state(values) の dict を想定
            messages = event.get("messages") if isinstance(event, dict) else None
            if not isinstance(messages, list) or not messages:
                continue

            latest = messages[-1]
            latest_content = getattr(latest, "content", None)

            # 進捗更新
            with jobs_lock:
                job = jobs.get(thread_id)
                if job:
                    if JobUtils.get_cancel_flag(job):
                        JobUtils.append_server_log(job, "Cancel requested. Stopping stream loop.")
                        job.status = "cancelled"
                        break
                    job.progress["latest_message"] = latest_content

                    tool_payloads = _extract_tool_payloads_from_messages(messages)
                    if tool_payloads:
                        last_tool = tool_payloads[-1]
                        job.progress["last_tool"] = last_tool
                        JobUtils.append_server_log(job, f"tool_result received keys={list(last_tool.keys())}")
                        # stdout/stderr があれば status ポーリングで返せるようにコピー
                        if "stdout" in last_tool:
                            job.progress["stdout"] = last_tool.get("stdout")
                        if "stderr" in last_tool:
                            job.progress["stderr"] = last_tool.get("stderr")

                        # cancel が要求されていたら executor 側にも kill を試みる
                        if JobUtils.get_cancel_flag(job):
                            JobUtils.try_cancel_executor_task(job)

        # 最終 state を取得（stream で最後に来た event を使っても良いが、ここでは progress を採用）
        with jobs_lock:
            job = jobs.get(thread_id)
            if job:
                if JobUtils.get_cancel_flag(job):
                    JobUtils.append_server_log(job, "LangGraph stream finished (cancelled)")
                else:
                    JobUtils.append_server_log(job, "LangGraph stream finished")
            jobs[thread_id] = Job(
                thread_id=thread_id,
                status="cancelled" if (job and JobUtils.get_cancel_flag(job)) else "completed",
                progress=job.progress if job else {"latest_message": None},
                result={
                    "thread_id": thread_id,
                    "latest_message": job.progress.get("latest_message") if job else None,
                    "last_tool": job.progress.get("last_tool") if job else None,
                },
            )

    except Exception as e:
        with jobs_lock:
            job = jobs.get(thread_id)
            if job:
                JobUtils.append_server_log(job, f"ERROR: {repr(e)}")
                JobUtils.append_server_log(job, traceback.format_exc())
            jobs[thread_id] = Job(
                thread_id=thread_id,
                status="failed",
                progress=job.progress if job else {},
                error=repr(e),
            )
    finally:
        # 入力ZIPはPoCのため、そのまま残す（必要なら削除に変更可能）
        pass


def start_background_thread(thread_id: str, message: str, input_zip_path: Optional[str]) -> None:
    t = threading.Thread(target=_run_workflow_in_background, args=(thread_id, message, input_zip_path), daemon=True)
    t.start()

def poll_status(task_id: str, timeout_sec: int) -> Dict[str, Any]:
    """Cline Executor Service の /status をポーリングして完了を待つ（同期関数）"""
    base_url = ServerConfig.load_from_env().executor_base_url
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


def download_artifacts_zip_bytes(task_id: str) -> bytes:
    """Cline Executor Service の成果物ZIPをダウンロードして bytes で返す（同期関数）"""
    server_config = ServerConfig.load_from_env()
    base_url = server_config.executor_base_url
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


def _error_result(message: str, *, task_id: Optional[str] = None) -> Dict[str, Any]:
    res: Dict[str, Any] = {
        "status": "failed",
        "stdout": "",
        "stderr": message,
        "artifacts": [],
    }
    if task_id is not None:
        res["task_id"] = task_id
    return res


@tool
def run_cline_executor(
    prompt: str,
    initial_files: Optional[Dict[str, str]] = None,
    timeout: int = 300,
) -> Dict[str, Any]:
    """Executor Service(コーディングエージェント実行API) を呼び出して結果を返す（同期ツール）。

    呼び出し:
    1) POST /execute で task_id を取得
    2) GET /status/{task_id} を完了までポーリング
    3) completed/failed/timeout 等の最終結果を返す

    NOTE:
        LangGraph の ToolNode は同期実行パスを通ることがあるため、このツールは同期関数にしている。
    """

    server_config = ServerConfig.load_from_env()
    try:
        base_url = server_config.executor_base_url
        payload: Dict[str, Any] = {"prompt": prompt, "timeout": timeout}
        if initial_files:
            payload["initial_files"] = initial_files

        res = requests.post(f"{base_url}/execute", json=payload, timeout=30)
        res.raise_for_status()
        task_id = res.json()["task_id"]

        try:
            final_status = poll_status(task_id, timeout_sec=timeout + 30)
        except Exception as e:
            return _error_result(f"Failed to poll status: {e}", task_id=task_id)

        # 完了後に成果物ZIPを取得して返す。
        # NOTE: base64 でクライアントへ返すのは PoC 用の便法。
        #       ファイルサイズが大きいとレスポンス肥大・メモリ圧迫・転送コスト増となり不向き。
        #       将来的にはシステム全体で成果物置き場（S3/Box等）を構築し、URL参照（署名付きURL等）で
        #       受け渡す方式を検討する。
        try:
            zip_bytes = download_artifacts_zip_bytes(task_id)
            zip_b64 = base64.b64encode(zip_bytes).decode("ascii")
            file_list, text_previews = _inspect_zip_bytes(zip_bytes)
        except Exception as e:
            # 成果物取得に失敗しても、実行結果自体は返す
            return {
                "task_id": task_id,
                **final_status,
                "artifacts_zip_error": str(e),
            }

        return {
            "task_id": task_id,
            **final_status,
            "artifacts_zip_bytes": len(zip_bytes),
            "artifacts_zip_base64": zip_b64,
            "artifacts_zip_file_list": file_list,
            "artifacts_zip_text_previews": text_previews,
        }
    except Exception as e:
        return _error_result(f"run_cline_executor failed: {e}")


@tool
def run_cline_executor_zip(
    prompt: str,
    dir_path: Optional[str] = None,
    zip_path: Optional[str] = None,
    timeout: int = 600,
) -> Dict[str, Any]:
    """Executor Service の /execute/zip を使い、関連ファイル一式をアップロードして実行する（同期ツール）。

    `dir_path` または `zip_path` のどちらか一方を指定する。

    処理の流れ:
    1) dir_path の場合はディレクトリをZIP化（zip_path の場合はそのまま読む）
    2) multipart/form-data で POST /execute/zip
    3) GET /status/{task_id} を完了までポーリング
    """
    server_config = ServerConfig.load_from_env()  # 先にロードしておいて、エラーがあれば早めに返す  

    if (dir_path is None and zip_path is None) or (dir_path is not None and zip_path is not None):
        raise ValueError("Specify exactly one of dir_path or zip_path")

    try:
        base_url = server_config.executor_base_url

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

            try:
                final_status = poll_status(task_id, timeout_sec=timeout + 30)
            except Exception as e:
                return _error_result(f"Failed to poll status: {e}", task_id=task_id)

            try:
                zip_bytes = download_artifacts_zip_bytes(task_id)
                zip_b64 = base64.b64encode(zip_bytes).decode("ascii")
                file_list, text_previews = _inspect_zip_bytes(zip_bytes)
            except Exception as e:
                return {
                    "task_id": task_id,
                    **final_status,
                    "artifacts_zip_error": str(e),
                }

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
    except Exception as e:
        return _error_result(f"run_cline_executor_zip failed: {e}")


tools = [run_cline_executor, run_cline_executor_zip]
tool_node = ToolNode(tools)

# ==========================================
# 2. Supervisor（LLM）の設定
# ==========================================

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

