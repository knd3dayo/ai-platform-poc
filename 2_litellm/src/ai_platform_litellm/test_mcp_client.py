import asyncio
from fastmcp import Client
from fastmcp.client import StreamableHttpTransport

async def test_gateway_list_tools():
    # LiteLLMゲートウェイのMCP専用エンドポイント
    # 形式: http://<litellm_host>:<port>/<config.yamlの登録名>/mcp
    url = "http://localhost:4000/mcp"
    
    # LiteLLMのマスターキー（または特定のアクセス権を持つキー）で認証
    headers = {
        "Authorization": "Bearer sk-poc-master-key-12345"
    }
    
    print(f"🔌 Connecting to LiteLLM MCP Gateway at {url} ...")
    
    try:
        # 認証ヘッダーを付与してLiteLLMゲートウェイに接続
        streamable_http_transport = StreamableHttpTransport(url=url, headers=headers)
        async with (
            Client(streamable_http_transport) as client
        ):
            tools = await client.list_tools()
            print("✅ Tools available in LiteLLM Gateway:")
            for tool in tools:
                print(f" - {tool.name} (description: {tool.description})")
                    
    except Exception as e:
        print(f"❌ Error connecting to Gateway: {e}")

if __name__ == "__main__":
    asyncio.run(test_gateway_list_tools())