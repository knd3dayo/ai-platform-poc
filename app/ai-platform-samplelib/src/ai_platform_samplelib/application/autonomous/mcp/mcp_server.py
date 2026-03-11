from __future__ import annotations

import argparse
import asyncio
import os
from typing import Callable

from dotenv import load_dotenv
from fastmcp import FastMCP

from ..core.endopoint import EndPoint


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
	parser.add_argument("-p", "--port", type=int, default=5001, help="Bind port for sse/http")
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
	return parser.parse_args()


def _normalize_tool_name(name: str) -> str:
	name = name.strip()
	if not name:
		return name
	# Allow EndPoint.healthz / endpoint.healthz-like inputs.
	if "." in name:
		name = name.split(".")[-1]
	return name


def prepare_mcp(mcp: FastMCP, tools_option: str) -> None:
	tool_registry: dict[str, Callable[..., object]] = {
		"healthz": EndPoint.healthz,
		"execute": EndPoint.execute,
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
			mcp.tool()(tool_registry[t])
		return

	for fn in tool_registry.values():
		mcp.tool()(fn)


async def main() -> None:
	load_dotenv()

	args = parse_args()
	if args.log_level:
		os.environ.setdefault("LOG_LEVEL", args.log_level)

	mcp = FastMCP("autonomous_agent_executor")
	prepare_mcp(mcp, args.tools)

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

