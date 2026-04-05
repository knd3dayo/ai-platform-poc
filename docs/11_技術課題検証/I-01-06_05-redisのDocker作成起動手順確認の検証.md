# I-01-06_05-redisのDocker作成起動手順確認の検証

## 検証目的

本検証の主目的は、サブ課題 I-01-06「`05-redis` の Docker 作成・起動手順確認」について、Redis を Event Bus / 状態管理用途の共通ミドルウェアとして起動できるか確認することである。

最終的には、I-01 の完了判定に必要な材料として、正常系、代表的な異常系、運用上の制約を明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| I-01 | I-01-06 | Redis コンテナを起動し、疎通確認コマンドで応答を得られること |

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../03_検証準備/技術課題と対応方針.md)
  - I-01-06 に対応し、`infra/05-redis` の起動手順を確認する。
- [01_生成AI基盤インフラ構築手順.md](../21_検証結果/01_生成AI基盤インフラ構築手順.md)
  - Redis 構築手順の基準を参照する。
- [../../infra/05-redis/docker-compose.yml](../../infra/05-redis/docker-compose.yml)
  - 実際の compose 定義を確認する。

## 検証で確認したいこと

### 1. 正常系

- compose 定義が解釈できること。
- Redis コンテナが起動し、`PING` に応答すること。

### 2. 異常系

- 停止時に `PING` 応答が得られないこと。
- 起動状態を `docker compose ps` で識別できること。

### 3. 運用系

- データ永続化や再起動時の扱いを説明できること。
- Event Bus / 状態管理の用途差を手順書から読み取れること。

## 前提条件

- I-01-01 の共通ネットワークが作成済みであること。
- Docker / Docker Compose が利用可能であること。

## 検証手順

### 1. 事前準備

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/05-redis"
docker compose config -q
```

### 2. 正常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/05-redis"
docker compose up -d
docker compose ps
docker compose exec redis redis-cli ping
```

期待結果:

- `docker compose config -q` が成功する。
- Redis サービスが running で表示される。
- `redis-cli ping` が `PONG` を返す。

### 3. 異常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/05-redis"
docker compose stop
docker compose exec redis redis-cli ping
docker compose start
```

期待結果:

- 停止中は `docker compose exec redis redis-cli ping` が失敗する。
- 再開後は正常系に戻せる。

## 判定基準

| 観点 | 判定基準 |
| --- | --- |
| 構造成立性 | Redis の compose 資材で環境を再現できる。 |
| 制御成立性 | 停止時に疎通確認が失敗し、稼働状態を判別できる。 |
| 運用成立性 | 再起動と永続化の扱いを説明できる。 |

## 検証結果記録欄

| 項目 | 結果 | 補足 |
| --- | --- | --- |
| 正常系 | 未記入 |  |
| 異常系 | 未記入 |  |
| 運用系 | 未記入 |  |

## 残課題

- Streams や RedisInsight の利用確認は別途必要である。
- メモリ制限や永続化ポリシーの評価は本手順確認の対象外とする。