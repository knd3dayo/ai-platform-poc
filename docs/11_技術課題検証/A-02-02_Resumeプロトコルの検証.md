# A-02-02_Resumeプロトコルの検証

## 検証目的

本検証の主目的は、サブ課題 A-02-02「Resume プロトコル」について、PoC 環境で pause 後の再開契約が成立しているかを確認することである。

最終的には、A-02 の完了判定に必要な材料として、正常系、代表的な異常系、運用上の制約を明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| A-02 | A-02-02 | `trace_id` / `thread_id` をキーに、中断地点から誤りなく再開できる契約が API、ライブラリ、workflow 実装で成立しているかを確認する。 |

必要に応じて、副次的に A-02-01、O-02-04、R-01-03 の前提整理にも利用する。

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../02_アーキテクチャ実現方式/技術課題と対応方針.md)
  - A-02-02 に対応し、`thread_id` などのキーによる中断地点からの再開を確認対象にする。
- [02_生成AIアプリケーション層の実現方式.md](../02_アーキテクチャ実現方式/02_生成AIアプリケーション層の実現方式.md)
  - 非同期 HITL で `thread_id` をキーに再開する設計方針を確認する。
- [01_生成AI基盤のコンポーネント配置と実装・運用原則.md](../02_アーキテクチャ実現方式/01_生成AI基盤のコンポーネント配置と実装・運用原則.md)
  - `trace_id` を横断キーとして扱う原則と、BFF での最終確定方針を確認する。
- [A-02-01_interruptとCheckpointer保存の検証.md](./A-02-01_interruptとCheckpointer保存の検証.md)
  - Resume プロトコルの前提になる pause と Checkpointer 保存の成立性を参照する。

## 検証で確認したいこと

### 1. 正常系

- pause 応答時に再開キーとして使う `trace_id` が返ること。
- workflow durable 実行時に同じ `trace_id` を `thread_id` として使い、中断地点から再開できること。
- API / ライブラリ利用時に、同じ `trace_id` を付けた再送で resume できること。

### 2. 異常系

- `trace_id` 未指定時に、resume API が曖昧な再開を許容しないこと。
- 存在しない `trace_id` では、誤って新規実行や別セッション再開に流れないこと。
- 不正な `trace_id` 形式が入力モデルで拒否されること。

### 3. 運用系

- `trace_id` が API、ヘッダー、内部 workflow の間で一貫した相関キーとして扱えること。
- CLI と API で再開能力に差がある場合、その制約を明示できること。
- プロセスを跨ぐ再開時に、同一 DB と同一 `trace_id` を使う前提が説明できること。

## 対象構成

| 論点 | 主な実装候補 | 現状評価 |
| --- | --- | --- |
| `trace_id` 正規化 | `/home/user/source/repos/ai-chat-util/app/src/ai_chat_util/common/model/ai_chatl_util_models.py` | 実装あり |
| workflow trace 解決 | `/home/user/source/repos/ai-chat-util/app/src/ai_chat_util/core/app.py` | 実装あり |
| workflow resume 処理 | `/home/user/source/repos/ai-chat-util/app/src/ai_chat_util/core/app.py`、`/home/user/source/repos/ai-chat-util/app/src/ai_chat_util/workflow/chat_client.py` | 実装あり |
| API 契約の説明 | `/home/user/source/repos/ai-chat-util/app/src/ai_chat_util/api/api_server.py`、`/home/user/source/repos/ai-chat-util/README_FOR_EXPERTS.md` | 実装あり |

## 現時点の実装確認結果

### 1. 再開キーの定義

- `ChatRequest.trace_id` は W3C trace-id 部分の 32 桁 hex として定義されている。
- `traceparent` 全体が渡された場合でも trace-id 部分へ正規化される。
- 全ゼロの `trace_id` は不正として拒否される。

### 2. workflow durable の resume 契約

- `run_mermaid_workflow_from_file()` と `run_durable_workflow_from_file()` は、受け取った `trace_id` を workflow の `thread_id` として利用する。
- `resume_durable_workflow()` は `trace_id` 必須であり、未指定時は例外になる。
- `WorkflowSessionStore` にセッションが存在しない `trace_id` についても例外になり、曖昧な再開を避けている。

### 3. API / ライブラリでの再開方法

