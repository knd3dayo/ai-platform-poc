# I-01-02_01-postgresqlのDocker作成起動手順確認の検証

## 検証目的

本検証の主目的は、サブ課題 I-01-02「`01-postgresql` の Docker 作成・起動手順確認」について、共有 PostgreSQL を PoC 基盤の共通 DB として起動できるか確認することである。

最終的には、I-01 の完了判定に必要な材料として、正常系、代表的な異常系、運用上の制約を明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| I-01 | I-01-02 | 共有 PostgreSQL コンテナを起動し、後続コンポーネントの接続先として利用できること |

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../02_アーキテクチャ実現方式/技術課題と対応方針.md)
  - I-01-02 に対応し、`infra/01-postgresql` の compose 資材による共通 DB 起動手順を確認する。
- [01_生成AI基盤インフラ構築手順.md](../04_検証準備/01_生成AI基盤インフラ構築手順.md)
  - 共通 PostgreSQL 構築手順の基準を参照する。
- [01_インフラ構築方針.md](../04_検証準備/01_インフラ構築方針.md)
  - 共有 PostgreSQL の位置づけを参照する。
- [../../infra/01-postgresql/docker-compose.yml](../../infra/01-postgresql/docker-compose.yml)
  - 実際の compose 定義を確認する。

## 検証で確認したいこと

### 1. 正常系

- compose 定義が解釈できること。
- PostgreSQL コンテナが起動し、`pg_isready` で応答すること。
- 他コンポーネントが共通 DB として利用できる前提が成立すること。

### 2. 異常系

- サービス停止時に DB 接続確認が失敗すること。
- 共通ネットワーク未作成時に依存条件不足を認識できること。

### 3. 運用系

- データ永続化ディレクトリの扱いを説明できること。
- 再起動後も接続先が不変であることを確認できること。

## 前提条件

- I-01-01 の前提となる共通ネットワークが作成済みであること。
- Docker / Docker Compose が利用可能であること。

## 検証手順

### 1. 事前準備

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/01-postgresql"
docker compose config -q
```

### 2. 正常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/01-postgresql"
docker compose up -d
docker compose ps
docker exec postgres pg_isready -U postgres
```

期待結果:

- `docker compose config -q` が成功する。
- `postgres` が running で表示される。
- `pg_isready` が accepting connections を返す。

### 3. 異常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/01-postgresql"
docker compose stop
docker exec postgres pg_isready -U postgres
docker compose start
```

期待結果:

- 停止中は `docker exec postgres ...` が失敗する。
- 再開後は正常系の確認に戻せる。

## 判定基準

| 観点 | 判定基準 |
| --- | --- |
| 構造成立性 | 共有 PostgreSQL の compose 定義で環境を再現できる。 |
| 制御成立性 | 停止時に接続確認が失敗し、稼働状態を判別できる。 |
| 運用成立性 | 再起動と永続化ディレクトリの扱いを説明できる。 |

## 検証結果記録欄

| 項目 | 結果 | 補足 |
| --- | --- | --- |
| 正常系 | 未記入 |  |
| 異常系 | 未記入 |  |
| 運用系 | 未記入 |  |

## 残課題

- DB 作成スクリプトの標準化は利用コンポーネントごとに別途確認が必要である。
- バックアップ / リストア方針はこの検証の対象外とする。