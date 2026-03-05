import asyncio
import argparse
import inspect
import os
import jwt
from typing import Optional, Dict, Annotated, Optional
from contextvars import ContextVar
from functools import wraps
from fastmcp import FastMCP, Context


# スレッド/タスクセーフなコンテキスト変数
current_raw_headers: ContextVar[Dict[str, str]] = ContextVar("raw_headers", default={})

def identity_aware_tool(mcp_instance: FastMCP):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # FastMCPから自動注入されたcontextを回収
            context: Optional[Context] = kwargs.pop("context", None)
            
            if not isinstance(context, Context):
                return await func(*args, **kwargs)

            # FastMCPの内部構造からリクエストオブジェクトにアクセス
            # (FastMCPのバージョンにより構造が微細に異なる場合があるため安全にアクセス)
            request_context = getattr(context, "request_context", None)
            if not request_context:
                return await func(*args, **kwargs)
            
            request = getattr(request_context, "request", None)
            if not request:
                return await func(*args, **kwargs)
            
            # --- [追加] 生ヘッダーのキャプチャ処理 ---
            # すべてのヘッダーを小文字キーの辞書に変換して保存（プロキシでの小文字化対策）
            headers = {k.lower(): v for k, v in request.headers.items()}
            current_raw_headers.set(headers)
            return await func(*args, **kwargs)

        # --- FastMCP用シグネチャ調整ロジック ---
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
    
# --- 3. メイン処理 ---
mcp = FastMCP("Test-Server")

@identity_aware_tool(mcp)
async def hello(name: Annotated[str, "Your name"]) -> str:
    """
    名前を挨拶し、現在保持されている2つのトークン情報、
    および実際にサーバーが受信したヘッダー一覧を返します。
    """
    # 全ヘッダーを取得
    raw_headers = current_raw_headers.get()
    
    # 全ヘッダーを整形
    headers_str = "\n".join([f"{k}: {v}" for k, v in raw_headers.items()])

    return (
        f"Hello, {name}!\n\n"
        f"--- [Full Received Headers] ---\n"
        f"{headers_str}\n"
    )

async def main():
    # -p --port オプションでポートを指定できるようにする
    parser = argparse.ArgumentParser(description="Identity-Aware MCP Server")
    parser.add_argument("-p", "--port", type=int, default=5101, help="Port to run the MCP server on")
    args = parser.parse_args()

    port = args.port
    print(f"🚀 Starting Identity-Aware MCP server on port {port}...")
    # 実際には identity_aware_tool のラッパー内で 
    # current_raw_headers.set(context.request.headers) 
    # を行う必要があります。
    await mcp.run_async(transport="streamable-http", host="0.0.0.0", port=port)

if __name__ == "__main__":
    asyncio.run(main())