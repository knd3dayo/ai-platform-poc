# I-01-07_11-langfuseのDocker作成起動手順確認の検証

## 検証目的

本検証の主目的は、サブ課題 I-01-07「`11-langfuse` の Docker 作成・起動手順確認」について、Langfuse を可観測性基盤として起動できるか確認することである。

最終的には、I-01 の完了判定に必要な材料として、正常系、代表的な異常系、運用上の制約を明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| I-01 | I-01-07 | Langfuse 関連コンテナ群を起動し、UI へアクセスできること |

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../03_検証準備/技術課題と対応方針.md)
  - I-01-07 に対応し、`infra/11-langfuse` の起動手順を確認する。
- [01_生成AI基盤インフラ構築手順.md](../21_検証結果/01_生成AI基盤インフラ構築手順.md)
  - Langfuse 構築手順の基準を参照する。
- [../../infra/11-langfuse/docker-compose.yml](../../infra/11-langfuse/docker-compose.yml)
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

## 前提条件

- I-01-01 の共通ネットワークが作成済みであること。
- `$HOME/data` 配下に必要なディレクトリを作成できること。

## 検証手順

### 1. 事前準備

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/11-langfuse"
docker compose config -q
mkdir -p "$HOME/data/ai-platform-poc/clickhouse/data" "$HOME/data/ai-platform-poc/clickhouse/logs"
mkdir -p "$HOME/data/ai-platform-poc/minio"
```

### 2. 正常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/11-langfuse"
docker compose up -d
docker compose ps
curl -I http://localhost:3000
```

期待結果:

- `docker compose config -q` が成功する。
- Langfuse 関連サービスが running で表示される。
- `localhost:3000` へアクセスできる。

### 3. 異常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/11-langfuse"
docker compose stop
curl -I http://localhost:3000
docker compose start
```

期待結果:

- 停止中は `localhost:3000` へのアクセスが失敗する。
- 再開後は正常系に戻せる。

## 判定基準

| 観点 | 判定基準 |
| --- | --- |
| 構造成立性 | Langfuse の compose 資材と永続ディレクトリ準備で環境を再現できる。 |
| 制御成立性 | 停止時に UI アクセスが失敗し、稼働状態を判別できる。 |
| 運用成立性 | 補助コンポーネントを含めた再起動手順を説明できる。 |

## 検証結果記録欄

| 項目 | 結果 | 補足 |
| --- | --- | --- |
| 正常系 | 未記入 |  |
| 異常系 | 未記入 |  |
| 運用系 | 未記入 |  |

## 残課題

- Langfuse の初期設定や API キー払い出しは別途確認が必要である。
- 監視データ保持期間やバックアップ方針は本手順確認の対象外とする。