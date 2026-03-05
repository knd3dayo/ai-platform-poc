# 02 共通基盤アプリのサンプル実装 Assurance層

## ステップ2：AI Assurance層（LiteLLM Proxy）の構築

LiteLLM Proxyは、全てのLLMリクエストの「関所」です。ここでは、**「ガードレール（検閲）」「監査（Langfuse）」「MCPゲートウェイ」**の3機能を一気に立ち上げます。

### 2-1. プロジェクト構造の準備

まず、カスタムHook用のディレクトリを含む構造を作成します。

```bash
mkdir -p 2_litellm/src/ai_platform_litellm
cd 2_litellm
# uvを利用したパッケージ管理（任意）
uv init

```

### 2-2. カスタムHookの実装（ガードレール）

設定ファイルから参照される「検閲ロジック」を先に作成します。ここで、機密情報の遮断やPIIマスキングの基礎を実装します。

**`src/ai_platform_litellm/custom_hooks.py`**

```python
from litellm.integrations.custom_logger import CustomLogger
import litellm

class MyEnterpriseGuardrail(CustomLogger):
    """
    エンタープライズ向けのガードレール実装。
    入力内容のチェックと、トレースIDの伝播を担う。
    """
    # 【入力ゲート】LLMへ送信する直前に発火
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        messages = data.get("messages", [])
        
        # trace_idの取得（BFFから渡される想定）
        metadata = data.get("metadata", {})
        trace_id = metadata.get("trace_id", "no-trace-id")

        for msg in messages:
            content = msg.get("content")
            if content is None or not isinstance(content, str):
                continue
                
            # 【検閲】NGワードや機密情報のチェック
            ng_words = ["litellm_ng_test", "社外秘", "password"]
            if any(word in content for word in ng_words):
                raise Exception(f"【Security Alert】機密情報が含まれているため、リクエストを遮断しました。 (Trace: {trace_id})")
        
        return data

    # 【出力ゲート】成功時に発火
    async def async_post_call_success_hook(self, data, user_api_key_dict, response):
        pass

# LiteLLM設定ファイルから参照するためのインスタンス
proxy_handler_instance = MyEnterpriseGuardrail()

```

### 2-3. 設定ファイル（config.yaml）の作成

LiteLLMの挙動を定義します。**「Pythonのインスタンスをどこで呼ぶか」**がポイントです。

**`config.yaml`**

```yaml
model_list:
  - model_name: gpt-4o
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/OPENAI_API_KEY

litellm_settings:
  success_callbacks: ["langfuse"]
  failure_callbacks: ["langfuse"]
  # ↓ 先ほど作成したPythonクラスのインスタンスを指定
  callbacks: ai_platform_litellm.custom_hooks.proxy_handler_instance

mcp_servers:
  my_hello_mcp:
    url: "http://mcp-server:5101/mcp"
    type: "http" # Streamable HTTP (SSE) を使用
    # MCPサーバー（Denodo等）に引き継ぎたいヘッダーを定義
    extra_headers: 
      Authorization: "Bearer token" # 必要に応じて動的に変更
      x-trace-id: "metadata.trace_id" 

```

### 2-4. インフラ構成（Docker）と環境変数

**`.env`**

```env
LITELLM_MASTER_KEY=sk-poc-master-key-12345
OPENAI_API_KEY=sk-your-openai-api-key
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
# 同一ネットワーク上のLangfuseサービス名を指定
LANGFUSE_HOST=http://langfuse-web:3000 

```
## Docker Compose再起動
```bash
docker compose down
docker compose up -d 
```

---

### 2-5. 動作確認テスト

#### ① 通常の疎通確認

```bash
curl -X POST 'http://localhost:4000/v1/chat/completions' \
-H 'Authorization: Bearer sk-poc-master-key-12345' \
-H 'Content-Type: application/json' \
-d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "こんにちは"}]
}'

```

#### ② ガードレールの遮断テスト

NGワードを含めて送信し、`500 Internal Server Error`（またはExceptionメッセージ）が返れば成功です。

