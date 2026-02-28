from pathlib import Path
import time
from collections import deque
import tempfile
import uuid
from typing import Any, Dict, Optional, List, Deque

from fastapi import FastAPI, BackgroundTasks, HTTPException, UploadFile, File, Form

from ..model.models import Job, jobs_lock, jobs
from ..core.utils import JobUtils
from ..core.parallel_agent_workflow import ToolNode, run_cline_executor, run_cline_executor_zip, start_background_thread

app = FastAPI(title="SV Agent Executor API")

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
    background_tasks.add_task(start_background_thread, thread_id, message, input_zip_path)

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


@app.delete("/api/cancel/{thread_id}")
async def cancel(thread_id: str):
    """ジョブのキャンセル要求を受け付ける。

    NOTE:
        - LangGraph 実行を強制停止する仕組みは限定的なため、ここでは cancel フラグを立てて
          stream ループを break する（ベストエフォート）。
        - すでに tool が Cline Executor のタスクを起動済みで task_id が取れる場合は、
          Executor 側 `/cancel/{task_id}` にもキャンセルを投げる。
    """
    with jobs_lock:
        job = jobs.get(thread_id)
        if not job:
            raise HTTPException(status_code=404, detail="thread_id not found")

        JobUtils.set_cancel_flag(job)
        JobUtils.append_server_log(job, "Cancel requested via API")
        JobUtils.try_cancel_executor_task(job)

    return {"thread_id": thread_id, "status": "cancel_requested"}


if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="SV Agent Executor API Server")
    parser.add_argument("-p", "--port", type=int, default=5202, help="Port to run the API server on (default: 5202)")
    args = parser.parse_args()
    uvicorn.run(app, host="0.0.0.0", port=args.port)
