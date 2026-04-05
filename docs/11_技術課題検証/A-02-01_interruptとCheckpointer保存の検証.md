# A-02-01_interruptとCheckpointer保存の検証

## 検証目的

本検証の主目的は、サブ課題 A-02-01「`interrupt` と Checkpointer への保存」について、PoC 環境に存在する実装をもとに、承認待ちや長時間待機の直前で状態を保存し、同期処理を抜けられることを確認することである。

最終的には、A-02 の完了判定に必要な材料として、正常系、代表的な異常系、運用上の制約を明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| A-02 | A-02-01 | 承認待ちや入力待ちの直前で `interrupt` が発火し、Checkpointer に再開可能な状態を保存できるかを確認する。 |

必要に応じて、副次的に A-02-02、A-02-04、R-01-03 の前提整理にも利用する。

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../03_検証準備/技術課題と対応方針.md)
  - A-02-01 に対応し、「承認直前で `interrupt` を発火し、Checkpointer へ状態を保存する」論点を検証対象にする。
- [02_生成AIアプリケーション層の実現方式.md](../02_アーキテクチャ実現方式/02_生成AIアプリケーション層の実現方式.md)
  - 非同期 HITL を標準パターンとし、`interrupt`、Checkpointer、`thread_id` による再開を分離して扱う方針を確認する。
- [06_Application層実装方針.md](../03_検証準備/06_Application層実装方針.md)
  - LangGraph の Checkpointer を Application 層内部状態の保存先として使う方針と、SV 型の pause / resume 前提を確認する。
- [A-01-03_型間エスカレーションの検証.md](./A-01-03_型間エスカレーションの検証.md)
  - pause / resume の成立性が、型間エスカレーションの前提でもあることを参照する。

## 検証で確認したいこと

### 1. 正常系

- approval ノードなどで `interrupt` が発火した時点で、実行が `paused` になり同期処理を抜けられること。
- durable workflow 実行時に、LangGraph の Checkpointer が `thread_id` をキーとして状態を保存できること。
- 同じ `trace_id` / `thread_id` を使って再開したとき、保存済み状態から続行できること。

### 2. 異常系

- Checkpointer が使えない場合に、処理がクラッシュするのではなく durable 機能が無効化されること。
- `trace_id` が不正または欠落している場合に、再開 API が誤って別セッションを再開しないこと。
- SessionStore と Checkpointer の役割が混同されず、graph の内部状態保存を SessionStore だけに依存していないこと。

### 3. 運用系

- Checkpointer の保存先が固定的に解決でき、再起動後も同じ DB を参照できること。
- `trace_id` を再開キーとして BFF や API 層から扱えること。
- Checkpointer と UI 向け状態管理が別責務として説明できること。

## 対象構成

| 論点 | 主な実装候補 | 現状評価 |
| --- | --- | --- |
| Workflow の `interrupt` 発火 | `${HOME}/source/repos/ai-chat-util/app/src/ai_chat_util/workflow/workflow/langgraph_builder.py` | 実装あり |
| durable workflow 実行 | `${HOME}/source/repos/ai-chat-util/app/src/ai_chat_util/workflow/workflow/runner.py`、`${HOME}/source/repos/ai-chat-util/app/src/ai_chat_util/core/app.py` | 実装あり |
| SQLite Checkpointer 作成 | `${HOME}/source/repos/ai-chat-util/app/src/ai_chat_util/base/agent/agent_client_util.py` | 実装あり |
| Workflow の再開メタ情報保存 | `${HOME}/source/repos/ai-chat-util/app/src/ai_chat_util/workflow/session_store.py` | 実装あり |

補足:

- SessionStore は workflow の phase や prepared markdown などの補助情報を保存する。
- graph の内部状態そのものは LangGraph Checkpointer が保持するため、A-02-01 の主対象は SQLite Checkpointer 側である。

## 現時点の実装確認結果

### 1. `interrupt` の発火地点

- approval ノードでは `langgraph.types.interrupt` を呼び出し、承認対象ツール、プロンプト、ノード ID などを payload として返している。
- `WorkflowRunner.run()` は `__interrupt__` を検知すると `WorkflowPauseResult` を返し、同期実行を継続せず `paused` として処理を抜ける。

### 2. Checkpointer の保存先と有効化

- durable workflow 実行では `_create_workflow_checkpointer()` を経由して SQLite Checkpointer を生成する。
- 保存先は `(<working_directory または config 配置ディレクトリ>)/.ai_chat_util/langgraph_checkpoints.sqlite` であり、runtime config から安定して解決される。
- `AsyncSqliteSaver` が利用できない場合は warning を出し、durable 機能を無理に継続せず checkpoint 無効化へフォールバックする。

### 3. 再開処理

