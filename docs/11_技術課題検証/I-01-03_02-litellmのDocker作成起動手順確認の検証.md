# I-01-03_02-litellmのDocker作成起動手順確認の検証

## 検証目的

本検証の主目的は、サブ課題 I-01-03「`02-litellm` の Docker 作成・起動手順確認」について、LiteLLM Proxy を PoC 基盤の共通 LLM ゲートウェイとして起動できるか確認することである。

最終的には、I-01 の完了判定に必要な材料として、正常系、代表的な異常系、運用上の制約を明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| I-01 | I-01-03 | `.env` と `config.yaml` を前提に LiteLLM Proxy を起動し、HTTP エンドポイントへ到達できること |

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../03_検証準備/技術課題と対応方針.md)
  - I-01-03 に対応し、`infra/02-litellm` の compose 資材による起動手順を確認する。
- [01_生成AI基盤インフラ構築手順.md](../21_検証結果/01_生成AI基盤インフラ構築手順.md)
  - LiteLLM Proxy の起動と疎通確認の基準手順を参照する。
- [../../infra/02-litellm/docker-compose.yml](../../infra/02-litellm/docker-compose.yml)
  - 実際の compose 定義を確認する。
- [../../infra/02-litellm/config.yaml](../../infra/02-litellm/config.yaml)
  - モデル定義と callback 設定の前提を確認する。

## 検証で確認したいこと

### 1. 正常系

- compose 定義が解釈できること。
- LiteLLM コンテナが起動し、HTTP エンドポイントへアクセスできること。
- `config.yaml` と `.env` の前提が手順として明示されていること。

### 2. 異常系

- 停止時に HTTP エンドポイントへの到達が失敗すること。
- 設定不足時に `docker compose config` または起動ログから問題箇所を特定できること。

### 3. 運用系

- 設定ファイル変更後の再起動手順を説明できること。
- Langfuse や上流クライアントとの依存関係を説明できること。

## 前提条件

- I-01-01 の共通ネットワークが作成済みであること。
- 必要な API キー類を `.env` に設定済みであること。

## 検証手順

### 1. 事前準備

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/02-litellm"
docker compose config -q
```

### 2. 正常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/02-litellm"
docker compose up -d
docker compose ps
curl -X POST 'http://localhost:4000/v1/chat/completions' \
  -H 'Authorization: Bearer sk-poc-master-key-12345' \
  -H 'Content-Type: application/json' \
  -d '{"model":"poc-chat-model","messages":[{"role":"user","content":"ping"}]}'
```

期待結果:

- `docker compose config -q` が成功する。
- `litellm` が running で表示される。
- `localhost:4000` への API 呼び出しでレスポンスが返る。

### 3. 異常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/02-litellm"
docker compose stop
curl -X POST 'http://localhost:4000/v1/chat/completions' \
  -H 'Authorization: Bearer sk-poc-master-key-12345' \
  -H 'Content-Type: application/json' \
  -d '{"model":"poc-chat-model","messages":[{"role":"user","content":"ping"}]}'
docker compose start
```

期待結果:

- 停止中は HTTP エンドポイント呼び出しが失敗する。
- 再開後は正常系に戻せる。

## 判定基準

| 観点 | 判定基準 |
| --- | --- |
| 構造成立性 | LiteLLM Proxy の compose 定義と設定ファイルで環境を再現できる。 |
| 制御成立性 | 停止時に API 呼び出しが失敗し、稼働状態を判別できる。 |
| 運用成立性 | 設定投入、再起動、依存関係の説明が手順化されている。 |

## 検証結果記録欄

| 項目 | 結果 | 補足 |
| --- | --- | --- |
| 正常系 | OK | `docker compose config -q` は成功した。`docker compose up -d` 後に `litellm` は running となり、`model=poc-chat-model` を指定した `curl -X POST http://localhost:4000/v1/chat/completions ...` は `http_code=200` で応答し、本文は `pong` を返した。`.env` には `OPENAI_API_KEY`、`LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY`、`LANGFUSE_HOST` の定義を確認した。 |
| 異常系 | OK | `docker compose stop` 実行中は同 API 呼び出しが `curl: (7) Failed to connect to localhost port 4000` で失敗した。設定不備を模した `docker compose run --rm litellm --config /app/missing-config.yaml` では `Config file not found: /app/missing-config.yaml` が出力され、起動ログから問題箇所を特定できた。 |
| 運用系 | OK | `docker compose start` と `docker compose restart` 後に再度 `http_code=200` を確認した。`config.yaml` 変更時は `docker compose restart` で反映できる。依存関係として `ai_platform_internal` / `ai_platform_egress`、共有 PostgreSQL、`.env` に定義した Langfuse / OpenAI 設定が必要である。 |

