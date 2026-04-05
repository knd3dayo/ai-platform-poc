# I-01-05_21-sambaのDocker作成起動手順確認の検証

## 検証目的

本検証の主目的は、サブ課題 I-01-05「`21-samba` の Docker 作成・起動手順確認」について、自律型エージェントのワークスペース用途を想定した Samba コンテナを起動できるか確認することである。

最終的には、I-01 の完了判定に必要な材料として、正常系、代表的な異常系、運用上の制約を明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| I-01 | I-01-05 | Samba コンテナを起動し、共有設定を読み込んだ状態で稼働させられること |

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../03_検証準備/技術課題と対応方針.md)
  - I-01-05 に対応し、`infra/21-samba` の起動手順を確認する。
- [../../infra/21-samba/docker-compose.yml](../../infra/21-samba/docker-compose.yml)
  - 実際の compose 定義を確認する。

## 検証で確認したいこと

### 1. 正常系

- compose 定義が解釈できること。
- Samba コンテナが起動し、共有設定を読み込めること。

### 2. 異常系

- 停止時に共有サービスが継続しないこと。
- ボリュームや設定不足がログから判別できること。

### 3. 運用系

- 共有ディレクトリ更新時の再起動要否を説明できること。
- 権限設定の調整ポイントを説明できること。

## 前提条件

- Docker / Docker Compose が利用可能であること。
- 共有対象ディレクトリと設定ファイルが配置済みであること。

## 検証手順

### 1. 事前準備

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/21-samba"
docker compose config -q
```

### 2. 正常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/21-samba"
docker compose up -d
docker compose ps
docker compose logs --tail=50
```

期待結果:

- `docker compose config -q` が成功する。
- Samba サービスが running で表示される。
- 共有設定読み込み失敗を示す致命的エラーがログに出ていない。

### 3. 異常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/21-samba"
docker compose stop
docker compose ps
docker compose start
```

期待結果:

- 停止中は running サービスが存在しないことを確認できる。
- 再開で正常系に戻せる。

## 判定基準

| 観点 | 判定基準 |
| --- | --- |
| 構造成立性 | Samba の compose 資材で共有サービスを再現できる。 |
| 制御成立性 | 停止・再開時の稼働状態を把握できる。 |
| 運用成立性 | 共有設定と権限調整の手順を説明できる。 |

## 検証結果記録欄

| 項目 | 結果 | 補足 |
| --- | --- | --- |
| 正常系 | OK | `docker compose config -q` は成功。`docker compose up -d` 後、`21-samba-samba-1` は `Up (healthy)` となり、ログ上も `[workspace]` セクション読込と `waiting for connections` を確認。 |
| 異常系 | OK | `docker compose stop` 後は `Exited (0)` となり、`docker compose start` 後は再度 `Up (healthy)` へ復帰。 |
| 運用系 | OK | `${HOME}/data/workspace` の事前作成が必要。`network_mode: host` で動作するため、共有定義変更時は compose 再起動前提で、ネットワーク境界の扱いは通常の `ai_platform_internal` 接続と異なる。 |

## 検証メモ

- 事前に `mkdir -p $HOME/data/workspace` を実施した。
- 初回 `docker compose up -d` ではイメージ取得に時間を要したが、再実行後に正常起動した。
- ログには `Failed to register my name ... on subnet 192.168.35.89`、`open_ep: SO_RCVBUFFORCE: Operation not permitted` などの警告が出たが、最終的にコンテナは `healthy` となり、`smbd` は `waiting for connections` 状態に入った。
- `docker inspect 21-samba-samba-1 --format '{{.HostConfig.NetworkMode}}'` の結果は `host` であり、compose 末尾の外部ネットワーク定義よりも `network_mode: host` が優先される構成であることを確認した。

## 残課題

- クライアント OS ごとのマウント確認は別途必要である。
- `network_mode: host` を前提にする妥当性と、PoC 全体の内部ネットワーク方針との整合は別途評価が必要である。
- アクセス制御ポリシーの詳細確認は本手順確認の対象外とする。