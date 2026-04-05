# I-01-01_00-networkのDocker作成起動手順確認の検証

## 検証目的

本検証の主目的は、サブ課題 I-01-01「`00-network` の Docker 作成・起動手順確認」について、共通ネットワークと Squid を起動する手順が PoC 環境で成立するか確認することである。

最終的には、I-01 の完了判定に必要な材料として、正常系、代表的な異常系、運用上の制約を明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| I-01 | I-01-01 | `ai_platform_internal`、`ai_platform_egress`、`squid` を作成し、後続ミドルウェアの前提を提供できること |

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../03_検証準備/技術課題と対応方針.md)
  - I-01-01 に対応し、`infra/00-network` の compose 資材で共通ネットワークと egress proxy の起動手順を確認する。
- [01_生成AI基盤インフラ構築手順.md](../21_検証結果/01_生成AI基盤インフラ構築手順.md)
  - 共通ネットワーク構築の基準手順を参照する。
- [01_インフラ構築方針.md](../03_検証準備/01_インフラ構築方針.md)
  - internal ネットワークと egress 分離の方針を参照する。
- [../../infra/00-network/docker-compose.yml](../../infra/00-network/docker-compose.yml)
  - 実際の compose 定義を確認する。

## 検証で確認したいこと

### 1. 正常系

- compose 定義が解釈できること。
- `squid` コンテナが起動し、共通ネットワークが作成されること。
- proxy 経由の疎通確認ができること。

### 2. 異常系

- `squid` 停止時に proxy 経由通信が成立しないこと。
- 後続ミドルウェアの前提ネットワークとして機能停止を検知できること。

### 3. 運用系

- `squid.conf` の変更後に再起動で設定反映できること。
- ネットワーク再作成を伴う切替手順を説明できること。

## 前提条件

- Docker / Docker Compose が利用可能であること。
- リポジトリルートを `AI_PLATFORM_POC_ROOT` に設定済みであること。

## 検証手順

### 1. 事前準備

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/00-network"
docker compose config -q
```

### 2. 正常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/00-network"
docker compose up -d
docker compose ps
docker network inspect ai_platform_internal >/dev/null
docker network inspect ai_platform_egress >/dev/null
curl -I -x http://localhost:3128 https://opencode.ai
```

期待結果:

- `docker compose config -q` が成功する。
- `squid` が running で表示される。
- `ai_platform_internal` と `ai_platform_egress` が作成される。
- proxy 経由の HTTP(S) 到達確認が成功する。

### 3. 異常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/00-network"
docker compose stop squid
curl -I -x http://localhost:3128 https://opencode.ai
docker compose start squid
```

期待結果:

- `squid` 停止中は proxy 経由の通信が失敗する。
- `squid` 再開後は正常系に戻せる。

## 判定基準

| 観点 | 判定基準 |
| --- | --- |
| 構造成立性 | 共通ネットワークと Squid の compose 定義で環境を再現できる。 |
| 制御成立性 | `squid` 停止時に外向き proxy 経由通信が失敗する。 |
| 運用成立性 | 再起動、再作成、設定変更反映の手順を説明できる。 |

## 検証結果記録欄

| 項目 | 結果 | 補足 |
| --- | --- | --- |
| 正常系 | 未記入 |  |
| 異常系 | 未記入 |  |
| 運用系 | 未記入 |  |

## 残課題

- `squid.conf` の allowlist 運用の妥当性確認は別途必要である。
- 後続ミドルウェア側の proxy 環境変数注入状況は個別サブ課題で確認する。