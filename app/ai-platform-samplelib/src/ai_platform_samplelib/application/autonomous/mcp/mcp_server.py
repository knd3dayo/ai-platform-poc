from __future__ import annotations

import argparse
import asyncio
import os
from functools import wraps
import inspect
from typing import Callable

from dotenv import load_dotenv
from fastmcp import FastMCP, Context

from ..core.endopoint import EndPoint
from ...common.request_headers import RequestHeaders, bind_current_request_headers

default_port = 7101

def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Run Autonomous Agent Executor MCP server")
	parser.add_argument(
		"-m",
		"--mode",
		choices=["sse", "http", "stdio"],
		default="stdio",
		help=(
			"Transport mode: 'stdio' (default), 'sse', or 'http' (streamable-http)."
		),
	)
	parser.add_argument(
		"-t",
		"--tools",
		type=str,
		default="",
		help=(
			"Comma-separated list of tool names to expose. "
			"Supported: healthz, execute, status, cancel. "
			"If omitted, all tools are exposed."
		),
	)
	parser.add_argument("--host", type=str, default="0.0.0.0", help="Bind host for sse/http")
	parser.add_argument("-p", "--port", type=int, default=default_port, help="Bind port for sse/http")
	parser.add_argument(
		"-v",
		"--log_level",
		type=str,
		default="",
		help=(
			"Log level (sets env var LOG_LEVEL if provided). "
			"fastmcp itself may not use it, but downstream libs can."
		),
	)
	parser.add_argument(
		"--sync_mode",
		action="store_true",
		help="Run MCP server in synchronous mode.",
	)

	return parser.parse_args()


def _normalize_tool_name(name: str) -> str:
	name = name.strip()
	if not name:
		return name
	# Allow EndPoint.healthz / endpoint.healthz-like inputs.
	if "." in name:
		name = name.split(".")[-1]
	return name


def prepare_mcp(mcp: FastMCP, tools_option: str, sync_mode: bool) -> None:
	def header_aware_tool(mcp_instance: FastMCP, *, tool_name: str):
		def decorator(func):
			@wraps(func)
			async def wrapper(*args, **kwargs):
				context = kwargs.pop("context", None)
				headers_obj: RequestHeaders | None = None
				if isinstance(context, Context):
					request_context = getattr(context, "request_context", None)
					request = getattr(request_context, "request", None) if request_context else None
					if request is not None:
						headers = {str(k).lower(): str(v) for k, v in request.headers.items()}
						headers_obj = RequestHeaders.from_mapping(headers)

				with bind_current_request_headers(headers_obj):
					return await func(*args, **kwargs)

			# IMPORTANT: Expose stable tool names expected by clients
			# (e.g. client calls "execute" while underlying implementation may be "execute_async").
			wrapper.__name__ = tool_name

			sig = inspect.signature(func)
			params = list(sig.parameters.values())
			if "context" not in [p.name for p in params]:
				params.append(
					inspect.Parameter(
						"context",
						inspect.Parameter.KEYWORD_ONLY,
						annotation=Context,
						default=None,
						)
				)
			setattr(wrapper, "__signature__", sig.replace(parameters=params))
			return mcp_instance.tool()(wrapper)

		return decorator

	tool_registry: dict[str, Callable[..., object]] = {
		"healthz": EndPoint.healthz,
		"execute": EndPoint.execute_async if not sync_mode else EndPoint.execute_sync,
		"status": EndPoint.status,
		"cancel": EndPoint.cancel,
	}

	if tools_option:
		selected = [_normalize_tool_name(t) for t in tools_option.split(",")]
		missing = [t for t in selected if t and t not in tool_registry]
		if missing:
			raise ValueError(
				f"Unknown tool(s): {missing}. Supported: {sorted(tool_registry.keys())}"
			)
		for t in selected:
			if not t:
				continue
			header_aware_tool(mcp, tool_name=t)(tool_registry[t])
		return

	for name, fn in tool_registry.items():
		header_aware_tool(mcp, tool_name=name)(fn)


async def main() -> None:
	load_dotenv()

	args = parse_args()
	if args.log_level:
		os.environ.setdefault("LOG_LEVEL", args.log_level)

	mcp = FastMCP("autonomous_agent_executor")
	prepare_mcp(mcp, args.tools, args.sync_mode)

	if args.mode == "stdio":
		await mcp.run_async()
		return

	if args.mode == "sse":
		await mcp.run_async(transport="sse", host=args.host, port=args.port)
		return

	# args.mode == "http"
	await mcp.run_async(transport="streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
	asyncio.run(main())

