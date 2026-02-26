from typing import Dict, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

# --- リクエスト/レスポンスモデル ---

class ClineRequest(BaseModel):
    prompt: str = Field(..., examples=["hello.py を修正して"])
    initial_files: Optional[Dict[str, str]] = None # 事前に配置したいファイル
    timeout: int = Field(default=300, ge=1, le=1800)

class TaskStatus(BaseModel):
    task_id: str
    status: str  # running, completed, failed, timeout
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    artifacts: Optional[List[str]] = None
    created_at: datetime
    container_id: Optional[str] = None


# タスク管理ストア（本番はRedis推奨）
tasks: Dict[str, TaskStatus] = {}


