# T-04-02_Dry Run Plan と承認後 Apply 経路の検証

## 検証目的

本検証の主目的は、サブ課題 T-04-02「Dry Run / Plan の標準出力」および T-04-03「承認後 Apply 経路」について、support-desk-agent の実装をもとに、`POST /plan` でエージェントが実行計画のみを返し、`POST /action` で計画を引き継いで実行へ移行できることを確認することである。

最終的には、T-04 の完了判定に必要な材料として、正常系、代表的な異常系、運用上の制約を明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| T-04 | T-04-02 | `POST /plan` による Dry Run 計画出力と `plan_steps` の標準化 |
| T-04 | T-04-03 | `POST /action` による計画引き継ぎと `approval_decision` に基づくルーティング |

副次的に O-02-04（trace_id の再開利用）と G-03-02（HITL エスカレーション）とも関連する。

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../03_検証準備/技術課題と対応方針.md)
  - T-04-02/03 に対応し、Plan → Approve → Apply の経路を検証対象とする。
- [G-03-02_HITLへの選択的エスカレーションの検証.md](./G-03-02_HITLへの選択的エスカレーションの検証.md)
  - `wait_for_approval` ノードが plan/action 分離の HITL 境界となることを参照する。
- [O-02-01_trace_id採番とレイヤ横断伝播の検証.md](./O-02-01_trace_id採番とレイヤ横断伝播の検証.md)
  - `/action` が `/plan` の `trace_id` を引き継ぐことで state 継続が実現されることを参照する。

## 検証で確認したいこと

### 1. 正常系

- `POST /plan` が `execution_mode: "plan"` で実行を進め、`plan_summary` / `plan_steps` のみを返して実際のチケット更新・調査を行わないこと。
- `POST /action` が `execution_plan`（= plan の結果）と `trace_id` を受け取り、調査・承認・チケット更新まで実行すること。
- `approval_decision = "approved"` の場合、`ticket_update_subgraph` ノードへルーティングされてチケット更新が実行されること。
- `approval_decision = "rejected"` の場合、`draft_review` ノードへ戻ってドラフトが再生成されること。
- `approval_decision = "reinvestigate"` の場合、`investigation` ノードへ戻って再調査が実行されること。

### 2. 異常系

- `execution_plan` が指定されない `POST /action` で、plan 段階を経ずに調査が開始されても、状態整合が崩れないこと。
- `trace_id` 不一致で `POST /action` を呼び出した場合、新規セッションとして扱われ別セッションを上書きしないこと。

### 3. 運用系

- plan の結果（`plan_summary` / `plan_steps`）が `RuntimeEnvelope` として返され、フロントエンドで表示・確認できること。
- `summarize_plan()` の出力がワークフロー種別（`WorkflowKind`）に対応した日本語説明を含むこと。

## 対象構成

| 論点 | 実装箇所 | 現状評価 |
| --- | --- | --- |
| Plan エンドポイント | `interfaces/api.py` の `POST /plan` | 実装あり |
| Action エンドポイント | `interfaces/api.py` の `POST /action` | 実装あり |
| plan_steps 生成 | `workflow/router.py` の `build_plan_steps()` / `summarize_plan()` | 実装あり |
| 承認後ルーティング | `workflow/sample/sample_case_workflow.py` の `_route_after_approval()` | 実装あり |

## 現時点の実装確認結果

### 1. Plan エンドポイント

- `POST /plan` は `service.plan()` を呼び出す。内部で `execution_mode = "plan"` が設定され、計画立案のみを実行する。
- 計画結果は `RuntimeEnvelope`（`plan_summary` / `plan_steps` / `trace_id` 等を含む）として返される。

### 2. Action エンドポイント

- `POST /action` は `service.action()` を呼び出し、`execution_plan`（plan 結果の JSON）と `trace_id` を受け取る。
- plan 段階の `trace_id` を `thread_id` キーとして Checkpointer から state を復元し、調査フェーズへ移行する。

### 3. 承認後ルーティング

- `_route_after_approval()` は `approval_decision` 文字列で分岐する。
  - `"approved"` / `"approve"` → `ticket_update_subgraph`（チケット更新実行）
  - `"rejected"` / `"reject"` → `draft_review`（ドラフト再生成）
  - `"reinvestigate"` → `investigation`（再調査）
  - その他 → `__end__`（終了）
- `wait_for_approval` ノード（LangGraph の `interrupt` 相当）で実行が一時停止し、`approval_decision` が外部から設定されるまで続行しない。

## 前提条件

- `support-desk-agent` の依存が導入済みであること（`uv sync`）。
- `samples/support-desk-agent/config-sample.yml` が配置済みであること。
- LiteLLM Proxy 等の LLM バックエンドが稼働していること（API 統合確認の場合）。

## 検証手順

### 1. 事前準備

```bash
cd ${HOME}/source/repos/support-desk-agent
uv sync
```

### 2. Plan → Action フローのユニットテスト

```bash
cd ${HOME}/source/repos/support-desk-agent
uv run python -m pytest tests/ -v -k "plan or action or approval"
```

期待結果:

- plan エンドポイント呼び出し後に `plan_steps` が設定されていること。
- `approval_decision = "approved"` で ticket_update ルートが選択されること。

### 3. API による Plan / Action 確認（統合確認）

```bash
# API 起動
cd ${HOME}/source/repos/support-desk-agent/samples/support-desk-agent
./start-sample.sh --workspace-root work --config config-sample.yml &

# Plan 実行
curl -s -X POST http://localhost:8010/plan \
  -H "Content-Type: application/json" \
  -d '{"prompt": "ログにエラーが発生しています。調査してください。"}' | python3 -m json.tool
```

期待結果:

- `plan_summary` と `plan_steps` が返り、チケット更新は実行されていないこと（`ticket_update_result` が null）。
- `trace_id` が `TRACE-` プレフィックスで返ること。

## 暫定判定

| 観点 | 現状評価 |
| --- | --- |
| `POST /plan` による Dry Run 計画出力 | 成立している |
| `plan_steps` の構造化出力 | 成立している |
| `POST /action` による計画引き継ぎ | 成立している |
| `approval_decision` による承認後ルーティング | 成立している（approved / rejected / reinvestigate の 3 経路） |
| UI 接続（承認入力の外部化） | 追加確認余地あり（A-04-05 相当） |

T-04-02/T-04-03 の主要な成立条件は support-desk-agent で確認済みである。
