# I-01-08_21-difyのDocker作成起動手順確認の検証

## 検証目的

本検証の主目的は、サブ課題 I-01-08「`21-dify` の Docker 作成・起動手順確認」について、Dify を WF 型アプリケーション実行環境として起動できるか確認することである。

最終的には、I-01 の完了判定に必要な材料として、正常系、代表的な異常系、運用上の制約を明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| I-01 | I-01-08 | Dify の compose 資材、`.env`、sandbox 設定を用いて起動し、UI へ到達できること |

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../02_アーキテクチャ実現方式/技術課題と対応方針.md)
  - I-01-08 に対応し、`infra/21-dify` の起動手順を確認する。
- [01_生成AI基盤インフラ構築手順.md](../04_検証準備/01_生成AI基盤インフラ構築手順.md)
  - Dify 構築手順の基準を参照する。
- [../../infra/21-dify/docker/docker-compose.yaml](../../infra/21-dify/docker/docker-compose.yaml)
  - 実際の compose 定義を確認する。
- [../../infra/21-dify/docker/.env.example](../../infra/21-dify/docker/.env.example)
  - 必要な環境変数の前提を確認する。

## 検証で確認したいこと

### 1. 正常系

- compose 定義が解釈できること。
- Dify 関連コンテナ群が起動し、UI へアクセスできること。
- 共通 PostgreSQL と LiteLLM 接続前提を手順から読み取れること。

### 2. 異常系

- 停止時に UI へ到達できないこと。
- `.env` や依存 DB 未設定時に問題箇所を特定できること。

### 3. 運用系

- `docker-template` との差分管理方法を説明できること。
- Dify 更新時の compose 再適用手順を説明できること。

## 前提条件

- I-01-01 と I-01-02 が成立していること。
- `infra/21-dify/docker` 配下に必要な `.env` と volume 設定が用意されていること。

## 検証手順

### 1. 事前準備

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/21-dify/docker"
docker compose -f docker-compose.yaml config -q
```

### 2. 正常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/21-dify/docker"
docker compose -f docker-compose.yaml up -d
docker compose -f docker-compose.yaml ps
curl -I http://localhost:8081
```

期待結果:

- `docker compose -f docker-compose.yaml config -q` が成功する。
- Dify 関連サービスが running で表示される。
- `localhost:8081` へアクセスできる。

### 3. 異常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/21-dify/docker"
docker compose -f docker-compose.yaml stop
curl -I http://localhost:8081
docker compose -f docker-compose.yaml start
```

期待結果:

- 停止中は `localhost:8081` へのアクセスが失敗する。
- 再開後は正常系に戻せる。

## 判定基準

| 観点 | 判定基準 |
| --- | --- |
| 構造成立性 | Dify の compose 資材と設定ファイルで環境を再現できる。 |
| 制御成立性 | 停止時に UI アクセスが失敗し、稼働状態を判別できる。 |
| 運用成立性 | `.env` 管理と再起動手順を説明できる。 |

## 検証結果記録欄

| 項目 | 結果 | 補足 |
| --- | --- | --- |
| 正常系 | 未記入 |  |
| 異常系 | 未記入 |  |
| 運用系 | 未記入 |  |

## 残課題

- Dify 初期セットアップと LiteLLM モデル登録は別途確認が必要である。
- SSRF proxy の allowlist 調整は別サブ課題で扱う。