from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from ..core.endopoint import EndPoint
from ..model.models import CancelResponse, ExecuteResponse, HealthzResponse, TaskStatus


app = FastAPI(title="Autonomous Agent Executor API", version="0.1")


app.get("/healthz", response_model=HealthzResponse)(EndPoint.healthz)
app.post("/execute", response_model=ExecuteResponse)(EndPoint.execute)
app.get("/status/{task_id}", response_model=TaskStatus)(EndPoint.status)
app.delete("/cancel/{task_id}", response_model=CancelResponse)(EndPoint.cancel)

if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Run Autonomous Agent Executor API")
    parser.add_argument("-p", "--port", type=int, default=7101)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port)
