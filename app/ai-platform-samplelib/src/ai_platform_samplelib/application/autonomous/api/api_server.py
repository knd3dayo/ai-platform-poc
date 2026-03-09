from __future__ import annotations

import os
import pathlib
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException

from ..core.coding_agent_runner import CodingAgentRunner
from ..core.task_manager import TaskManager

from .models import ExecuteRequest, ExecuteResponse


app = FastAPI(title="Autonomous Agent Executor API", version="0.1")


def _validate_workspace_path(workspace_path: str) -> pathlib.Path:
    if not isinstance(workspace_path, str) or not workspace_path.strip():
        raise HTTPException(status_code=400, detail="workspace_path is required")

    p = pathlib.Path(workspace_path).expanduser()
    if not p.is_absolute():
        raise HTTPException(status_code=400, detail="workspace_path must be an absolute path")

    # 任意だが、パス注入対策として許可ルート配下に制限できる
    allowed_root = os.getenv("EXECUTOR_ALLOWED_WORKSPACE_ROOT")
    if allowed_root:
        root = pathlib.Path(allowed_root).expanduser().resolve()
        resolved = p.resolve()
        try:
            if not resolved.is_relative_to(root):
                raise HTTPException(status_code=403, detail="workspace_path is outside allowed root")
        except AttributeError:
            # Python < 3.9 互換（本PJは 3.11+ 前提だが念のため）
            if str(resolved).startswith(str(root)) is False:
                raise HTTPException(status_code=403, detail="workspace_path is outside allowed root")

    # workspace はSVが用意するが、無ければ作る
    p.mkdir(parents=True, exist_ok=True)
    return p


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/execute", response_model=ExecuteResponse)
async def execute(req: ExecuteRequest) -> ExecuteResponse:
    workspace_dir = _validate_workspace_path(req.workspace_path)

    # task_id は外部から指定可（未指定ならcreate_runner内で採番）
    runner = await CodingAgentRunner.create_runner(
        prompt=req.prompt,
        task_id=req.task_id,
        detach=True,
        workspace_path=workspace_dir,
    )
    if req.trace_id:
        runner.task_status.trace_id = req.trace_id

    container = runner.run()
    runner.task_status.container_id = getattr(container, "id", None)
    runner.task_status.starting_background()
    TaskManager.upsert_task(runner.task_status)

    return ExecuteResponse(task_id=runner.task_id)


@app.get("/status/{task_id}")
async def status(task_id: str, tail: Optional[int] = 200) -> Any:
    # 既存のTaskStatus(JSON)をそのまま返す（SV側は status/sub_status を見て完了判定する）
    task = await TaskManager.get_status(task_id, tail=tail)
    return task.model_dump(mode="json")


@app.delete("/cancel/{task_id}")
async def cancel(task_id: str) -> Dict[str, Any]:
    res: Any = await TaskManager.cancel_task(task_id)
    if isinstance(res, dict):
        return res
    return {"message": "cancel requested"}


if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Run Autonomous Agent Executor API")
    parser.add_argument("-p", "--port", type=int, default=7101)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port)
