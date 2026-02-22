import asyncio
import json
from typing import Annotated, Dict
from fastmcp import FastMCP
# あなたの作成したモジュールをインポート
from ai_platform_litellm.tool_wrapper import identity_aware_tool, current_raw_headers

# --- 3. メイン処理 ---
mcp = FastMCP("OIDC-Test-Server")

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
    port = 5001
    print(f"🚀 Starting Identity-Aware MCP server on port {port}...")
    # 実際には identity_aware_tool のラッパー内で 
    # current_raw_headers.set(context.request.headers) 
    # を行う必要があります。
    await mcp.run_async(transport="streamable-http", host="0.0.0.0", port=port)

if __name__ == "__main__":
    asyncio.run(main())