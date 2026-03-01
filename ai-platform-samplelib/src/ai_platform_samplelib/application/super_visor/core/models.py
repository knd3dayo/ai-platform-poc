from dataclasses import dataclass
from typing import Dict, Any, Optional
import threading
from pydantic import BaseModel
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

jobs: Dict[str, Job] = {}


class ServerConfig(BaseModel):
    # ここに Supervisor の設定項目を追加していく
    llm_provider: str = "openai"  # azure / openai / local
    llm_model: str = "gpt-4o"  # 例: gpt-4o, gpt-4o-2024-08-06, gpt-3.5-turbo
    llm_base_url: Optional[str] = None  # 例: Azure OpenAI のエンドポイント
    llm_api_key: Optional[str] = None  # LLM API Key (環境変数等で管理することが望ましい)

    autonomous_agent_server_url: Optional[str] = None  # Autonomous Agent Workflow API のエンドポイント (例: http://autonomous-agent-workflow:5202)
    