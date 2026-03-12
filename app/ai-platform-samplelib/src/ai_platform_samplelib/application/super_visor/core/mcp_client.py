from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional, TypeVar, Coroutine, cast

from fastmcp import Client
from fastmcp.client import StreamableHttpTransport
from mcp.types import TextContent


T = TypeVar("T")


def _run_coro_sync(coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine from sync code.

    ToolNode may call sync tools from either a non-async context or within an
    already-running event loop. In the latter case, we run the coroutine in a
    dedicated thread to avoid "asyncio.run() cannot be called" errors.
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}
    error: list[BaseException] = []

    def _worker() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as e:
            error.append(e)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join()

    if error:
        raise error[0]

    if "value" not in result:
        raise RuntimeError("Failed to obtain coroutine result")
    return cast(T, result["value"])


def _extract_json_from_call_tool_result(tool_result: Any) -> Dict[str, Any]:
    """Best-effort JSON extraction from FastMCP Client.call_tool result."""

    if isinstance(tool_result, dict):
        return tool_result

    content = getattr(tool_result, "content", None)
    if not isinstance(content, list) or not content:
        return {"result": tool_result}

    # Prefer first text content
    for item in content:
        if isinstance(item, TextContent):
            text = item.text
            if not isinstance(text, str):
                continue
            text = text.strip()
            if not text:
                continue
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
                return {"result": parsed}
            except Exception:
                return {"result": text}

    # Fallback: return repr
    return {"result": repr(content)}


@dataclass(frozen=True)
class ExecutorMcpConfig:
    url: str
    headers: dict[str, str]


class AutonomousExecutorMcpClient:
    def __init__(self, *, url: str, headers: Optional[dict[str, str]] = None) -> None:
        url = (url or "").strip()
        if not url:
            raise ValueError("Executor MCP url is required")
        self._cfg = ExecutorMcpConfig(url=url, headers=headers or {})

    async def _call(self, tool_name: str, arguments: dict[str, Any]) -> Dict[str, Any]:
        transport = StreamableHttpTransport(url=self._cfg.url, headers=self._cfg.headers)
        async with Client(transport) as client:
            res = await client.call_tool(tool_name, arguments=arguments)
        return _extract_json_from_call_tool_result(res)

    def execute(
        self,
        *,
        prompt: str,
        workspace_path: str,
        timeout: int,
        trace_id: Optional[str],
        task_id: Optional[str] = None,
    ) -> str:
        async def _run() -> str:
            req: dict[str, Any] = {
                "prompt": prompt,
                "workspace_path": workspace_path,
                "timeout": int(timeout),
            }
            if task_id:
                req["task_id"] = task_id
            if trace_id:
                req["trace_id"] = trace_id

            data = await self._call("execute", {"req": req})
            tid = data.get("task_id")
            if not isinstance(tid, str) or not tid:
                raise RuntimeError(f"Invalid execute response: {data}")
            return tid

        return _run_coro_sync(_run())

    def status(self, task_id: str, *, tail: Optional[int] = 200) -> Dict[str, Any]:
        async def _run() -> Dict[str, Any]:
            args: dict[str, Any] = {"task_id": task_id}
            if tail is not None:
                args["tail"] = tail
            return await self._call("status", args)

        return _run_coro_sync(_run())

    def cancel(self, task_id: str) -> Dict[str, Any]:
        async def _run() -> Dict[str, Any]:
            return await self._call("cancel", {"task_id": task_id})

        return _run_coro_sync(_run())
