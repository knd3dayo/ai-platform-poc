import asyncio
import os
import httpx
from fastmcp import Client
from fastmcp.client import StreamableHttpTransport
from dotenv import load_dotenv
from mcp.types import (
    AudioContent,
    EmbeddedResource,
    ImageContent,
    ResourceLink,
    TextContent,
)

# .envファイルを読み込む
load_dotenv()

async def get_tokens():
    """マスターキーとOIDCトークンの両方を取得する"""
    master_key = os.getenv("LITELLM_MASTER_KEY", "sk-poc-master-key-12345")
    oidc_token = None

    # 戦略がOIDCの場合、Zitadelからトークンを取得
    if os.getenv("AUTH_STRATEGY", "").lower() == "oidc":
        print("🔑 Fetching OIDC token from Zitadel for backend propagation...")
        token_url = os.getenv("ZITADEL_TOKEN_URL")
        client_id = os.getenv("ZITADEL_CLIENT_ID")
        client_secret = os.getenv("ZITADEL_CLIENT_SECRET")
        scopes = os.getenv("ZITADEL_SCOPES", "openid profile")
        if not token_url or not client_id or not client_secret:
            print("⚠️ OIDC configuration is incomplete. Skipping token fetch.")
        else:

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    token_url,
                    data={"grant_type": "client_credentials", "scope": scopes},
                    auth=(client_id, client_secret),
                )
                response.raise_for_status()
                oidc_token = response.json().get("access_token")
                print(f"✅ OIDC token obtained: {oidc_token[:20]}...")
    
    return master_key, oidc_token

async def run_mcp_gateway_test():
    # 例: http://localhost:4000/my_hello_mcp/mcp
    gateway_url = os.getenv("MCP_GATEWAY_URL", "http://localhost:4000/my_hello_mcp/mcp")
    
    # URLからサーバーエイリアスを抽出 (my_hello_mcp)
    server_alias = gateway_url.split('/')[-2]
    
    try:
        # 1. 必要なトークンを準備
        master_key, oidc_token = await get_tokens()
        
        # 2. LiteLLM独自のプレフィックス・ヘッダーを構築
        # LiteLLMはこのプレフィックスを見て、バックエンド送信時にヘッダーをリネームします
        headers = {
            # LiteLLM Proxy自体の認証用
            "x-litellm-api-key": f"Bearer {master_key}",
            # バックエンドMCPで 'Authorization' として受け取らせる
            f"x-mcp-{server_alias}-Authorization": f"Bearer {master_key}",
            f"x-mcp-{server_alias}-litellm-api-key": f"{master_key}",
            f"x-mcp-{server_alias}-test": "This header is for testing purposes"
        }
        
        # OIDCトークンがある場合は、バックエンドで 'X-OIDC-Token' として受け取らせる
        if oidc_token:
            headers[f"x-mcp-{server_alias}-Authorization"] = f"Bearer {oidc_token}"

        print(f"🔌 Connecting to LiteLLM MCP Gateway at {gateway_url} ...")
        print(f"📡 Forwarding headers for alias: {server_alias}")
        
        # 3. 接続確立
        transport = StreamableHttpTransport(url=gateway_url, headers=headers)
        async with Client(transport) as client:
            
            # 4. ツール一覧の取得
            tools = await client.list_tools()
            print("\n✅ [Step 1] Tools available in LiteLLM Gateway:")
            for tool in tools:
                print(f" - {tool.name}: {tool.description}")

            # 5. hello ツールの実行
            tool_name = "hello"
            args = {"name": "MCP-Hybrid-Client"}
            
            print(f"\n🚀 [Step 2] Executing tool '{tool_name}' with dual-token propagation...")
            
            result = await client.call_tool(tool_name, arguments=args)
            
            # 6. 結果の表示
            print("\n📥 [Result from Backend MCP]:")
            print("------------------------------------------")
            for content in result.content:
                if isinstance(content, TextContent):
                    print(content.text)
                elif isinstance(content, ImageContent):
                    print(f"[Image Content: {content.mimeType}]")
                elif isinstance(content, ResourceLink):
                    print(f"[ResourceLink: {content.uri}]")
                else:
                    print(repr(content))
            print("------------------------------------------")
                    
    except Exception as e:
        print(f"❌ Error during MCP Gateway test: {e}")

if __name__ == "__main__":
    asyncio.run(run_mcp_gateway_test())