- API / ライブラリ利用時は、pause 時に `status="paused"` と `trace_id` が返る。
- 再開は同じ `trace_id` を付けた次の `ChatRequest` を送るだけで成立する。
- README_FOR_EXPERTS でも、プロセスを跨ぐ再開は API / ライブラリ利用で `ChatRequest.trace_id` を指定する前提が明示されている。

### 4. CLI 制約

- CLI の `agent_chat` は同一プロセス内で pause / resume を処理する。
- プロセスを跨いだ再開のための `trace_id` 指定オプションは現状ない。
- したがって、A-02-02 は API / ライブラリ契約では成立しているが、CLI 単体の再開契約は限定的である。

## A-02-02 としての暫定判定

| 観点 | 現状評価 |
| --- | --- |
| `trace_id` 正規化と検証 | 成立している |
| workflow durable の resume | 成立している |
| API / ライブラリでの resume 契約 | 成立している |
| CLI 横断再開 | 制約あり |

したがって、A-02-02 は「API / ライブラリ利用を前提とした Resume プロトコルは成立している」と判断できる。一方で、CLI 単体でのプロセス跨ぎ再開は対象外であり、運用制約として明示が必要である。

## 前提条件

- `/home/user/source/repos/ai-chat-util/app` の依存が導入済みであること。
- workflow durable 実行と session store が利用可能であること。
- pause / resume は API またはライブラリ利用を主対象とすること。

## 検証手順

### 1. 事前準備

```bash
cd /home/user/source/repos/ai-chat-util/app
uv sync
```

### 2. focused workflow resume テスト

```bash
cd /home/user/source/repos/ai-chat-util/app
uv run pytest src/ai_chat_util/workflow/_test_/test_langgraph_workflow.py -k "trace_id or plan or pause or resume" -q
```

期待結果:

- plan approval 後に同一 trace_id で再開できる。
- approval pause 後に同一 thread_id で再開できる。

### 3. resume 契約の実装確認

```bash
cd /home/user/source/repos/ai-chat-util
grep -RIn "resume_durable_workflow\|trace_id\|thread_id\|status=\"paused\"" app/src README_FOR_EXPERTS.md
```

期待結果:

- `trace_id` の正規化と説明が確認できる。
- pause 応答に `trace_id` が含まれる説明が確認できる。
- `resume_durable_workflow()` の入力契約が確認できる。

## 判定基準

| 観点 | 判定基準 |
| --- | --- |
| 構造成立性 | `trace_id` / `thread_id` による再開経路が API、モデル、workflow 実装に存在する。 |
| 制御成立性 | pause 後に同じ相関キーで再送すると、誤った新規実行ではなく resume になる。 |
| 運用成立性 | API、CLI、ライブラリの差分と制約を説明できる。 |

## 検証結果記録欄

### 2026-04-05 実施結果

実行コマンド:

```bash
cd /home/user/source/repos/ai-chat-util/app
uv run pytest src/ai_chat_util/workflow/_test_/test_langgraph_workflow.py -k "trace_id or plan or pause or resume" -q
```

実行結果:

- `3 passed, 6 deselected in 6.19s`
- 確認できた観点は次のとおり。
  - plan mode の承認後に同一 trace_id で再開できること。
  - approval pause 後に同一 thread_id で実行継続できること。
  - `WorkflowChatClient` が session store を使って phase を判定し、同一 trace_id で plan / graph の両系統を再開できること。

| 項目 | 結果 | 補足 |
| --- | --- | --- |
| `trace_id` 正規化 | 確認済み | 32 桁 hex へ正規化し、全ゼロは拒否する。 |
| pause 応答での再開キー返却 | 確認済み | API / ライブラリ利用時は `paused` と `trace_id` を返す。 |
| workflow durable resume | 確認済み | `resume_durable_workflow()` が同一 `trace_id` を要求する。 |
| 不正・欠落 trace_id の拒否 | 確認済み | 欠落時と未保存セッション時は例外になる。 |
| CLI 横断再開 | 未確認 | CLI は同一プロセス内対話に限定される。 |

## 残課題

- O-02-04 として、BFF から見た再開キー利用の end-to-end 検証を追加する必要がある。
- A-02-04 として、通知、タイムアウト、再送、キャンセルと Resume プロトコルの結合を確認する必要がある。
- CLI にも横断的 resume 契約を持たせるかは、別途要件整理が必要である。