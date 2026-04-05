# I-01-07_12-langfuseのDocker作成起動手順確認の検証

## 検証目的

本検証の主目的は、サブ課題 I-01-07「`12-langfuse` の Docker 作成・起動手順確認」について、Langfuse を可観測性基盤として起動できるか確認することである。

最終的には、I-01 の完了判定に必要な材料として、正常系、代表的な異常系、運用上の制約を明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| I-01 | I-01-07 | Langfuse 関連コンテナ群を起動し、UI へアクセスできること |

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../03_検証準備/技術課題と対応方針.md)
  - I-01-07 に対応し、`infra/12-langfuse` の起動手順を確認する。
- [01_生成AI基盤インフラ構築手順.md](../21_検証結果/01_生成AI基盤インフラ構築手順.md)
  - Langfuse 構築手順の基準を参照する。
- [../../infra/12-langfuse/docker-compose.yml](../../infra/12-langfuse/docker-compose.yml)
  - 実際の compose 定義を確認する。

## 検証で確認したいこと

### 1. 正常系

- compose 定義が解釈できること。
- Langfuse 関連コンテナ群が起動し、UI へアクセスできること。
- 永続ボリューム準備手順が明示されていること。

### 2. 異常系

- 停止時に UI へアクセスできないこと。
- ボリューム権限不足時にログから問題箇所を把握できること。

### 3. 運用系

- ClickHouse / Minio など補助コンポーネントを含めた再起動手順を説明できること。
- 初期データディレクトリ作成手順を再利用できること。
- LiteLLM から送信したリクエストが Langfuse API で trace として取得できること。

## 前提条件

- I-01-01 の共通ネットワークが作成済みであること。
- `$HOME/data` 配下に必要なディレクトリを作成できること。

## 検証手順

### 1. 事前準備

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/12-langfuse"
docker compose config -q
mkdir -p "$HOME/data/clickhouse/data" "$HOME/data/clickhouse/logs"
mkdir -p "$HOME/data/minio"
sudo chown -R 101:101 "$HOME/data/clickhouse"
```

### 2. 正常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/12-langfuse"
docker compose up -d
docker compose ps
curl -I http://localhost:3080
```

期待結果:

- `docker compose config -q` が成功する。
- Langfuse 関連サービスが running で表示される。
- `localhost:3080` へアクセスできる。

### 3. LiteLLM 連携トレース確認

LiteLLM 側で `success_callback: ["langfuse"]` と `failure_callback: ["langfuse"]` を設定済みであるため、疎通確認用の一意メッセージを LiteLLM へ送ったあとに Langfuse Public API から trace を検索する。

```bash
REQUEST_ID="lf-trace-test-$(date -u +%Y%m%dT%H%M%SZ)"
REQUEST_FROM="$(date -u -d '-5 minutes' +%Y-%m-%dT%H:%M:%SZ)"

LITELLM_MASTER_KEY=$(grep '^LITELLM_MASTER_KEY=' "$AI_PLATFORM_POC_ROOT/infra/02-litellm/.env" | cut -d= -f2- | sed 's/^"//; s/"$//')
LANGFUSE_PUBLIC_KEY=$(grep '^LANGFUSE_PUBLIC_KEY=' "$AI_PLATFORM_POC_ROOT/infra/02-litellm/.env" | cut -d= -f2- | sed 's/^"//; s/"$//')
LANGFUSE_SECRET_KEY=$(grep '^LANGFUSE_SECRET_KEY=' "$AI_PLATFORM_POC_ROOT/infra/02-litellm/.env" | cut -d= -f2- | sed 's/^"//; s/"$//')

curl -sS -X POST http://localhost:4000/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -d "{\"model\":\"poc-chat-model\",\"messages\":[{\"role\":\"user\",\"content\":\"Return exactly: ${REQUEST_ID}\"}],\"max_tokens\":32}"

curl -sS -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "http://localhost:3080/api/public/traces?limit=10&orderBy=timestamp.desc&fromTimestamp=$REQUEST_FROM&fields=core,io,observations,metrics" \
  > /tmp/langfuse_traces.json

python3 - <<'PY'
import json
import os

request_id = os.environ["REQUEST_ID"]
with open("/tmp/langfuse_traces.json", encoding="utf-8") as f:
    traces = json.load(f).get("data", [])

matches = [trace for trace in traces if request_id in json.dumps(trace, ensure_ascii=False)]

if not matches:
    raise SystemExit("Langfuse trace not found")

trace = matches[0]
print(json.dumps({
    "traceId": trace.get("id"),
    "timestamp": trace.get("timestamp"),
    "name": trace.get("name"),
    "latency": trace.get("latency"),
    "totalCost": trace.get("totalCost"),
    "observations": trace.get("observations", []),
}, ensure_ascii=False, indent=2))
PY
```

