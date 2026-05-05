# O-02-01_trace_id 採番とレイヤ横断伝播の検証

## 検証目的

本検証の主目的は、サブ課題 O-02-01「`trace_id` の入口採番」、O-02-02「レイヤ横断伝播」、O-02-04「再開・検索キーとしての利用」について、support-desk-agent の実装をもとに、入口での採番・全レイヤへの一貫伝播・再開キーとしての活用が成立することを確認することである。

最終的には、O-02 の完了判定に必要な材料として、正常系、代表的な異常系、運用上の制約を明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| O-02 | O-02-01 | 入口 API での `trace_id` / `case_id` 採番ロジック |
| O-02 | O-02-02 | CaseState 経由での `trace_id` / `thread_id` / `workflow_run_id` の一体管理 |
| O-02 | O-02-04 | `trace_id` を再開キーとした Checkpointer state 復元 |

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../03_検証準備/技術課題と対応方針.md)
  - O-02-01 〜 O-02-04 に対応し、trace_id の採番・伝播・再開キー利用を検証対象とする。
- [A-02-02_Resumeプロトコルの検証.md](./A-02-02_Resumeプロトコルの検証.md)
  - Resume 時の `thread_id` 利用は本サブ課題の O-02-04 と連携する。
- [R-01-03_Checkpointer再開責務の検証.md](./R-01-03_Checkpointer再開責務の検証.md)
  - Checkpointer の `thread_id` キーによる state 復元は本サブ課題の前提となる。

## 検証で確認したいこと

### 1. 正常系

- `CaseIdResolverService.resolve()` が `CASE-YYYYmmdd-HHMMSS-XXXX` 形式で `case_id` を採番できること。
- `CaseState._normalize_trace_identifiers()` が `trace_id` / `thread_id` / `workflow_run_id` を同一値に統一できること。
- レガシーな `session_id` が `SESSION-` プレフィックスを持つ場合、`TRACE-` プレフィックスへ正規化されること。
- `_load_state()` が `thread_id` (`= trace_id`) を Checkpointer キーとして正しく state を復元できること。

### 2. 異常系

- `trace_id` が欠落した状態で `_load_state()` を呼び出した場合、空の `CaseState` が返り別セッションを再開しないこと。
- `case_id` / `workspace_path` が未指定の場合、Checkpointer が `ValueError` を送出して不正なキーで保存しないこと。

### 3. 運用系

- `checkpoint_status()` で `trace_ids` を一覧確認でき、同一 `case_id` のセッション履歴を再開候補として取得できること。
- `case_id` に対応するワークスペースに `.support-ope-case-id` ファイルがあれば、プロンプトに明示がなくても同一 `case_id` を再利用できること。

## 対象構成

| 論点 | 実装箇所 | 現状評価 |
| --- | --- | --- |
| `case_id` / `trace_id` 採番 | `runtime/case_id_resolver.py` の `CaseIdResolverService` | 実装あり |
| trace 識別子の統一正規化 | `models/state.py` の `CaseState._normalize_trace_identifiers()` | 実装あり |
| trace_id を再開キーとした state 復元 | `runtime/abstract_service.py` の `_load_state()` / `checkpoint_status()` | 実装あり |

## 現時点の実装確認結果

### 1. case_id 採番

- `CaseIdResolverService.resolve()` は次の優先順で `case_id` を決定する。
  1. `explicit_case_id` が指定されていれば即時採用する。
  2. ワークスペースの `.support-ope-case-id` ファイルから読み込む。
  3. プロンプト本文から正規表現 3 パターンで抽出する。
  4. いずれも該当しない場合は `CASE-{YYYYmmdd}-{HHMMSS}-{UUID4[:4].upper()}` を生成する。
- `_generate_case_id()` は `datetime.now()` と `uuid4()` を組み合わせるため、衝突しない一意値を保証する。

### 2. trace 識別子の正規化

- `CaseState` の `model_validator(mode="before")` により、`trace_id` / `thread_id` / `workflow_run_id` は常に同一値へ統一される。
- レガシーな `session_id = "SESSION-xxx"` は `TRACE-xxx` へ自動変換される。
- `TRACE-` 以外のプレフィックスには `TRACE-` が付加され、プレフィックスなし文字列の不整合を防ぐ。

### 3. trace_id による再開キー利用

- `_load_state(case_id, trace_id, workspace_path)` は `SqliteSaver` から `thread_id = trace_id` で state を読み戻す。
- `checkpoint_status()` は Checkpointer DB の `checkpoints` テーブルから `DISTINCT thread_id` を取得し、既存セッションの一覧を返す。
- `_invoke_workflow()` は `{"configurable": {"thread_id": trace_id}}` を LangGraph に渡し、trace_id を実行スコープキーとして利用する。

## 前提条件

- `support-desk-agent` の依存が導入済みであること（`uv sync`）。
- `langgraph-checkpoint-sqlite` が利用可能であること。
- テスト実行は `${HOME}/source/repos/support-desk-agent/` から行う。

## 検証手順

### 1. 事前準備

```bash
cd ${HOME}/source/repos/support-desk-agent
uv sync
```

### 2. case_id 採番の単体テスト

```bash
cd ${HOME}/source/repos/support-desk-agent
uv run python -m pytest tests/test_case_id_resolver.py -v
```

期待結果:

- `test_generated_case_id_uses_timestamp_and_suffix_format`: `CASE-\d{8}-\d{6}-[0-9A-F]{4}` パターンに一致する。
- `test_prefers_explicit_ticket_ids`: `explicit_ticket_id` が大文字正規化されて返る。

### 3. trace 識別子正規化の単体テスト

```bash
cd ${HOME}/source/repos/support-desk-agent
uv run python -m pytest tests/test_state_model.py -v
```

期待結果:

- `test_model_normalizes_legacy_session_id`: `session_id="SESSION-legacy-001"` が `trace_id="TRACE-legacy-001"` になる。
- `test_model_preserves_existing_trace_family`: `thread_id` が `trace_id` に上書き統一される。

## 暫定判定

| 観点 | 現状評価 |
| --- | --- |
| `case_id` 採番 | 成立している |
| `trace_id` / `thread_id` の一体管理 | 成立している |
| `trace_id` を再開キーとした state 復元 | 成立している |
| CLI 横断・外部 BFF からの trace 引継ぎ | 追加確認余地あり |

support-desk-agent における O-02-01/02/04 の主要な成立条件は確認済みである。API 層を超えた trace_id 引継ぎ（外部クライアントからの指定）については O-03 系との連携で追加確認を行う。
