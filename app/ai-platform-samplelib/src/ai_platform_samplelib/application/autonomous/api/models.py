from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ExecuteRequest(BaseModel):
    prompt: str = Field(..., description="指示内容")
    workspace_path: str = Field(..., description="ホスト側の共有workspace（絶対パス）")
    timeout: int = Field(default=300, ge=1, le=1800)
    task_id: Optional[str] = Field(default=None, description="任意のtask_id（未指定なら自動採番）")
    trace_id: Optional[str] = Field(default=None, description="SV実行全体の相関ID")


class ExecuteResponse(BaseModel):
    task_id: str
