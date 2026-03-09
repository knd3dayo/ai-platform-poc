from typing import Any, Dict, Optional

from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode

from ..model.models import ServerConfig
from .autonomous_executor_api_client import AutonomousExecutorApiClient
from .utils import error_result, poll_status


class Tools:

    @tool
    @staticmethod
    def run_autonomous_agent_executor(
        prompt: str,
        workspace_path: str,
        timeout: int = 300,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Executor Service(コーディングエージェント実行API) を呼び出して結果を返す（同期ツール）。

        共有workspace前提のため、SV側で workspace を用意し、このツールには
        `workspace_path`（ホスト絶対パス）を渡す。

        呼び出し:
        1) POST /execute で task_id を取得（即時復帰）
        2) GET /status/{task_id} を完了までポーリング
        3) 最終結果(TaskStatus)を返す

        NOTE:
            LangGraph の ToolNode は同期実行パスを通ることがあるため、このツールは同期関数にしている。
        """

        try:
            server_config = ServerConfig.load_from_env()
            base_url = server_config.executor_base_url
            client = AutonomousExecutorApiClient(base_url)

            task_id = client.execute(
                prompt=prompt,
                workspace_path=workspace_path,
                timeout=timeout,
                trace_id=trace_id,
            )
            try:
                final_status = poll_status(task_id, timeout_sec=timeout + 30)
            except Exception as e:
                return error_result(f"Failed to poll status: {e}", task_id=task_id)

            return {
                "task_id": task_id,
                "workspace_path": workspace_path,
                **final_status,
            }
        except Exception as e:
            return error_result(f"run_autonomous_agent_executor failed: {e}")

    tools: list = [run_autonomous_agent_executor]
    tools_node = ToolNode(tools)
