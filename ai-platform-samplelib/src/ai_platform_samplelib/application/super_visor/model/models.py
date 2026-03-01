from typing import Dict, Any, Optional, ClassVar
import threading
from pydantic import BaseModel
from dotenv import load_dotenv
import os
# =====================================================
# In-memory job store (PoC)
# =====================================================
# NOTE:
#   本番用途では Redis / DB など永続ストアに移すこと。

class Job (BaseModel):
    thread_id: str
    status: str  # queued, running, completed, failed
    # status polling で返すための進捗情報（PoC）
    progress: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


jobs_lock = threading.Lock()
jobs: Dict[str, Job] = {}


class ServerConfig(BaseModel):
    env_file: ClassVar[Optional[str]] = ".env"  # .env ファイルのパス（必要に応じて変更）

    # ここに Supervisor の設定項目を追加していく
    llm_provider: str = "openai"  # azure / openai / local
    llm_model: str = "gpt-4o"  # 例: gpt-4o, gpt-4o-2024-08-06, gpt-3.5-turbo
    llm_base_url: Optional[str] = None  # 例: Azure OpenAI のエンドポイント
    llm_api_key: Optional[str] = None  # LLM API Key (環境変数等で管理することが望ましい)

    executor_base_url: str = ""  # Executor API のエンドポイント (例: http://host.docker.internal:7101)

    # 環境変数や .env ファイルから設定をロードする関数    
    @classmethod
    def load_from_env(cls) -> "ServerConfig":
        load_dotenv(cls.env_file)

        in_container = os.path.exists("/.dockerenv")
        llm_base_url = os.getenv("LLM_BASE_URL") or ("http://litellm:4000/v1" if in_container else "http://localhost:4000/v1")
        executor_base_url = os.getenv("EXECUTOR_BASE_URL") or ("http://host.docker.internal:7101" if in_container else "http://localhost:7101")
        executor_base_url = executor_base_url.rstrip("/")

        return cls(
            llm_provider=os.getenv("LLM_PROVIDER", "openai"),
            llm_model=os.getenv("LLM_MODEL", "gpt-4o"),
            llm_base_url=llm_base_url,
            llm_api_key=os.getenv("LLM_API_KEY"),
            executor_base_url=executor_base_url,
        )