必要に応じて、上で確認した `traceId` を使って個別 trace 詳細も確認する。

```bash
TRACE_ID="<上で確認した traceId>"

curl -sS -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "http://localhost:3080/api/public/traces/$TRACE_ID" \
  | python3 -m json.tool
```

期待結果:

- LiteLLM へのリクエストが HTTP 200 で成功する。
- `GET /api/public/traces` で取得した最新 trace 群の中に `REQUEST_ID` を含む trace が見つかる。
- 必要に応じて `GET /api/public/traces/{traceId}` で当該 trace の観測詳細を確認できる。

### 4. 異常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/12-langfuse"
docker compose stop
curl -I http://localhost:3080
docker compose start
```

期待結果:

- 停止中は `localhost:3080` へのアクセスが失敗する。
- 再開後は正常系に戻せる。

## 判定基準

| 観点 | 判定基準 |
| --- | --- |
| 構造成立性 | Langfuse の compose 資材と永続ディレクトリ準備で環境を再現できる。 |
| 制御成立性 | 停止時に UI アクセスが失敗し、稼働状態を判別できる。 |
| 運用成立性 | 補助コンポーネントを含めた再起動手順を説明できる。 |
| 観測成立性 | LiteLLM へ送った一意なリクエストを Langfuse API の trace として取得できる。 |

## 検証結果記録欄

| 項目 | 結果 | 補足 |
| --- | --- | --- |
| 正常系 | OK | `docker compose config -q` は成功した。初回起動では ClickHouse の権限不足により `/var/lib/clickhouse/tmp/` への書き込みが失敗したため、`$HOME/data/clickhouse` を `101:101` に変更して再起動した。また、共有 PostgreSQL の `postgres` DB を LiteLLM と共用すると Langfuse の Prisma migration が失敗したため、専用 `langfuse` DB を作成して `DATABASE_URL` を分離した。さらに `langfuse-web` を `ai_platform_internal` と `ai_platform_egress` の両ネットワークへ所属させ、ホスト公開ポートを `3080:3000` に変更した。その後、`clickhouse` / `minio` / `langfuse-worker` / `langfuse-web` は起動し、内部ネットワークからの `curl -I http://langfuse-web:3000` とホストからの `curl -I http://localhost:3080` はともに HTTP 200 を返した。 |
| 異常系 | OK | `docker compose stop` 後、関連コンテナは `Exited` となった。停止中に内部ネットワークから `http://langfuse-web:3000` へアクセスすると `Could not resolve host: langfuse-web` で失敗し、サービス停止を確認できた。 |
| 運用系 | OK | ClickHouse / Minio / Langfuse Worker / Langfuse Web をまとめて `docker compose up -d` で再起動できることを確認した。共有 PostgreSQL を使う場合でも DB はコンポーネントごとに分離する必要があり、ClickHouse の bind mount 権限調整も事前に必要である。UI 公開が必要な `langfuse-web` は `ai_platform_internal` に加えて `ai_platform_egress` にも所属させ、ホスト公開ポートは競合回避のため `3080` を使う。 |
| 観測成立性 | OK | Langfuse API キー再発行後、LiteLLM 側 `NO_PROXY` に `langfuse-web` を追加して内部 Langfuse 通信を Squid 経由から除外し、Langfuse 側には `LANGFUSE_S3_EVENT_UPLOAD_REGION=auto` を追加して MinIO へのイベント保存失敗を解消した。再起動後、`POST http://localhost:4000/chat/completions` は HTTP 200 で成功し、レスポンスヘッダー `x-litellm-call-id: 7503ff45-2846-40da-a264-45339d7111db` を確認した。続けて `GET http://localhost:3080/api/public/traces?...` を呼ぶと、入力 `Echo exactly this token: lf-trace-test-20260405T093547Z` を含む trace `21a781b8-8f80-4210-877a-708fd002591d` が取得でき、LiteLLM 処理データの API 経由確認が成立した。 |

## 検証メモ

