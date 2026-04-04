# A-02-03_UI状態とAI内部状態分離の検証

## 検証目的

本検証の主目的は、サブ課題 A-02-03「UI状態と AI内部状態の分離」について、PoC 環境で責務分離がどこまで成立しているかを確認することである。

最終的には、A-02 の完了判定に必要な材料として、正常系、代表的な異常系、運用上の制約を明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| A-02 | A-02-03 | UI が参照する現在状態と、AI 実行再開に必要な内部状態を別責務で扱う設計・実装になっているかを確認する。 |

必要に応じて、副次的に R-01-02、R-01-03、O-01-02 の前提整理にも利用する。

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../02_アーキテクチャ実現方式/技術課題と対応方針.md)
  - A-02-03 に対応し、状態管理 DB と Checkpointer の責務が混ざらないことを確認対象にする。
- [01_生成AI基盤のコンポーネント配置と実装・運用原則.md](../02_アーキテクチャ実現方式/01_生成AI基盤のコンポーネント配置と実装・運用原則.md)
  - Event Bus、状態管理DB、Checkpointer の三者分離原則を確認する。
- [02_生成AIアプリケーション層の実現方式.md](../02_アーキテクチャ実現方式/02_生成AIアプリケーション層の実現方式.md)
  - UI 向け状態と AI 内部状態を単一ストアに混ぜない方針を確認する。
- [システム構成案とPoC環境準備.md](../03_PoC手順/システム構成案とPoC環境準備.md)
  - BFF が状態管理 DB を持ち、Application 層が Checkpointer を持つ構成案を確認する。
- [A-02-01_interruptとCheckpointer保存の検証.md](./A-02-01_interruptとCheckpointer保存の検証.md)
  - Checkpointer が AI 内部状態の保存先として成立していることを参照する。

## 検証で確認したいこと

### 1. 正常系

- Checkpointer が AI 実行再開用の内部状態を保存する責務として分離されていること。
- UI / BFF 側の現在状態は別ストアで扱う設計として明記されていること。
- workflow 実装でも、再開メタ情報と graph 内部状態が別保存になっていること。

### 2. 異常系

- Checkpointer を UI 向け状態の正本として扱う設計になっていないこと。
- UI 表示都合の状態更新を Application 層内部の Checkpointer へ直接混在させていないこと。
- SessionStore を Checkpointer の代替として誤用していないこと。

### 3. 運用系

- Event Bus、状態管理DB、Checkpointer の責務境界を運用資料で説明できること。
- BFF やフロントが参照する状態と、AI 再開用状態の変更ライフサイクルが異なることを説明できること。
- 現状 PoC で未実装の部分があれば、未確認として切り分けられていること。

## 対象構成

| 論点 | 主な実装・文書候補 | 現状評価 |
| --- | --- | --- |
| AI 内部状態の保存 | `/home/user/source/repos/ai-chat-util/app/src/ai_chat_util/base/agent/agent_client_util.py`、`/home/user/source/repos/ai-chat-util/app/src/ai_chat_util/workflow/workflow/runner.py` | 実装あり |
| workflow 再開メタ情報 | `/home/user/source/repos/ai-chat-util/app/src/ai_chat_util/workflow/session_store.py` | 実装あり |
| UI 状態管理 DB の責務 | `/home/user/source/repos/ai-platform-poc/docs/02_アーキテクチャ実現方式/01_生成AI基盤のコンポーネント配置と実装・運用原則.md`、`/home/user/source/repos/ai-platform-poc/docs/03_PoC手順/システム構成案とPoC環境準備.md` | 設計あり |
| BFF による状態管理 | `/home/user/source/repos/ai-platform-poc/docs/03_PoC手順/システム構成案とPoC環境準備.md` | 設計あり |

## 現時点の実装確認結果

### 1. Checkpointer の責務

- ai-chat-util では LangGraph Checkpointer を SQLite に保存し、`thread_id` ごとの graph 状態を再開に利用する。
- これは UI 表示用ではなく、Application 層内部の再開責務に限定されている。

### 2. SessionStore の責務

