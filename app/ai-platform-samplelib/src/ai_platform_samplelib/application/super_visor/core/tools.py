from typing import Any, Dict, Optional
import os
import time

from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode

from ..model.models import ServerConfig
from .mcp_client import AutonomousExecutorMcpClient
from .utils import error_result


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

        def _poll_status_mcp(client: AutonomousExecutorMcpClient, task_id: str, timeout_sec: int) -> Dict[str, Any]:
            deadline = time.time() + timeout_sec
            terminal_sub_status = {"completed", "failed", "timeout", "cancelled"}

            while True:
                status_data = client.status(task_id, tail=200)
                status = status_data.get("status")
                sub_status = status_data.get("sub_status")

                if status == "exited":
                    return status_data
                if isinstance(sub_status, str) and sub_status in terminal_sub_status:
                    return status_data

                if time.time() > deadline:
                    raise TimeoutError(
                        f"Timed out while waiting executor task completion: task_id={task_id}"
                    )

                time.sleep(1.0)

        try:
            server_config = ServerConfig.load_from_env()

            # Authorization forwarding (best-effort)
            auth = (
                os.getenv("SV_AUTHORIZATION")
                or os.getenv("AI_PLATFORM_AUTHORIZATION")
                or os.getenv("AUTHORIZATION")
            )
            headers: dict[str, str] = {}
            if auth:
                headers["Authorization"] = auth
            if trace_id:
                headers["x-trace-id"] = trace_id

            client = AutonomousExecutorMcpClient(url=server_config.executor_mcp_url, headers=headers)

            task_id = client.execute(
                prompt=prompt,
                workspace_path=workspace_path,
                timeout=timeout,
                trace_id=trace_id,
            )
            try:
                final_status = _poll_status_mcp(client, task_id, timeout_sec=timeout + 30)
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
