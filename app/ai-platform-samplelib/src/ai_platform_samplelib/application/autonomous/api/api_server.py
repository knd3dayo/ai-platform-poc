from __future__ import annotations

from fastapi import FastAPI

from ..core.endopoint import EndPoint
from ..model.models import CancelResponse, ExecuteResponse, HealthzResponse, TaskStatus


def create_app(*, sync_mode: bool = False) -> FastAPI:
    """Create FastAPI app.

    `sync_mode=False` (default): /execute returns immediately (async execution).
    `sync_mode=True`: /execute blocks until task completion (sync execution).
    """

    app = FastAPI(title="Autonomous Agent Executor API", version="0.1")

    app.get("/healthz", response_model=HealthzResponse)(EndPoint.healthz)
    app.post("/execute", response_model=ExecuteResponse)(
        EndPoint.execute_sync if sync_mode else EndPoint.execute_async
    )
    app.get("/status/{task_id}", response_model=TaskStatus)(EndPoint.status)
    app.delete("/cancel/{task_id}", response_model=CancelResponse)(EndPoint.cancel)

    return app


# Default app instance for uvicorn import-style usage.
app = create_app(sync_mode=False)

if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Run Autonomous Agent Executor API")
    parser.add_argument("-p", "--port", type=int, default=7101)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument(
        "--sync_mode",
        action="store_true",
        help="Run API server in synchronous mode (/execute blocks until completion).",
    )
    args = parser.parse_args()

    uvicorn.run(create_app(sync_mode=args.sync_mode), host=args.host, port=args.port)
