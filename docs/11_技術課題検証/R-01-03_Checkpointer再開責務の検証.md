# R-01-03_Checkpointer 再開責務の検証

## 検証目的

本検証の主目的は、サブ課題 R-01-03「Checkpointer の再開責務」について、support-desk-agent の実装をもとに、LangGraph の SQLite Checkpointer が `thread_id`（= `trace_id`）をキーとしてワークフロー内部状態を保存・復元できることを確認することである。

最終的には、R-01 の完了判定に必要な材料として、正常系、代表的な異常系、運用上の制約を明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| R-01 | R-01-03 | `SqliteSaver` による中断状態保存と `trace_id` を使った state 復元 |

副次的に O-02-04（trace_id の再開利用）・A-02-01（interrupt と Checkpointer）の確認にも利用する。

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../03_検証準備/技術課題と対応方針.md)
  - R-01-03 に対応し、Checkpointer の再開責務を検証対象とする。
- [A-02-01_interruptとCheckpointer保存の検証.md](./A-02-01_interruptとCheckpointer保存の検証.md)
  - ai-chat-util 側の LangGraph Checkpointer 実装との対比として参照する。
- [O-02-01_trace_id採番とレイヤ横断伝播の検証.md](./O-02-01_trace_id採番とレイヤ横断伝播の検証.md)
  - `thread_id` = `trace_id` による統一管理はこちらで確認する。

## 検証で確認したいこと

### 1. 正常系

- `_workflow_checkpointer()` が `case_id` と `workspace_path` から決定論的に `checkpoints.sqlite` へのパスを解決できること。
- `graph.invoke()` 実行時に Checkpointer が `thread_id = trace_id` で各ノード境界の state を保存すること。
- `_load_state()` が同一 `thread_id` を使って Checkpointer から state を復元できること。
- `checkpoint_status()` が保存済み `trace_id` の一覧を返せること。

### 2. 異常系

- `case_id` または `workspace_path` が未指定の場合、`_workflow_checkpointer()` が `ValueError` を送出し、不正なパスで Checkpointer を初期化しないこと。
- 存在しない `trace_id` で `_load_state()` を呼び出した場合、空の `CaseState` が返り例外を送出しないこと。

### 3. 運用系

- `checkpoint_db_filename`（既定値 `checkpoints.sqlite`）が `config.yml` で変更可能であること。
- Checkpoint DB は `<workspace>/.traces/checkpoints.sqlite` に配置され、ケースごとに分離されること。
- 再起動後も同一パスの SQLite ファイルを参照することで、中断状態を復元できること。

## 対象構成

| 論点 | 実装箇所 | 現状評価 |
| --- | --- | --- |
| Checkpointer 生成 | `runtime/abstract_service.py` の `_workflow_checkpointer()` | 実装あり |
| State 保存・復元 | `runtime/abstract_service.py` の `_invoke_workflow()` / `_load_state()` | 実装あり |
| Checkpoint 状態確認 | `runtime/abstract_service.py` の `checkpoint_status()` | 実装あり |
| DB パス設定 | `config/models.py` の `DataPathSettings.checkpoint_db_filename` | 実装あり |

## 現時点の実装確認結果

### 1. Checkpointer の生成

- `_workflow_checkpointer(case_id, workspace_path)` は `case_paths.traces_dir / checkpoint_db_filename` を SQLite DB パスとして解決する。
- `SqliteSaver.from_conn_string()` でコンテキストマネージャーを返し、`graph.compile(checkpointer=checkpointer)` に渡す。
- `case_id` / `workspace_path` が未指定の場合は `ValueError` を送出して早期失敗する。

### 2. State 保存

- `_invoke_workflow()` は `{"configurable": {"thread_id": trace_id, "checkpoint_ns": ""}}` を LangGraph に渡す。
- 各ノード実行後、LangGraph が Checkpointer に state を自動保存する。
- `wait_for_approval` で処理が一時停止した場合も、その時点の state が Checkpointer に保存される。

### 3. State 復元

- `_load_state(case_id, trace_id, workspace_path)` は `graph.get_state({"configurable": {"thread_id": trace_id}})` で state を読み戻す。
- 復元した state を `_normalize_state_ids()` で trace 識別子を正規化して返す。

### 4. Checkpoint 状態確認

- `checkpoint_status()` は SQLite の `checkpoints` テーブルから `DISTINCT thread_id` を取得して `trace_ids` として返す。
- `trace_id` を指定した場合は `has_trace` / `state_status` / `workflow_kind` も返す。

### 5. DB パス

- `DataPathSettings.checkpoint_db_filename: str = "checkpoints.sqlite"` が既定値であり、`config.yml` で変更可能。
- DB は `<workspace>/.traces/checkpoints.sqlite` に配置され、ケースごとに独立する。

## 前提条件

- `support-desk-agent` の依存が導入済みであること（`uv sync`）。
- `langgraph-checkpoint-sqlite` が利用可能であること。

## 検証手順

### 1. 事前準備

```bash
cd ${HOME}/source/repos/support-desk-agent
uv sync
```

### 2. Checkpointer 関連テスト

```bash
cd ${HOME}/source/repos/support-desk-agent
uv run python -m pytest tests/ -v -k "checkpoint or state or restore"
```

### 3. checkpoint_status API の確認（統合確認）

```bash
# ケース実行後に確認
curl -s "http://localhost:8010/cases/{case_id}/runtime-audit?trace_id={trace_id}&workspace_path={workspace_path}" \
  | python3 -m json.tool
```

### 4. SQLite DB の直接確認

```bash
# ケース実行後、DB の存在と trace_id を確認
sqlite3 "${HOME}/source/repos/support-desk-agent/samples/support-desk-agent/work/{case_id}/.traces/checkpoints.sqlite" \
  "SELECT DISTINCT thread_id, COUNT(*) FROM checkpoints GROUP BY thread_id;"
```

期待結果:

- 実行した `trace_id` の行が存在し、複数の checkpoint 行が記録されていること。

## 暫定判定

| 観点 | 現状評価 |
| --- | --- |
| `SqliteSaver` による state 保存 | 成立している |
| `thread_id = trace_id` による state 復元 | 成立している |
| `checkpoint_status()` による一覧確認 | 成立している |
| DB パスの config 化 | 成立している |
| ケース間の DB 分離 | 成立している（`<workspace>/.traces/` 配下） |
| 状態管理 DB の UI 向け責務（R-01-02）| 追加確認余地あり（本文書の範囲外） |

R-01-03 の主要な成立条件は support-desk-agent で確認済みである。
