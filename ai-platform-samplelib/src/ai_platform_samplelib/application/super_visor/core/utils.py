from collections import deque
from typing import Deque, Dict, Any
import time
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.runnables import Runnable
from pydantic import SecretStr


from ..model.models import Job, jobs_lock, jobs, ServerConfig


class LLMUtils:
    @staticmethod
    def create_llm() -> Runnable:
        """LLMのインスタンスを生成する関数（必要に応じてカスタマイズ）"""
        # .envファイルから環境変数を読み込む
        server_config = ServerConfig.load_from_env()
        params = {
            "model": server_config.llm_model,
            "api_key": SecretStr(server_config.llm_api_key or ""),
        }
        if server_config.llm_base_url:
            base_url = server_config.llm_base_url
            params["base_url"] = base_url
        
        llm = ChatOpenAI(
            **params
            )
        return llm

class JobUtils:
    @classmethod
    def append_server_log(cls, job: Job, line: str, max_lines: int = 200) -> None:
        """サーバ側の進捗ログをリングバッファで保持する（/api/status で返す用）。"""
        logs: Deque[str] = job.progress.setdefault("server_logs", deque(maxlen=max_lines))  # type: ignore[assignment]
        # deque は json 化できないので、返却時に list 化する
        if isinstance(logs, deque):
            logs.append(line)

    @classmethod
    def get_cancel_flag(cls, job: Job) -> bool:
        return bool(job.progress.get("cancel_requested"))


    @classmethod
    def set_cancel_flag(cls, job: Job) -> None:
        job.progress["cancel_requested"] = True
        job.progress["cancel_requested_at"] = time.time()


    @classmethod
    def try_cancel_executor_task(cls, job: Job) -> None:
        """tool 結果に task_id が入っていれば Autonomous Agent Executor へ cancel を投げる（ベストエフォート）。"""
        last_tool = job.progress.get("last_tool")
        if not isinstance(last_tool, dict):
            return
        task_id = last_tool.get("task_id")
        if not task_id:
            return

        base_url = job.progress.get("executor_base_url")
        if not isinstance(base_url, str) or not base_url:
            return

        try:
            import requests

            requests.delete(f"{base_url.rstrip('/')}/cancel/{task_id}", timeout=10)
            cls.append_server_log(job, f"Sent cancel to executor task_id={task_id}")
        except Exception as e:
            cls.append_server_log(job, f"Failed to cancel executor task: {e}")