- `WorkflowSessionStore` は `phase`、workflow ファイルパス、prepared markdown、初回 message などの補助メタ情報を JSON に保存する。
- graph の内部状態そのものは保持しておらず、Checkpointer の代替ではない。
- したがって、内部状態と補助メタ情報の分離は実装上も成立している。

### 3. UI 状態管理 DB の責務

- アーキテクチャ文書では、UI 向け現在状態は状態管理 DB、AI 内部の再開用状態は Checkpointer、疎結合通知は Event Bus と明確に分離している。
- PoC 手順文書でも、BFF が Event Bus から状態を拾って Redis に append する構想が示されている。
- 一方で、今回確認した範囲では、状態管理 DB 自体の実装コードや end-to-end 検証文書は未整備である。

## A-02-03 としての暫定判定

| 観点 | 現状評価 |
| --- | --- |
| Checkpointer と SessionStore の責務分離 | 成立している |
| 文書上の UI 状態管理 DB 分離 | 成立している |
| UI 状態管理 DB の実装検証 | 未確認 |

したがって、A-02-03 は「設計原則と Application 層内部実装では責務分離が成立しているが、UI 状態管理 DB の PoC 実装検証は未了」と判断できる。

## 前提条件

- ai-chat-util の workflow 実装を参照できること。
- 本リポジトリのアーキテクチャ文書と PoC 手順書が最新化されていること。
- UI 状態管理 DB は現状設計文書ベースで評価すること。

## 検証手順

### 1. 文書上の責務分離確認

```bash
cd /home/user/source/repos/ai-platform-poc
grep -RIn "状態管理DB\|Checkpointer\|Event Bus" docs/02_アーキテクチャ実現方式 docs/03_PoC手順 | head -n 80
```

期待結果:

- 状態管理 DB、Checkpointer、Event Bus が別責務として記述されている。
- BFF が UI 向け状態を持つ設計が確認できる。

### 2. Application 層内部の分離確認

```bash
cd /home/user/source/repos/ai-chat-util
grep -RIn "WorkflowSessionStore\|langgraph_checkpoints.sqlite\|AsyncSqliteSaver" app/src README_FOR_EXPERTS.md
```

期待結果:

- SessionStore が補助メタ情報保存であることが確認できる。
- Checkpointer が graph 内部状態保存であることが確認できる。

## 判定基準

| 観点 | 判定基準 |
| --- | --- |
| 構造成立性 | 状態管理 DB、Checkpointer、Event Bus の責務分離が文書と実装の双方で説明できる。 |
| 制御成立性 | workflow 再開に必要な内部状態を UI 状態ストアへ依存させていない。 |
| 運用成立性 | 現状の未実装部分を含めて、責務境界と不足領域を明示できる。 |

## 検証結果記録欄

### 2026-04-05 実施結果

確認結果:

- ai-chat-util 側では、workflow 再開用の graph 状態が SQLite Checkpointer に保存されることを確認した。
- `WorkflowSessionStore` は JSON ベースの補助メタ情報保存であり、Checkpointer とは役割が異なることを確認した。
- 本リポジトリのアーキテクチャ文書では、UI 向け状態管理 DB と Checkpointer を明示的に分離していることを確認した。
- ただし、UI 状態管理 DB の PoC 実装そのものを検証するコードや検証結果は未整備である。

| 項目 | 結果 | 補足 |
| --- | --- | --- |
| Checkpointer の AI 内部状態責務 | 確認済み | workflow 再開用の内部状態を保持する。 |
| SessionStore の補助メタ情報責務 | 確認済み | phase、prepared markdown、message などに限定される。 |
| UI 状態管理 DB の分離方針 | 確認済み | 文書上は BFF / UI 向け状態として分離されている。 |
| UI 状態管理 DB の実装検証 | 未確認 | Redis などの実装確認は別課題で必要。 |

## 残課題

- R-01-02 として、状態管理 DB の UI 向け責務を具体実装で検証する必要がある。
- A-02-04 として、通知とタイムアウト時に UI 状態管理 DB と Checkpointer がどう連携するかを検証する必要がある。
- Event Bus から BFF 状態管理までの end-to-end 動線は、別文書で整理する必要がある。