## 検証メモ

### 1. モデル名はエイリアス運用を基本とする

- LiteLLM は実在モデル名をそのまま公開するよりも、`production-chat-model` や `standard-large-model` のようなエイリアスをクライアントに使わせる運用が望ましい。
- エイリアスを使うことで、クライアント実装を変更せずに、LiteLLM 側の `config.yaml` だけで接続先モデルを差し替えられる。
- 開発、検証、本番で同じエイリアス名を維持したまま、背後の実モデルだけを切り替える運用にも向く。

### 2. エイリアス利用の主な利点

- 疎結合を維持できる。将来 `gpt-4o` から別モデルへ移行しても、クライアントコードの修正範囲を最小化できる。
- 環境ごとの差し替えがしやすい。たとえば Dev では安価なモデル、本番では高性能モデルへ同一エイリアスで切り替えられる。
- Virtual Key、流量制御、利用制限などの運用ルールを「実モデル名」ではなく「業務上の役割名」に紐づけられる。

### 3. NeMo Guardrails と組み合わせる場合の考え方

- クライアントは NeMo Guardrails 側の rails ID もしくは config 名を指定し、その設定の内部で LiteLLM のエイリアスを呼ぶ形にするのが整理しやすい。
- つまり、クライアントが直接実モデル名を知る必要はなく、Guardrails 側は対話制御名、LiteLLM 側は LLM ルーティング名として役割分担させるのが望ましい。
- この分離により、Guardrails のシナリオ名と、LiteLLM 上の実モデル選択・切替を独立して運用できる。

### 4. 厳格なクライアントとの互換性メモ

- OpenAI 互換クライアントの多くは `model` を単なる文字列として送るため、LiteLLM がその名前を解決できれば独自エイリアスでも問題ない。
- 一方で、利用ツール側が既知のモデル名リストでバリデーションする場合は、表向きのエイリアスを `gpt-4o` のような既知名に寄せ、その先を LiteLLM 内部で特定バージョンへ固定する運用も選択肢になる。

### 5. 現行 PoC 構成に対する補足

- `infra/02-litellm/config.yaml` は `poc-chat-model`、`poc-embedding-model`、`poc-fast-model` のような役割ベースの `model_name` に変更した。
- 実モデルは LiteLLM の背後に隠蔽し、クライアントや NeMo Guardrails からはエイリアス名だけを参照する構成へ寄せた。
- `poc-chat-model` を指定した直接呼び出しでは、HTTP 200 かつ `pong` 応答を確認した。

### 6. メモリ使用量メモ

- 2026-04-05 の再計測では、`docker stats --no-stream` 時点で LiteLLM コンテナは `854 MiB` 前後を使用しており、Langfuse ClickHouse と並んで重いコンテナだった。
- プロセス内訳は、LiteLLM 本体の Python プロセスが約 `814 MiB RSS`、Prisma query engine が約 `23 MiB RSS` で、補助スレッドや子プロセスは相対的に小さい。
- 起動オプションから `--detailed_debug` を外して再計測したところ、定常状態の LiteLLM コンテナは `834 MiB` 前後となり、差分は約 `20 MiB` だった。ログ量は大きく減る一方、メモリ削減効果は限定的である。
- 通常ログ起動でも `POST http://localhost:4000/chat/completions` は HTTP 200 で継続応答したため、常時デバッグが不要な通常運用では `--detailed_debug` なしを基本値としてよい。
- ログ上では spend 集計、DB 書き込み、日次集計キューなどの定期処理が継続的に動作しており、単純な OpenAI 互換中継より常駐メモリが大きくなる構成である。

## 残課題

- モデル別 API キーの切替や hook 実装の詳細確認は別サブ課題で扱う。
- LiteLLM の `model_name` を実モデル名直書きから業務役割ベースのエイリアスへ変更するかは別途判断する。
- Langfuse 連携の完全性は I-01-07 と合わせて確認する。