# I-01-09_22-denodoのDocker作成起動手順確認の検証

## 検証目的

本検証の主目的は、サブ課題 I-01-09「`22-denodo` の Docker 作成・起動手順確認」について、Denodo AI SDK 側の compose 資材を起動し、補助資材と合わせて利用前提を確認できるかを確認することである。

最終的には、I-01 の完了判定に必要な材料として、正常系、代表的な異常系、運用上の制約を明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| I-01 | I-01-09 | `infra/22-denodo/denodo-ai-sdk` 配下の compose 資材と補助ファイルで起動確認できること |

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../02_アーキテクチャ実現方式/技術課題と対応方針.md)
  - I-01-09 に対応し、`infra/22-denodo` の起動手順を確認する。
- [01_生成AI基盤インフラ構築手順.md](../04_検証準備/01_生成AI基盤インフラ構築手順.md)
  - Denodo AI SDK の準備手順を参照する。
- [../../infra/22-denodo/denodo-ai-sdk/docker-compose.yml](../../infra/22-denodo/denodo-ai-sdk/docker-compose.yml)
  - 実際の compose 定義を確認する。

## 検証で確認したいこと

### 1. 正常系

- compose 定義が解釈できること。
- Denodo AI SDK 関連コンテナが起動し、補助資材と整合していること。

### 2. 異常系

- 停止時に関連サービスが継続しないこと。
- 外部依存や設定不足をログから把握できること。

### 3. 運用系

- SDK 側と別資材の責務分離を説明できること。
- 更新時に compose 再適用と依存パッケージ確認が必要であることを説明できること。

## 前提条件

- Docker / Docker Compose が利用可能であること。
- Denodo 側の接続先や必要な認証情報が整理されていること。

## 検証手順

### 1. 事前準備

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/22-denodo/denodo-ai-sdk"
docker compose config -q
```

### 2. 正常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/22-denodo/denodo-ai-sdk"
docker compose up -d
docker compose ps
docker compose logs --tail=50
```

期待結果:

- `docker compose config -q` が成功する。
- 対象サービスが running で表示される。
- 起動失敗を示す致命的エラーがログに出ていない。

### 3. 異常系確認

```bash
cd "$AI_PLATFORM_POC_ROOT/infra/22-denodo/denodo-ai-sdk"
docker compose stop
docker compose ps
docker compose start
```

期待結果:

- 停止中は running サービスが存在しないことを確認できる。
- 再開後は正常系に戻せる。

## 判定基準

| 観点 | 判定基準 |
| --- | --- |
| 構造成立性 | Denodo AI SDK 側の compose 資材で環境を再現できる。 |
| 制御成立性 | 停止・再開時の状態変化を把握できる。 |
| 運用成立性 | SDK 側と補助資材の責務分離を説明できる。 |

## 検証結果記録欄

| 項目 | 結果 | 補足 |
| --- | --- | --- |
| 正常系 | 未記入 |  |
| 異常系 | 未記入 |  |
| 運用系 | 未記入 |  |

## 残課題

- Denodo Express 自体の配備手順は別資料と合わせて確認が必要である。
- OIDC や MCP 連携の詳細は Tool 層検証と合わせて扱う。