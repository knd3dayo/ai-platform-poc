from typing import Dict, Any, Optional, ClassVar
from collections import deque
import threading
from pydantic import BaseModel, field_serializer
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

    # NOTE:
    #   progress に deque を保持していると FastAPI/Pydantic の JSON 変換で
    #   `Unable to serialize unknown type: <class 'collections.deque'>` が発生する。
    #   ただし server_logs はリングバッファとして deque のまま保持したいので、
    #   レスポンスへ dump するタイミングだけ list に変換する。
    @field_serializer("progress")
    def _serialize_progress(self, progress: Dict[str, Any]):
        if not isinstance(progress, dict):
            return progress

        server_logs = progress.get("server_logs")
        if isinstance(server_logs, deque):
            # shallow copy して server_logs だけ list 化
            return {**progress, "server_logs": list(server_logs)}

        return progress


jobs_lock = threading.Lock()
jobs: Dict[str, Job] = {}


class ServerConfig(BaseModel):
    env_file: ClassVar[Optional[str]] = ".env"  # .env ファイルのパス（必要に応じて変更）

    # ここに Supervisor の設定項目を追加していく
    llm_provider: str = "openai"  # azure / openai / local
    llm_model: str = "gpt-4o"  # 例: gpt-4o, gpt-4o-2024-08-06, gpt-3.5-turbo
    llm_api_key: str = ""  # LLM API Key (環境変数等で管理することが望ましい)
    llm_base_url: Optional[str] = None  # 例: Azure OpenAI のエンドポイント

    executor_base_url: str = ""  # Executor API のエンドポイント (例: http://host.docker.internal:7101)

    # 環境変数や .env ファイルから設定をロードする関数    
    @classmethod
    def load_from_env(cls) -> "ServerConfig":
        load_dotenv(cls.env_file)

        in_container = os.path.exists("/.dockerenv")
        llm_provider = os.getenv("LLM_PROVIDER", "openai")
        llm_base_url = os.getenv("LLM_BASE_URL") 
        llm_model = os.getenv("LLM_MODEL", "gpt-4o")
        executor_base_url = os.getenv("EXECUTOR_BASE_URL") or ("http://host.docker.internal:7101" if in_container else "http://localhost:7101")
        executor_base_url = executor_base_url.rstrip("/")
        llm_api_key = os.getenv("LLM_API_KEY", "")

        params = {
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_api_key": llm_api_key,
            "executor_base_url": executor_base_url,
        }
        if llm_base_url:
            params["llm_base_url"] = llm_base_url

        return cls(
            **params
        )