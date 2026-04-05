# I-01-10_91-zitadelのDocker作成起動手順確認の検証

## 検証目的

本検証の主目的は、サブ課題 I-01-10「`91-zitadel` の Docker 作成・起動手順確認」について、Zitadel を IdP として起動し、管理 UI へ到達できるか確認することである。

最終的には、I-01 の完了判定に必要な材料として、正常系、代表的な異常系、運用上の制約を明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| I-01 | I-01-10 | 共有 PostgreSQL を前提に Zitadel コンテナを起動し、管理 UI へアクセスできること |

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../02_アーキテクチャ実現方式/技術課題と対応方針.md)
  - I-01-10 に対応し、`infra/91-zitadel` の起動手順を確認する。
- [01_生成AI基盤インフラ構築手順.md](../04_検証準備/01_生成AI基盤インフラ構築手順.md)
  - Zitadel 構築とログイン確認の基準手順を参照する。
- [01_インフラ構築方針.md](../04_検証準備/01_インフラ構築方針.md)
  - 共有 PostgreSQL 利用方針を参照する。
- [../../infra/91-zitadel/docker-compose.yml](../../infra/91-zitadel/docker-compose.yml)
  - 実際の compose 定義を確認する。

## 検証で確認したいこと

### 1. 正常系

- compose 定義が解釈できること。
- Zitadel コンテナが起動し、管理 UI へアクセスできること。
- 共有 PostgreSQL 依存を手順として説明できること。

### 2. 異常系

- 停止時に管理 UI へ到達できないこと。
- 先行する PostgreSQL 未起動時に依存不足を認識できること。

### 3. 運用系

- 初期化後のログイン手順と管理者情報の確認方法を説明できること。
- DB 初期化や再起動順の扱いを説明できること。

## 前提条件

- I-01-01 と I-01-02 が成立していること。
- 初期管理者情報や設定ファイルが準備済みであること。

## 検証手順

### 1. 事前準備

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/91-zitadel"
docker compose config -q
```

### 2. 正常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/91-zitadel"
docker compose up -d
docker compose ps
curl -I http://localhost:8080/ui/console
```

期待結果:

- `docker compose config -q` が成功する。
- Zitadel サービスが running で表示される。
- `localhost:8080/ui/console` へアクセスできる。

### 3. 異常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/91-zitadel"
docker compose stop
curl -I http://localhost:8080/ui/console
docker compose start
```

期待結果:

- 停止中は `localhost:8080/ui/console` へのアクセスが失敗する。
- 再開後は正常系に戻せる。

## 判定基準

| 観点 | 判定基準 |
| --- | --- |
| 構造成立性 | Zitadel の compose 資材と共有 PostgreSQL 前提で環境を再現できる。 |
| 制御成立性 | 停止時に UI アクセスが失敗し、稼働状態を判別できる。 |
| 運用成立性 | 初期化、ログイン、起動順の説明が手順化されている。 |

## 検証結果記録欄

| 項目 | 結果 | 補足 |
| --- | --- | --- |
| 正常系 | 未記入 |  |
| 異常系 | 未記入 |  |
| 運用系 | 未記入 |  |

## 残課題

- クライアント登録や token 発行手順は別途認証検証で詳細化が必要である。
- 本番向け secret 管理やバックアップ方針は本手順確認の対象外とする。