# 01 共通基盤アプリのサンプル実装_Tool層

## 1. 【準備】Zitadel（IdP）の構築と設定

まずは認証のソースとなるZitadelを起動し、テスト用のクライアント（Machine-to-Machine）を作成します。

### 1-1. Dockerによる起動

既存の `ai-platform-net` に参加させ、各コンポーネントが名前解決できるようにします。

```yaml
# 0_zitadel/docker-compose.yml
services:
  zitadel:
    image: ghcr.io/zitadel/zitadel:latest
    # ... (省略: ポート設定、環境変数等) ...
    networks:
      - default
      - ai_platform_net

networks:
  ai_platform_net:
    external: true

```

### 1-2. Zitadelコンソールでのキー作成

1. `http://localhost:8080/ui/console` へログイン（初期：`zitadel-admin@zitadel.localhost` / `Password1!`）。
2. **Projects** ➔ **AI-Platform** を作成。
3. **Applications** ➔ **Create** ➔ **API**（Machine-to-Machine）を選択。
4. **Auth Method** を **Basic** に設定。
5. 生成された **Client ID** と **Client Secret** をメモし、テストクライアントの `.env` に設定します。

---

## 2. 【受信側】Identity-Aware MCPサーバー（Tool層）

次に、リクエストを受け取るバックエンド（Denodo相当）を作成します。このサーバーは、**「LiteLLMから送られてきた生（なま）のヘッダー」**を表示するデバッグ機能を備えています。

### 2-1. 実装のポイント：ヘッダーキャプチャ

`FastMCP` の標準機能ではヘッダーへのアクセスが制限されているため、デコレータを用いてリクエストコンテキストからヘッダーを抽出します。

```python
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

```

---

## 3. 【リレー側】テスト用クライアント（BFF相当）

最後に、Zitadelからトークンを取得し、LiteLLM Proxyへリクエストを送るクライアントを実装します。

### 3-1. 実装のポイント：`x-mcp` プレフィックス

LiteLLM Proxyの仕様に基づき、バックエンドに渡したいヘッダーには `x-mcp-{alias}-` というプレフィックスを付与します。

```python
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

```

---

## 4. このテストで証明されること

このサンプルを動かすことで、以下のアーキテクチャ上の要件が満たされていることが証明されます。

1. **認証の隔離**: クライアントはIdP（Zitadel）のトークンを知っているが、LiteLLMがその正当性を仲介している。
2. **ID伝播の実効性**: LiteLLM Proxyがプレフィックス付きヘッダーを解釈し、バックエンドのMCPサーバー（Denodo）へ**正しい `Authorization` ヘッダーとして再構成**して届けている。
3. **セマンティックレイヤーの準備**: MCPサーバー側で `current_raw_headers` を通じてユーザーIDを特定できるため、Denodo側でユーザーごとの行レベルアクセス制御が可能になる。

---