```bash
curl -X POST 'http://localhost:4000/v1/chat/completions' \
-H 'Authorization: Bearer sk-poc-master-key-12345' \
-H 'Content-Type: application/json' \
-d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "litellm_ng_test"}]
}'

```

#### ③ MCP経由でのツール呼び出しテスト

自作のMCPクライアント、またはLiteLLMのAPI経由でツールが露出しているか確認します。

```bash
# MCPツール一覧の確認
curl -H 'Authorization: Bearer sk-poc-master-key-12345' 'http://localhost:4000/v1/tools'

```

---

---

## 2-5. 統合テスト：MCPゲートウェイとID伝播の検証

LiteLLM Proxyが単なるプロキシではなく、**「認証情報を適切に書き換えてバックエンド（Denodo等）に渡せているか」**を検証します。このテストが成功すれば、Application層（LangGraph）から透過的にツールを使える準備が整います。

### ① 必要パッケージのインストール

テストクライアントの実行に必要なライブラリを追加します。

```bash
uv add httpx fastmcp python-dotenv

```

### ② テストクライアントの配置

以下のコードを `src/ai_platform_litellm/test_mcp_client.py` として保存します。このスクリプトは、**OIDCトークンの取得 ➔ LiteLLMプレフィックス付与 ➔ MCPツール実行** の一連の流れをシミュレートします。

<details>
<summary>📋 テスト用クライアントコードを表示</summary>

```python
# (ご提示いただいたコードをここに配置します)
import asyncio
import os
import httpx
from fastmcp import Client
from fastmcp.client import StreamableHttpTransport
from dotenv import load_dotenv
from mcp.types import TextContent, ImageContent, ResourceLink

load_dotenv()

async def get_tokens():
    """マスターキーとOIDCトークンの両方を取得する"""
    master_key = os.getenv("LITELLM_MASTER_KEY", "sk-poc-master-key-12345")
    oidc_token = None

    if os.getenv("AUTH_STRATEGY", "").lower() == "oidc":
        print("🔑 Fetching OIDC token from Zitadel...")
        # ... (OIDC取得ロジック)
    
    return master_key, oidc_token

async def run_mcp_gateway_test():
    gateway_url = os.getenv("MCP_GATEWAY_URL", "http://localhost:4000/my_hello_mcp/mcp")
    server_alias = gateway_url.split('/')[-2]
    
    try:
        master_key, oidc_token = await get_tokens()
        
        # 【重要】LiteLLMはこのプレフィックスを見て、バックエンド送信時にヘッダーをリネームします
        headers = {
            "x-litellm-api-key": f"Bearer {master_key}",
            f"x-mcp-{server_alias}-Authorization": f"Bearer {oidc_token if oidc_token else master_key}",
            f"x-mcp-{server_alias}-test": "Identity Propagation Test"
        }
        
        transport = StreamableHttpTransport(url=gateway_url, headers=headers)
        async with Client(transport) as client:
            # ツール一覧の取得確認
            tools = await client.list_tools()
            print(f"\n✅ [Step 1] Tools found: {[t.name for t in tools]}")

            # ツール実行確認
            result = await client.call_tool("hello", arguments={"name": "AI-Platform-Tester"})
            print(f"\n📥 [Result]: {result.content[0].text}")
                    
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    asyncio.run(run_mcp_gateway_test())

```

</details>

---

### ③ テストの実行とチェックポイント

環境変数をセットし、テストを実行します。

```bash
# 実行
uv run -m ai_platform_litellm.test_mcp_client

```

#### 🔍 ログで確認すべき3つのポイント

1. **LiteLLMのログ**:
`async_pre_call_hook` が発火し、NGワードチェックが走り抜けているかを確認します。
2. **MCPサーバー（Denodo等）の受信ログ**:
LiteLLMがプレフィックスを剥がし、生（なま）の `Authorization` ヘッダーとしてトークンが届いているかを確認します。
3. **Langfuseの画面**:
新しいトレースが作成され、どのツールが呼ばれたか、コスト（トークン量）が記録されているかを確認します。

---
