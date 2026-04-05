# A-04-02_WF型Dify実装の検証

## 検証目的

本検証の主目的は、サブ課題 A-04-02「WF型エージェントの実装検証（Dify）」について、PoC 環境で成立性を確認することである。

最終的には、A-04 の完了判定に必要な材料として、Dify を WF 型の実装基盤として採用できるか、定型フロー、入力 UI、通知、人間入力を含む運用がどこまで成立するかを明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| A-04 | A-04-02 | Dify の workflow 機能で、定型フロー、入力 UI、通知、人間入力を含む WF 型運用が成立するかを確認する。 |

必要に応じて、副次的に A-02-04、I-01-08 の前提整理にも利用する。

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../03_検証準備/01_技術課題と対応方針.md)
  - A-04-02 に対応し、Dify を WF 型の実装基盤として採用できるかを確認する。
- [Application層の実装方針](../03_検証準備/12_Application層実装方針.md)
  - WF 型 / SV 型 / 自律型の分担と、クライアントからの入口構成を参照する。
- [生成AIアプリケーション層の実現方式](../02_アーキテクチャ実現方式/02_生成AIアプリケーション層の実現方式.md)
  - GUI ベースの協業や運用可視化を重視する場合に Dify を優先する整理を参照する。
- [修正版_技術メモ_ワークフローの状態管理と非同期HITLについて.md](../98_検討資料/修正版_技術メモ_ワークフローの状態管理と非同期HITLについて.md)
  - Dify の Human Input を用いた非同期 HITL 前提を参照する。
- [I-01-08_22-difyのDocker作成起動手順確認の検証.md](./I-01-08_22-difyのDocker作成起動手順確認の検証.md)
  - Dify 基盤の起動確認結果を前提とする。

## 検証で確認したいこと

### 1. 正常系

- Dify の workflow 機能で定型フローを実装できること。
- Human Input、Webhook、通知などの製品機能で WF 型の運用を支えられること。
- Dify を API または運用 UI の入口として利用できること。

### 2. 異常系

- Dify に閉じにくい複雑な状態管理を無理に持ち込まず、SV 型へ委譲すべき境界を説明できること。
- Human Input や workflow 定義の不足時に、運用が破綻する箇所を明示できること。
- Dify だけで cross-type 制御を完結できると誤認しないこと。

### 3. 運用系

- 運用 UI、入力画面、通知、履歴管理を標準機能として使えること。
- workflow 更新時の差分管理と変更反映の流れを整理できること。
- Dify と LangGraph / ai-chat-util の責務境界を明文化できること。

## 対象構成

| 観点 | 主な既存実装 / 入口 | 備考 |
| --- | --- | --- |
| インフラ | `${HOME}/source/repos/ai-platform-poc/infra/22-dify` | Dify compose 資材 |
| 起動確認 | [I-01-08_22-difyのDocker作成起動手順確認の検証.md](./I-01-08_22-difyのDocker作成起動手順確認の検証.md) | Dify 基盤の前提 |
| 運用前提 | `docs/98_検討資料/修正版_技術メモ_ワークフローの状態管理と非同期HITLについて.md` | Human Input 前提 |
| ai-chat-util との関係 | `${HOME}/source/repos/ai-chat-util/README_FOR_EXPERTS.md` の Cross-type Coordinator / workflow 記述 | Dify は主に疎結合連携先 |

## 既存実装と入口の対応づけ

1. Dify 側の主入口

- Dify Web UI による workflow 設計・実行
- Dify API による workflow 実行

2. ai-chat-util 側との接続候補

- `coordinated_chat` が WF 型を選んだ後、将来的に Dify workflow へ委譲する構成余地がある。
- ただし現時点の ai-chat-util 既定 WF 型は LangGraph ベースであり、Dify は別実装基盤として扱う。

3. 本リポジトリ側の既存根拠

- `infra/22-dify` に基盤資材がある。
- I-01-08 で起動確認観点が整理されている。
- 98_検討資料で Human Input による非同期 HITL の適性が整理されている。

## 前提条件

- Dify 基盤が起動済みであること。
- workflow 設計用の Dify 管理 UI にアクセスできること。
- 必要に応じて LiteLLM / Guardrails 接続先が利用可能であること。

## 検証手順

### 1. 事前準備

```bash
cd ${HOME}/source/repos/ai-platform-poc/infra/22-dify
docker compose up -d
```

### 2. 正常系確認

```bash
cd ${HOME}/source/repos/ai-platform-poc/infra/22-dify
docker compose ps
```

期待結果:

- Dify の関連コンテナが起動している。
- Dify UI から workflow を作成・実行できる前提が整う。

### 3. WF 型確認

期待結果:

- workflow ノードで定型フローを表現できる。
- Human Input ノードを使って人間入力待ちへ遷移できる。
- Dify 単体で UI / 通知を伴う WF 型運用を構成できる。

### 4. 異常系確認

期待結果:

- 複雑な状態機械や cross-type 切替が必要な場合、Dify 単独では限界があることを確認できる。
- その場合は SV 型または LangGraph 側へ責務を逃がす判断ができる。

## 判定基準

| 観点 | 判定基準 |
| --- | --- |
| 構造成立性 | Dify workflow を WF 型の独立実装基盤として位置付けられる。 |
| 制御成立性 | 定型フロー、Human Input、通知、運用 UI を使った WF 型の基本制御が成立する。 |
| 運用成立性 | workflow 更新、入力 UI、通知運用を製品機能中心に整理できる。 |

## 検証結果記録欄

| 項目 | 結果 | 補足 |
| --- | --- | --- |
| 正常系 | 未記入 |  |
| 異常系 | 未記入 |  |
| 運用系 | 未記入 |  |

## 残課題

- Dify と ai-chat-util / LangGraph の責務境界をどこまで固定するか、PoC での整理が必要である。
- Dify workflow を Coordinator の WF 型選択先としてどう接続するかは未整理である。
- 本文書では基盤成立性を扱い、個別業務ワークフローの設計標準までは扱わない。