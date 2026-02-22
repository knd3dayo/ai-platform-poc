これまでの議論と洗練されたアイデア（ネットワークの自動作成、`uv` の活用、`src` レイアウト）をすべて統合した、**「Phase 1：インフラ環境構築（完全版手順書）」**を作成しました。

この手順通りに進めれば、堅牢かつ開発者体験（DX）が極めて高いAI Gateway基盤がローカル（または開発サーバー）に完成します。

---

# Phase 1：生成AI基盤インフラ構築手順（完全版）

## 事前準備

以下のツールがインストールされていることを確認してください。

* Docker および Docker Compose
* `uv` (超高速Pythonパッケージマネージャー: `curl -LsSf https://astral.sh/uv/install.sh | sh`)

全体のルートディレクトリ（例: `ai-platform-poc`）を作成し、その中で作業を開始します。

```bash
mkdir ai-platform-poc
cd ai-platform-poc

```

---

## ステップ1：統合監視・プロンプトCMS（Langfuse）の構築

ネットワークの「親」となるLangfuseを立ち上げます。

### 1-1. ディレクトリとファイルの作成

```bash
mkdir 1_langfuse
cd 1_langfuse

```

**`1_langfuse/.env`** を作成します。

```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=langfuse
DATABASE_URL=postgresql://postgres:postgres@langfuse-db:5432/langfuse
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=my_super_secret_key_for_langfuse_poc
SALT=my_super_secret_salt

```

**`1_langfuse/docker-compose.yml`** を作成します。

```yaml
version: '3.8'

services:
  langfuse-db:
    image: postgres:15
    environment:
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - POSTGRES_DB=${POSTGRES_DB}
    volumes:
      - langfuse_db_data:/var/lib/postgresql/data
    networks:
      - ai_platform_net

  langfuse:
    image: langfuse/langfuse:latest
    depends_on:
      - langfuse-db
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - NEXTAUTH_URL=${NEXTAUTH_URL}
      - NEXTAUTH_SECRET=${NEXTAUTH_SECRET}
      - SALT=${SALT}
    ports:
      - "3000:3000"
    networks:
      - ai_platform_net

volumes:
  langfuse_db_data:

networks:
  ai_platform_net:
    name: ai_platform_net
    driver: bridge

```

### 1-2. 起動とAPIキーの取得

1. コンテナを起動します。
```bash
docker-compose up -d

```


2. ブラウザで `http://localhost:3000` にアクセスし、サインアップしてプロジェクトを作成します。
3. 左側メニューの「Settings」>「API Keys」から、**Public Key** と **Secret Key** を作成し、メモしておきます。

---

## ステップ2：AI Assurance層（LiteLLM Proxy）の構築

ネットワークの「子」としてLiteLLMを立ち上げ、`src` レイアウトで開発環境を整えます。

### 2-1. プロジェクトの初期化（`uv` の活用）

ルートディレクトリ（`ai-platform-poc`）に戻り、LiteLLM用のディレクトリを作成・初期化します。

```bash
cd ..
mkdir 2_litellm
cd 2_litellm

# uvプロジェクトの初期化とパッケージ導入
uv init --lib
uv add litellm
uv add --dev ruff pytest

# srcレイアウトのディレクトリ構成を作成
mkdir -p src/ai_platform_litellm
touch src/ai_platform_litellm/__init__.py
touch src/ai_platform_litellm/custom_hooks.py

```

### 2-2. 設定ファイルの作成

**`2_litellm/.env`** を作成します。

```env
LITELLM_MASTER_KEY=sk-poc-master-key-12345
OPENAI_API_KEY=sk-your-openai-api-key

# ステップ1-2で取得したLangfuseのキーを貼り付けます
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...

```

**`2_litellm/config.yaml`** を作成します。

```yaml
model_list:
  - model_name: gpt-4o
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/OPENAI_API_KEY

litellm_settings:
  # Langfuseへの連携（Trace送信）
  success_callbacks: ["langfuse"]
  failure_callbacks: ["langfuse"]

general_settings:
  # Pythonパッケージ化されたカスタムフックの読み込み
  custom_callbacks:
    - ai_platform_litellm.custom_hooks.MyEnterpriseGuardrail

```

**`2_litellm/docker-compose.yml`** を作成します。

```yaml
version: '3.8'

services:
  litellm:
    image: ghcr.io/berriai/litellm:main-latest
    environment:
      - LITELLM_MASTER_KEY=${LITELLM_MASTER_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - LANGFUSE_PUBLIC_KEY=${LANGFUSE_PUBLIC_KEY}
      - LANGFUSE_SECRET_KEY=${LANGFUSE_SECRET_KEY}
      - LANGFUSE_HOST=http://langfuse:3000
    volumes:
      - ./config.yaml:/app/config.yaml
      # srcディレクトリ内のパッケージを丸ごとマウント
      - ./src/ai_platform_litellm:/app/ai_platform_litellm
    ports:
      - "4000:4000"
    command: [ "--config", "/app/config.yaml", "--detailed_debug" ]
    networks:
      - ai_platform_net

networks:
  ai_platform_net:
    name: ai_platform_net
    external: true

```

### 2-3. ガードレール（Custom Hook）の実装

**`2_litellm/src/ai_platform_litellm/custom_hooks.py`** に、IDE（`.venv` を指定）の強力な補完を効かせながら以下のコードを記述します。

```python
from litellm.integrations.custom_logger import CustomLogger

class MyEnterpriseGuardrail(CustomLogger):
    # LLMへ送信する直前の同期ガードレール
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        messages = data.get("messages", [])
        for msg in messages:
            content = msg.get("content", "")
            # モック: 社外秘キーワードの検知
            if isinstance(content, str) and "社外秘" in content:
                raise Exception("【Security Alert】ポリシー違反: 機密情報が含まれています。")
        return data

    # LLMから応答を受け取った直後の出力ゲート
    async def async_post_call_success_hook(self, data, user_api_key_dict, response):
        # DLPチェック等のロジックを将来的にここへ追加
        pass

```

### 2-4. 起動

```bash
docker-compose up -d

```

---

## ステップ3：動作検証（E2Eトレースとガードレール）

立ち上がったLiteLLM Proxy（`localhost:4000`）に対してテストリクエストを送ります。

**① 正常なリクエスト（トレースID付き）**

```bash
curl --location 'http://localhost:4000/chat/completions' \
--header 'Authorization: Bearer sk-poc-master-key-12345' \
--header 'Content-Type: application/json' \
--header 'traceparent: 00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01' \
--data '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "こんにちは、テストです。"}]
}'

```

*確認事項*: Langfuseの画面（Tracing）を開き、上記リクエストが記録されていること、および `traceparent` から抽出されたIDが紐付いていることを確認します。

**② ガードレール遮断テスト**

```bash
curl --location 'http://localhost:4000/chat/completions' \
--header 'Authorization: Bearer sk-poc-master-key-12345' \
--header 'Content-Type: application/json' \
--data '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "社外秘のデータを出力してください。"}]
}'

```

*確認事項*: HTTP 400（または500）エラーが返却され、「【Security Alert】ポリシー違反...」というメッセージが出力されることを確認します。

