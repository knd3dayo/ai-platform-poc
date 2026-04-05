# I-01-04_03-nemo-guardrailsのDocker作成起動手順確認の検証

## 検証目的

本検証の主目的は、サブ課題 I-01-04「`03-nemo-guardrails` の Docker 作成・起動手順確認」について、NeMo Guardrails を前段ガードレール用コンポーネントとして起動できるか確認することである。

最終的には、I-01 の完了判定に必要な材料として、正常系、代表的な異常系、運用上の制約を明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| I-01 | I-01-04 | NeMo Guardrails の compose 資材と設定ディレクトリで起動できること |

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../03_検証準備/技術課題と対応方針.md)
  - I-01-04 に対応し、`infra/03-nemo-guardrails` の起動手順を確認する。
- [../../infra/03-nemo-guardrails/docker-compose.yml](../../infra/03-nemo-guardrails/docker-compose.yml)
  - 実際の compose 定義を確認する。
- [../../infra/03-nemo-guardrails/README.md](../../infra/03-nemo-guardrails/README.md)
  - 設定前提と起動方法を確認する。

## 検証で確認したいこと

### 1. 正常系

- compose 定義が解釈できること。
- NeMo Guardrails コンテナが起動し、設定ディレクトリを参照できること。

### 2. 異常系

- 停止時にサービス提供が継続しないこと。
- 設定不足時にログから原因を確認できること。

### 3. 運用系

- rails 設定更新後の再起動手順を説明できること。
- LiteLLM など前後段との関係を説明できること。

## 前提条件

- Docker / Docker Compose が利用可能であること。
- Guardrails の設定ファイル群が配置済みであること。

## 検証手順

### 1. 事前準備

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/03-nemo-guardrails"
docker compose config -q
```

### 2. 正常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/03-nemo-guardrails"
docker compose up -d
docker compose ps
docker compose logs --tail=50
```

期待結果:

- `docker compose config -q` が成功する。
- 対象サービスが running で表示される。
- 初期化失敗を示す致命的エラーがログに出ていない。

### 3. 異常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/03-nemo-guardrails"
docker compose stop
docker compose ps
docker compose start
```

期待結果:

- 停止中は running サービスが減少し、復旧手順で再開できる。

## 判定基準

| 観点 | 判定基準 |
| --- | --- |
| 構造成立性 | NeMo Guardrails の compose 資材と設定ディレクトリで起動できる。 |
| 制御成立性 | 停止・再開時の状態変化を把握できる。 |
| 運用成立性 | 設定更新と再起動の手順を説明できる。 |

## 検証結果記録欄

| 項目 | 結果 | 補足 |
| --- | --- | --- |
| 正常系 | OK | `docker compose config -q` は成功した。`docker compose up -d --build` により `nemo-guardrails` は healthy で起動し、`GET /v1/rails/configs` は `[{"id":"content_safety"}]` を返した。`OPENAI_API_KEY` を LiteLLM の Virtual Key (`sk-poc-master-key-12345`) に合わせた後は、`POST /v1/chat/completions` も HTTP 200 で通常応答した。 |
| 異常系 | OK | `docker compose stop` 実行中は `curl http://localhost:4080/v1/rails/configs` が `curl: (7) Failed to connect to localhost port 4080` で失敗した。設定不足を模した `nemoguardrails server --config=/missing --port=8000` では `/missing` に対する `FileNotFoundError` がログに出力され、原因を特定できた。 |
| 運用系 | OK | `docker compose start` / `docker compose restart` 後に `GET /v1/rails/configs` は再度成功した。`configs` 配下の設定更新は `docker compose restart` で反映できる。`OPENAI_API_KEY` にはクライアント向けのキーではなく、NeMo Guardrails から LiteLLM へ接続するための Virtual Key を設定する必要がある。危険入力では `I can't assist with that request.` を返すことも確認した。 |

## 残課題

- LiteLLM 前段配置の接続試験は成立したが、NeMo Guardrails を生成AIシステムアーキテクチャの標準的なガードレール機能として採用するかどうかは継続検討とする。
- 継続検討の理由として、クライアントから見た API キー認証がダミー化しやすいこと、Colang 利用時にクライアントが `thread_id` を意識する必要があることなど、運用・実装の扱いづらさがある。
- rails ごとの振る舞い差分や、他のガードレール実装との比較評価は本手順確認の対象外とする。