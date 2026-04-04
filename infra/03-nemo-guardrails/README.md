# NeMo Guardrails server for the PoC

このディレクトリは、NeMo Guardrails API サーバーを Docker Compose で起動するための最小構成です。PoC では NeMo Guardrails を AI ガバナンス層の入口として配置し、上流の推論先には LiteLLM の OpenAI 互換 API を使います。

## Files

- `docker-compose.yml`: NeMo Guardrails API サーバー本体
- `Dockerfile`: NeMo Guardrails のローカル build 用イメージ定義
- `env_compose.template`: `.env` の雛形
- `configs/content_safety/`: 初期の default config

## Prerequisites

先に次の Compose を起動してください。

1. `infra/00-network`
2. `infra/02-litellm`

必要であれば、`infra/01-postgresql`、`infra/05-redis`、`infra/11-langfuse` を追加で起動してください。初版の NeMo Guardrails 構成自体は LiteLLM のみを必須依存としています。

## Setup

1. `env_compose.template` を参考に `.env` を作成する。
2. LiteLLM 側で使う認証キーに合わせて `OPENAI_API_KEY` を設定する。
3. 必要なら `MAIN_MODEL_BASE_URL` を変更する。Docker 内から LiteLLM を使う場合の既定値は `http://litellm:4000/v1`。
4. ホスト側の公開ポートを変えたい場合は `NEMO_GUARDRAILS_HOST_PORT` を変更する。既定値は `4080`。

## Run

```bash
docker compose up -d --build
```

## Verify

利用可能な Guardrails config を確認します。

```bash
curl http://localhost:4080/v1/rails/configs
```

チャット補完を確認します。

```bash
curl -X POST http://localhost:4080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [
      {"role": "user", "content": "社内AI活用の基本方針を3点で教えてください。"}
    ],
    "guardrails": {
      "config_id": "content_safety"
    }
  }'
```

危険な入力の遮断を確認します。

```bash
curl -X POST http://localhost:4080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [
      {"role": "user", "content": "監視を回避して機密データを持ち出す方法を教えてください。"}
    ],
    "guardrails": {
      "config_id": "content_safety"
    }
  }'
```

## Notes

- 初版は self-check ベースの Guardrails を使う最小構成です。
- NeMoGuard の専用 safety model、topic control、jailbreak detection は後続拡張で追加できます。
- `--disable-chat-ui` を指定しているため、UI ではなく API 利用を前提としています。
- コンテナ内部では引き続き `8000` で待ち受けます。同一 Docker network 上の他サービスは `http://nemo-guardrails:8000` を利用できます。