- durable workflow は `thread_id` として `trace_id` を利用し、同じキーで resume できる。
- `resume_durable_workflow()` は SessionStore から phase を読み、plan approval 再開か graph 再開かを分岐する。
- graph の内部状態は Checkpointer 側にあるため、resume 時は同じ `thread_id` を指定して LangGraph 側の保存状態を読み戻す。

### 4. SessionStore と Checkpointer の責務分離

- SessionStore は `workflow_sessions/<trace_id>.json` に phase、workflow ファイルパス、prepared markdown などを保持する。
- Checkpointer は LangGraph の node 実行状態や resume に必要な内部状態を SQLite に保持する。
- このため、A-02-01 の成立には SessionStore だけでは不十分であり、Checkpointer の存在が前提であることを確認できる。

## A-02-01 としての暫定判定

| 観点 | 現状評価 |
| --- | --- |
| `interrupt` 発火 | 成立している |
| Checkpointer 保存 | WF 型 durable workflow で成立している |
| 同一 `thread_id` / `trace_id` での再開 | 成立している |
| Application 層全体への横展開 | 追加検証余地あり |

したがって、A-02-01 は「WF 型 durable workflow を中心に、`interrupt` と Checkpointer への保存は成立している」と判断できる。一方で、SV 型全体や外部 BFF / イベント連携を含めた end-to-end の検証は今後の課題として残る。

## 前提条件

- `${HOME}/source/repos/ai-chat-util/app` の依存が導入済みであること。
- `langgraph-checkpoint-sqlite` と `aiosqlite` を含む workflow 実行依存が利用可能であること。
- WF 型は LangGraph workflow を使う前提とする。

## 検証手順

### 1. 事前準備

```bash
cd ${HOME}/source/repos/ai-chat-util/app
uv sync
```

### 2. workflow interrupt / resume の単体テスト

```bash
cd ${HOME}/source/repos/ai-chat-util/app
uv run pytest src/ai_chat_util/workflow/_test_/test_langgraph_workflow.py -q
```

期待結果:

- approval ノードで `WorkflowPauseResult` が返る。
- `InMemorySaver` を使った pause / resume が成功する。
- plan approval と graph resume の両方がテストで確認できる。

### 3. Checkpointer 実装の確認

```bash
cd ${HOME}/source/repos/ai-chat-util
grep -RIn "langgraph_checkpoints.sqlite\|AsyncSqliteSaver\|resume_durable_workflow\|WorkflowSessionStore" app/src README_FOR_EXPERTS.md
```

期待結果:

- SQLite Checkpointer の既定保存先が確認できる。
- durable workflow の resume API と SessionStore の役割が確認できる。

## 判定基準

| 観点 | 判定基準 |
| --- | --- |
| 構造成立性 | `interrupt`、Checkpointer、`thread_id` / `trace_id` による再開経路が実装として存在する。 |
| 制御成立性 | approval 待ちの直前で `paused` を返し、再入力時に同一状態から再開できる。 |
| 運用成立性 | 保存先、再開キー、SessionStore との責務分離を説明できる。 |

## 検証結果記録欄

### 2026-04-05 実施結果

実行コマンド:

```bash
cd ${HOME}/source/repos/ai-chat-util/app
uv run pytest src/ai_chat_util/workflow/_test_/test_langgraph_workflow.py -q
```

実行結果:

- `9 passed in 5.78s`
- 確認できた観点は次のとおり。
  - approval ノードで `interrupt` により pause できること。
  - `InMemorySaver` を使った Checkpointer 付き pause / resume が成功すること。
  - `WorkflowChatClient` が同一 trace_id で approval 後に再開できること。
  - durable workflow 実装が SQLite Checkpointer を使う構造であること。

補足:

- 今回の再検証では、主に WF 型 durable workflow を対象に確認した。
- SV 型全体の長時間待機や外部通知まで含めた end-to-end 検証は、本サブ課題では扱っていない。

| 項目 | 結果 | 補足 |
| --- | --- | --- |
| `interrupt` 発火 | 確認済み | approval ノードで `interrupt()` を呼び、`paused` に遷移する。 |
| Checkpointer 保存 | 確認済み | durable workflow は LangGraph Checkpointer を使う。 |
| 同一 trace_id での再開 | 確認済み | `thread_id` として trace_id を使って再開できる。 |
| SessionStore との責務分離 | 確認済み | 補助メタ情報は SessionStore、内部状態は Checkpointer が保持する。 |
| Application 層全体への横展開 | 未確認 | SV 型全体や外部非同期連携を含む検証は別途必要。 |

## 残課題

- SV 型全体で、`interrupt` と Checkpointer 保存がどこまで同じ設計で成立しているかを追加検証する必要がある。
- A-02-02 として、Resume API / `thread_id` 契約を end-to-end で確認する必要がある。
- A-02-03 として、UI 状態管理 DB と Checkpointer の責務分離を別文書で明確化する必要がある。