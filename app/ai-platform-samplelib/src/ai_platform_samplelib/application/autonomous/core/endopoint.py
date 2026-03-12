import os
import pathlib
from typing import Any, Dict, Optional, Annotated

from fastapi import Body, HTTPException, Path, Query

from ..core.task_service_factory import select_task_service
from ..core.task_manager import TaskManager

from ..model.models import (
    CancelResponse,
    ExecuteRequest,
    ExecuteResponse,
    HealthzResponse,
    TaskStatus,
)

from ...common.request_headers import RequestHeaders, get_current_request_headers

class EndPoint:

    @staticmethod
    def validate_workspace_path(workspace_path: str) -> pathlib.Path:
        if not isinstance(workspace_path, str) or not workspace_path.strip():
            raise HTTPException(status_code=400, detail="workspace_path is required")

        p = pathlib.Path(workspace_path).expanduser()
        if not p.is_absolute():
            raise HTTPException(status_code=400, detail="workspace_path must be an absolute path")

        # 任意だが、パス注入対策として許可ルート配下に制限できる
        allowed_root = os.getenv("EXECUTOR_ALLOWED_WORKSPACE_ROOT")
        if allowed_root:
            root = pathlib.Path(allowed_root).expanduser().resolve()
            resolved = p.resolve()
            try:
                if not resolved.is_relative_to(root):
                    raise HTTPException(status_code=403, detail="workspace_path is outside allowed root")
            except AttributeError:
                # Python < 3.9 互換（本PJは 3.11+ 前提だが念のため）
                if str(resolved).startswith(str(root)) is False:
                    raise HTTPException(status_code=403, detail="workspace_path is outside allowed root")

        # workspace はSVが用意するが、無ければ作る
        p.mkdir(parents=True, exist_ok=True)
        return p


    @staticmethod
    async def healthz() -> HealthzResponse:
        """
        ヘルスチェック用エンドポイント。SVはこれを叩いてエージェントが生きているか確認する。
        """
        return HealthzResponse(status="ok")


    @staticmethod
    async def _execute_main_(
        wait_for_completion: bool,
        req: Annotated[ExecuteRequest, Body(description="タスク実行リクエスト")],
    ) -> ExecuteResponse:
        """
        タスク実行用エンドポイント（同期版/非同期版）の共通処理。SVはこれを叩いてエージェントにタスク実行を指示する。
        引数のwait_for_completionで、タスク完了までHTTPレスポンスを返すかどうかを制御する。
        """
        workspace_dir = EndPoint.validate_workspace_path(req.workspace_path)

        # Inbound headers are captured by:
        # - FastAPI middleware (HTTP API)
        # - MCP tool wrapper (MCP server)
        incoming = get_current_request_headers()

        if incoming and incoming.trace_id and not req.trace_id:
            req.trace_id = incoming.trace_id

        task_service = select_task_service()
        await task_service.prepare(
            prompt=req.prompt,
            sources=None,
            task_id=req.task_id,
            workspace_path=workspace_dir,
            extra_env=(incoming.to_env() if incoming else None),
        )

        if req.trace_id:
            task_service.get_agent_runner().get_task_status().trace_id = req.trace_id

        task_status = task_service.start(wait=wait_for_completion, timeout=req.timeout)
        TaskManager.upsert_task(task_status)

        # For synchronous execution, block until the task converges to a final state.
        # `start(wait=True)` only marks the initial intent (foreground) for the backend;
        # actual convergence is performed by `monitor()`.
        if wait_for_completion:
            async for st in task_service.monitor(timeout=req.timeout):
                TaskManager.upsert_task(st)

        return ExecuteResponse(task_id=task_status.task_id)

    @staticmethod
    async def execute_sync(
        req: Annotated[ExecuteRequest, Body(description="タスク実行リクエスト")],
    ) -> ExecuteResponse:
        """
        タスク実行用エンドポイント（同期版）。ユーザーはこれを叩いてエージェントにタスク実行を指示する。
        executeとの違いは、タスク完了までHTTPレスポンを返さない点。小規模タスクやテスト用途向け。
        """
        return await EndPoint._execute_main_(wait_for_completion=True, req=req)


    @staticmethod
    async def execute_async(
        req: Annotated[ExecuteRequest, Body(description="タスク実行リクエスト")],
    ) -> ExecuteResponse:
        """
        タスク実行用エンドポイント（非同期版）。ユーザーはこれを叩いてエージェントにタスク実行を指示する。
        処理が完了する前にHTTPレスポンスを返す。
        ユーザーは/statusエンドポイントを叩いてタスクの進捗や結果を取得する。   
        キャンセルを行う場合は、/cancelエンドポイントを叩く。
        """
        return await EndPoint._execute_main_(wait_for_completion=False, req=req)

    @staticmethod
    async def status(
        task_id: Annotated[str, Path(description="task id")],
        tail: Annotated[
            Optional[int],
            Query(description="ログの末尾 n 行（省略時は 200、null で全量）", ge=0),
        ] = 200,
    ) -> TaskStatus:
        """
         タスクステータス取得用エンドポイント。SVはこれを叩いてタスクの進捗や結果を取得する。
         tailはログの末尾n行を取得するためのパラメータ。
         既存のTaskStatus(JSONをそのまま返す。SV側は status/sub_status を見て完了判定する。
        """
        return await TaskManager.get_status(task_id, tail=tail)


    @staticmethod
    async def cancel(task_id: Annotated[str, Path(description="task id")]) -> CancelResponse:
        """
         タスクキャンセル用エンドポイント。SVはこれを叩いてタスクのキャンセルを指示する。
        """
        res: Any = await TaskManager.cancel_task(task_id)
        if isinstance(res, dict):
            return CancelResponse(**res)
        return CancelResponse(message="cancel requested")