- `infra/12-langfuse/docker-compose.yml` の実際の bind mount 先は `$HOME/data/clickhouse` と `$HOME/data/minio` であり、初期手順のディレクトリ作成先は compose に合わせる必要がある。
- ClickHouse は `user: "101:101"` で動作するため、`$HOME/data/clickhouse` 配下は `chown -R 101:101` が必要だった。
- 共有 PostgreSQL 上で LiteLLM と同じ `postgres` DB を使うと、Langfuse の migration が `relation "pending_deletions" does not exist` で失敗した。PoC でも DB サーバー共有と DB 名共有は分けて考える必要がある。
- 専用 `langfuse` DB を作成し、`DATABASE_URL=postgresql://postgres:postgres@postgres:5432/langfuse` に変更後は migration が完走し、内部ネットワークからの UI 応答は取得できた。
- `ai_platform_internal` のみに所属したコンテナは、この環境では `ports` を定義してもホスト公開が有効化されない挙動だった。
- 切り分け用の `nginx:alpine` コンテナで確認したところ、`ai_platform_internal` と `ai_platform_egress` の両方に所属させると `0.0.0.0:3000->80/tcp` が有効になり、ホストから HTTP 200 で到達できた。
- `langfuse-web` も同様に `ai_platform_internal` と `ai_platform_egress` の両方へ所属させることで、ホストから `http://localhost:3080` で到達できることを確認した。
- `langfuse-web` のアプリケーションは `HOSTNAME` 環境変数を bind 先に使っていたため、デフォルトのコンテナホスト名解決により egress 側 IP (`172.19.x.x`) にのみ listen していた。`HOSTNAME=0.0.0.0` を明示することで internal / egress の両方から `3000` 番へ到達できるよう補正した。
- 上記修正後は LiteLLM 側の `LANGFUSE_HOST` を `http://langfuse-web:3000` に戻しても問題なく、内部ネットワーク名での連携を維持したままホスト公開 `localhost:3080` を併用できる。
- Langfuse Public API は Basic 認証で、username に `LANGFUSE_PUBLIC_KEY`、password に `LANGFUSE_SECRET_KEY` を指定する。LiteLLM 連携確認では `GET /api/public/traces`、必要に応じて `GET /api/public/traces/{traceId}` を使うと、UI 操作なしで収集状況を確認できる。
- LiteLLM コンテナでは `HTTP_PROXY` / `HTTPS_PROXY` が `squid:3128` を向いているため、Docker 内サービス名で疎通させる相手は `NO_PROXY` / `no_proxy` に明示する必要がある。`langfuse-web` が未登録だと Langfuse SDK の `auth_check()` が Squid へ流れ、`ERR_ACCESS_DENIED` で失敗した。
- Langfuse v3 の self-host 構成では、受信イベントをまず S3/MinIO へ保存してから worker が取り込む。MinIO 利用時も `LANGFUSE_S3_EVENT_UPLOAD_REGION` が必要で、未設定だと Langfuse Web ログに `Failed to upload JSON to S3 ... Region is missing` が出て trace / observation 生成が止まる。今回の構成では `auto` を設定すると解消した。
- 2026-04-05 のメモリ再計測では、`clickhouse` は約 `856 MiB`、`langfuse-web` は約 `568 MiB`、`langfuse-worker` は約 `365 MiB` だった。`clickhouse` は `clickhouse-server` 単体で約 `1.10 GiB RSS` を保持しており、Langfuse 一式では最重量コンポーネントだった。
- ClickHouse 内部メトリクスでは `MemoryResident` が約 `1.11 GB`、`jemalloc.active` が約 `641 MB`、`MemoryTracking` が約 `300 MB` で、再起動直後の一時処理ではなく常駐キャッシュ込みのベースライン使用量が大きいことを確認した。
- メモリ上限を設ける場合は、まず Docker Compose 側で `mem_limit` を設定するより、ClickHouse 側設定として `max_server_memory_usage` と `max_memory_usage_for_all_queries` を XML で明示し、OS への余白を残しながら段階的に制限する方が安全である。PoC では 8.73 GiB 上限のホストに対して、まず `max_server_memory_usage` を `2G` 前後、`max_memory_usage_for_all_queries` を `1G` 前後から試すのが現実的な出発点となる。

## 残課題

- Langfuse の初期設定や API キー払い出しは別途確認が必要である。
- LiteLLM から Langfuse へ送られた trace を Public API で取得する追加手順は実行したが、Langfuse API キー不整合により `401 Invalid credentials` で失敗した。Langfuse 側で有効な project API key を払い出し、LiteLLM `.env` の `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` を更新したうえで再検証が必要である。
- 監視データ保持期間やバックアップ方針は本手順確認の対象外とする。