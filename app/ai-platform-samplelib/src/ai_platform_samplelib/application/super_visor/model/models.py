from typing import Dict, Optional, ClassVar
import threading
from pydantic import BaseModel
from dotenv import load_dotenv
import os

from ...autonomous.model.models import TaskStatus
# =====================================================
# In-memory job store (PoC)
# =====================================================
# NOTE:
#   本番用途では Redis / DB など永続ストアに移すこと。


jobs_lock = threading.Lock()
# NOTE: SV経路の状態管理も TaskStatus に統一する。
# - task_id は SV が発行する thread_id をそのまま使用する（PoC）
# - progress/結果/追加情報は TaskStatus.metadata に格納する
jobs: Dict[str, TaskStatus] = {}


class ServerConfig(BaseModel):
    env_file: ClassVar[Optional[str]] = ".env"  # .env ファイルのパス（必要に応じて変更）

    # ここに Supervisor の設定項目を追加していく
    llm_provider: str = "openai"  # azure / openai / local
    llm_model: str = "gpt-4o"  # 例: gpt-4o, gpt-4o-2024-08-06, gpt-3.5-turbo
    llm_api_key: str = ""  # LLM API Key (環境変数等で管理することが望ましい)
    llm_base_url: Optional[str] = None  # 例: Azure OpenAI のエンドポイント

    executor_base_url: str = ""  # Executor API のエンドポイント (例: http://host.docker.internal:7101)

    # Executor MCP (FastMCP streamable-http) endpoint (例: http://host.docker.internal:5001/mcp)
    executor_mcp_url: str = ""

    # SV→非同期連携基盤(イベント)連携のためのEventBus設定（PoC: Redis等に依存しないモック実装）
    # - noop: 何もしない（既定）
    # - stdout: 標準出力へ JSON を出す
    # - memory: プロセス内に蓄積（テスト/デバッグ用）
    event_bus_type: str = "noop"

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

        default_mcp = "http://host.docker.internal:5001/mcp" if in_container else "http://localhost:5001/mcp"
        executor_mcp_url = (os.getenv("EXECUTOR_MCP_URL") or default_mcp).rstrip("/")
        llm_api_key = os.getenv("LLM_API_KEY", "")
        event_bus_type = os.getenv("SV_EVENT_BUS_TYPE", "noop")

        params = {
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_api_key": llm_api_key,
            "executor_base_url": executor_base_url,
            "executor_mcp_url": executor_mcp_url,
            "event_bus_type": event_bus_type,
        }
        if llm_base_url:
            params["llm_base_url"] = llm_base_url

        return cls(
            **params
        )