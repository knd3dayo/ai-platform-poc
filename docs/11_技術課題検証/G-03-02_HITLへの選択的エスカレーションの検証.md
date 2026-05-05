# G-03-02_HITL への選択的エスカレーションの検証

## 検証目的

本検証の主目的は、サブ課題 G-03-02「HITL への選択的エスカレーション」について、support-desk-agent の実装をもとに、エスカレーション要否の判定・承認待ちへの遷移・承認結果に基づくルーティングが成立することを確認することである。

最終的には、G-03 の完了判定に必要な材料として、正常系、代表的な異常系、運用上の制約を明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| G-03 | G-03-02 | `_should_escalate()` による選択的エスカレーション判定と `wait_for_approval` による HITL 待機 |

副次的に T-04-03（承認後 Apply 経路）・A-02-01（interrupt / Checkpointer 保存）とも関連する。

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../03_検証準備/技術課題と対応方針.md)
  - G-03-02 に対応し、AI ガバナンス層からの HITL 選択的エスカレーションを検証対象とする。
- [T-04-02_DryRunPlanと承認後Apply経路の検証.md](./T-04-02_DryRunPlanと承認後Apply経路の検証.md)
  - `wait_for_approval` 通過後の Apply 経路はこちらで確認する。
- [R-01-03_Checkpointer再開責務の検証.md](./R-01-03_Checkpointer再開責務の検証.md)
  - 承認待ち中の state が Checkpointer に保存されることはこちらで確認する。

## 検証で確認したいこと

### 1. 正常系

- `_should_escalate()` がエスカレーションマーカー（`"escalate"` / `"エスカレーション"` 等）を検出した場合、`escalation_required = True` に設定されること。
- エスカレーション不要の場合は `draft_review → wait_for_approval` 経路、要の場合は `escalation_review → wait_for_approval` 経路へルーティングされること。
- `wait_for_approval` ノードで処理が一時停止し、`status = "WAITING_APPROVAL"` になること。
- 承認後に `approval_decision` に応じた経路（`approved` → ticket_update、`rejected` → draft_review、`reinvestigate` → investigation）へ遷移すること。

### 2. 異常系

- エスカレーション executor が `None` の場合、フォールバックロジックで `escalation_summary` / `escalation_draft` が設定され、処理が継続すること。
- `cancel_requested = True` の場合、`force_stop` ノードへルーティングされ、承認待ちに遷移しないこと。

### 3. 運用系

- `approval_history` に承認記録が蓄積されること。
- `cancel_reason` に停止理由が記録されること。
- `POST /cases/{case_id}/cancel` でキャンセル要求を送り、次のノード境界で `FORCE_STOPPED` に遷移できること。

## 対象構成

| 論点 | 実装箇所 | 現状評価 |
| --- | --- | --- |
| エスカレーション判定 | `agents/sample/sample_supervisor_agent.py` の `_should_escalate()` | 実装あり |
| 承認待ちノード | `agents/sample/sample_supervisor_agent.py` の `wait_for_approval()` | 実装あり |
| エスカレーション経路分岐 | `workflow/sample/sample_case_workflow.py` の `_route_after_investigation()` | 実装あり |
| 承認後ルーティング | `workflow/sample/sample_case_workflow.py` の `_route_after_approval()` | 実装あり |
| 強制停止経路 | `workflow/sample/sample_case_workflow.py` の `_force_stop()` / `_route_after_receive()` | 実装あり |
| キャンセル API | `interfaces/api.py` の `POST /cases/{case_id}/cancel` | 実装あり |

## 現時点の実装確認結果

### 1. エスカレーション判定

- `_should_escalate()` は `escalation_required` フラグ、または `raw_issue` に `"escalate"` / `"エスカレーション"` / `"バックサポート"` 等のマーカーが含まれる場合に `True` を返す。
- 判定結果に基づき、`execute_investigation()` 終了後に `next_action` が設定される。

### 2. HITL 承認待ち

- `wait_for_approval` ノードでは `state.get("approval_decision")` を確認する。
- `approval_decision` が未設定の場合（`"pending"` または空）、ノードはそのまま終了し、workflow が `WAITING_APPROVAL` 状態で中断される。
- Checkpointer に中断状態が保存されるため、外部から `approval_decision` を設定して再実行すれば再開可能。

### 3. 承認後ルーティング

- `_route_after_approval()` の分岐:
  - `"approved"` / `"approve"` → `ticket_update_subgraph`
  - `"rejected"` / `"reject"` → `draft_review`
  - `"reinvestigate"` → `investigation`
  - その他 → `__end__`

### 4. 強制停止

- `_receive_case()` で `cancel_requested` が `True` であれば `force_stop` へルーティングする。
- `_force_stop()` で `status = "FORCE_STOPPED"` と `cancel_reason` を含む `next_action` を設定する。
- `POST /cases/{case_id}/cancel` は `CancellationStore` にキャンセル要求を書き込み、次の `_invoke_workflow()` 呼び出し時に反映される。

## 前提条件

- `support-desk-agent` の依存が導入済みであること（`uv sync`）。

## 検証手順

### 1. 事前準備

```bash
cd ${HOME}/source/repos/support-desk-agent
uv sync
```

### 2. HITL・エスカレーション関連テスト

```bash
cd ${HOME}/source/repos/support-desk-agent
uv run python -m pytest tests/ -v -k "approval or escalat or hitl or cancel"
```

期待結果:

- エスカレーション判定・承認後ルーティング・強制停止の各ケースが通過すること。

### 3. キャンセル API の動作確認（統合確認）

```bash
# API 起動後に実行
curl -s -X POST http://localhost:8010/cases/CASE-TEST/cancel \
  -H "Content-Type: application/json" \
  -d '{"trace_id": "TRACE-TEST", "workspace_path": "/tmp/test", "reason": "手動テスト停止"}' | python3 -m json.tool
```

期待結果:

- `{"case_id": "CASE-TEST", "trace_id": "TRACE-TEST", "status": "cancel_requested", "reason": "手動テスト停止"}` が返ること。

## 暫定判定

| 観点 | 現状評価 |
| --- | --- |
| エスカレーション選択判定 | 成立している（マーカーベース） |
| `wait_for_approval` HITL 待機 | 成立している |
| 承認後の 3 経路ルーティング | 成立している |
| 強制停止 / cancel API | 成立している |
| リスクスコアリングベースの判定（G-03-01）| 未実装（マーカーベース判定のみ） |
| 停止判断の完全な監査ログ（G-03-04）| 追加確認余地あり |

G-03-02 の主要な成立条件は support-desk-agent で確認済みである。リスクスコアリングによる定量的な判定（G-03-01）は別途検証が必要である。
