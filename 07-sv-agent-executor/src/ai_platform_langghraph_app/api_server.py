import json
import base64
import os
import threading
import time
import traceback
from pathlib import Path
from collections import deque
import tempfile
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional, List, Deque

from fastapi import FastAPI, BackgroundTasks, HTTPException, UploadFile, File, Form

from langchain_core.messages import HumanMessage

from ai_platform_langghraph_app.parallel_agent_workflow import ParallelAgentWorkflow


app = FastAPI(title="SV Agent Executor API")


# =====================================================
# In-memory job store (PoC)
# =====================================================
# NOTE:
#   本番用途では Redis / DB など永続ストアに移すこと。


@dataclass
class Job:
    thread_id: str
    status: str  # queued, running, completed, failed
    # status polling で返すための進捗情報（PoC）
    progress: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


jobs_lock = threading.Lock()


def _append_server_log(job: Job, line: str, max_lines: int = 200) -> None:
    """サーバ側の進捗ログをリングバッファで保持する（/api/status で返す用）。"""
    logs: Deque[str] = job.progress.setdefault("server_logs", deque(maxlen=max_lines))  # type: ignore[assignment]
    # deque は json 化できないので、返却時に list 化する
    if isinstance(logs, deque):
        logs.append(line)


jobs: Dict[str, Job] = {}


# =====================================================
# Background worker
# =====================================================


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
        # 接続先が分かるよう、最初にログしておく
        from ai_platform_langghraph_app.parallel_agent_workflow import _get_executor_base_url

        wf = ParallelAgentWorkflow()
        graph = wf.create_graph().compile()

        # parallel_agent_workflow 側のデフォルト分岐と合わせる
        in_container = os.path.exists("/.dockerenv")
        llm_base_url = os.getenv("BASE_URL") or ("http://litellm:4000/v1" if in_container else "http://localhost:4000/v1")
        executor_base_url = _get_executor_base_url()

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

        state = {"messages": [HumanMessage(content=user_message)]}

        with jobs_lock:
            job = jobs.get(thread_id)
            if job:
                _append_server_log(job, "LangGraph stream started")
                _append_server_log(job, f"llm_base_url={llm_base_url}")
                _append_server_log(job, f"executor_base_url={executor_base_url}")

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
                    job.progress["latest_message"] = latest_content

                    tool_payloads = _extract_tool_payloads_from_messages(messages)
                    if tool_payloads:
                        last_tool = tool_payloads[-1]
                        job.progress["last_tool"] = last_tool
                        _append_server_log(job, f"tool_result received keys={list(last_tool.keys())}")
                        # stdout/stderr があれば status ポーリングで返せるようにコピー
                        if "stdout" in last_tool:
                            job.progress["stdout"] = last_tool.get("stdout")
                        if "stderr" in last_tool:
                            job.progress["stderr"] = last_tool.get("stderr")

        # 最終 state を取得（stream で最後に来た event を使っても良いが、ここでは progress を採用）
        with jobs_lock:
            job = jobs.get(thread_id)
            if job:
                _append_server_log(job, "LangGraph stream finished")
            jobs[thread_id] = Job(
                thread_id=thread_id,
                status="completed",
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
                _append_server_log(job, f"ERROR: {repr(e)}")
                _append_server_log(job, traceback.format_exc())
            jobs[thread_id] = Job(
                thread_id=thread_id,
                status="failed",
                progress=job.progress if job else {},
                error=repr(e),
            )
    finally:
        # 入力ZIPはPoCのため、そのまま残す（必要なら削除に変更可能）
        pass


def _start_background_thread(thread_id: str, message: str, input_zip_path: Optional[str]) -> None:
    t = threading.Thread(target=_run_workflow_in_background, args=(thread_id, message, input_zip_path), daemon=True)
    t.start()


# =====================================================
# API
# =====================================================


@app.post("/api/submit")
async def submit(
    background_tasks: BackgroundTasks,
    message: str = Form(...),
    file: Optional[UploadFile] = File(None),
):
    """ユーザーからの質問（+ 任意ZIP）を受け取り、バックグラウンドで処理を開始する。"""

    thread_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[thread_id] = Job(thread_id=thread_id, status="queued", progress={"queued_at": time.time(), "server_logs": deque(maxlen=200)})

    input_zip_path: Optional[str] = None
    if file is not None:
        # tool から参照できるよう一時ファイルに保存
        tmp_dir = Path(tempfile.gettempdir()) / "sv-agent-executor" / thread_id
        tmp_dir.mkdir(parents=True, exist_ok=True)
        input_zip_path = str(tmp_dir / (file.filename or "input.zip"))
        contents = await file.read()
        Path(input_zip_path).write_bytes(contents)

    # FastAPI の BackgroundTasks で「スレッド起動」を遅延実行
    background_tasks.add_task(_start_background_thread, thread_id, message, input_zip_path)

    return {"thread_id": thread_id, "status": "queued"}


@app.get("/api/status/{thread_id}")
async def status(thread_id: str):
    """ジョブの進捗を返す。

    - parallel_agent_workflow の tool 実行結果（stdout/stderr/成果物ZIPのbase64等）が
      Supervisor へ渡るため、progress.last_tool に含まれる可能性があります。
    """

    with jobs_lock:
        job = jobs.get(thread_id)
    if not job:
        raise HTTPException(status_code=404, detail="thread_id not found")

    # deque は JSON にできないので list に変換
    progress = dict(job.progress)
    if isinstance(progress.get("server_logs"), deque):
        progress["server_logs"] = list(progress["server_logs"])  # type: ignore[assignment]

    return {
        "thread_id": job.thread_id,
        "status": job.status,
        "progress": progress,
        "result": job.result,
        "error": job.error,
    }


if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="SV Agent Executor API Server")
    parser.add_argument("-p", "--port", type=int, default=5202, help="Port to run the API server on (default: 5202)")
    args = parser.parse_args()
    uvicorn.run(app, host="0.0.0.0", port=args.port)
