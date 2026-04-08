# ai-chat-util チーム調査依頼: A-04-03 agent_chat の approval 停止制御が `completed` に収束する件

## 想定する issue タイトル

`agent_chat` で approval 対象ツールが `approval_status: required` を記録しても `paused` ではなく `completed` に収束する

## 概要

ai-platform-poc 側の A-04-03 検証で、SV 型 LangGraph 独自実装の主入口 `agent_chat` を追試したところ、normal-only 構成の正常系は再現できました。

一方で、`hitl_approval_tools: [analyze_files]` を設定した構成では、監査ログ上 `tool_selected` / `tool_result_received` に `approval_status: required` が記録されているにもかかわらず、その後 `sufficiency_judged` が `requires_hitl: false` / `requires_approval: false` となり、最終的に `final_status: completed` で終了しました。

過去の同系統ログでは `hitl_requested` と `final_status: paused` が記録されており、挙動が揺れています。approval 対象ツールの停止制御が現行実装でどの条件に依存しているかを調査したく、issue 化します。

## 背景

- 対象検証: A-04-03 SV 型エージェントの実装検証（LangGraph ベースの独自実装）
- 検証目的:
  - `agent_chat` が SV 型の主入口として成立すること
  - supervisor が tool agent 群を束ね、結果評価と追加照会を制御できること
  - approval / clarification / pause を含む状態遷移が成立すること

normal-only 構成では主入口として成立しているため、今回の論点は approval / HITL 制御に限定されます。

## 再現手順

### 1. normal-only 正常系

```bash
cd ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp
./run-ai-chat-util.sh --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.normal-only.poc.yml \
  agent_chat -p "読み込まれている設定ファイルの場所を教えてください"
```

期待結果:

- `agent_chat` が supervisor 入口として動作する
- `normal-tools` MCP 接続、tool catalog 解決、LiteLLM 応答、最終統合応答まで到達する

実測結果:

- 上記は成立
- 設定ファイル実パス `/home/user/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.normal-only.poc.yml` を返却

### 2. approval 対象ツールを含む構成

```bash
cd ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp
./run-ai-chat-util.sh --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.hitl.poc.yml \
  agent_chat -p "work ディレクトリを確認してください"
```

利用設定の要点:

- `routing_mode: structured`
- `sufficiency_check_enabled: true`
- `audit_log_enabled: true`
- `hitl_approval_tools:`
  - `analyze_files`

期待結果:

- `analyze_files` が approval 対象として扱われる
- supervisor が `paused` へ収束し、approval 要求を返す

実測結果:

- `analyze_files` は選択・実行された
- 監査ログには `approval_status: required` が記録された
- しかし最終的には `completed` に収束し、`work` ディレクトリの要約を返した

## 実測ログの要点

### 2026-04-07 の completed 側 trace

- trace_id: `11cb5b423e3744528057d64740716392`
- 監査ログ:
  - `route_name: general_tool_agent`
  - `tool_name: analyze_files`
  - `approval_status: required`
  - その後 `sufficiency_judged.decision: answerable`
  - `requires_hitl: false`
  - `requires_approval: false`
  - `final_status: completed`

該当ログ:

- `/home/user/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/work/structured-routing-hitl-audit.jsonl`

### 過去の paused 側 trace

- trace_id: `4bf92f3577b34da6a3ce929d0e0e4736`
- 監査ログ:
  - `reason_code: sufficiency.approval_required`
  - `hitl_requested`
  - `approval_status: requested`
  - `final_status: paused`

該当ログ:

- `/home/user/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/work/structured-routing-hitl-audit.jsonl`
- 参考応答:
  - `/home/user/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/work/hitl-response-1.json`

## 期待する調査観点

1. `hitl_approval_tools` が設定されている場合、`tool_selected.approval_status=required` の後に `completed` へ進んでしまう条件は何か
2. `sufficiency_judged` が `approval_required` ではなく `answerable` へ倒れる分岐条件は何か
3. post-close evidence 補完や final answer augmentation が、approval 判定を上書きしていないか
4. CLI `agent_chat` 経路と、過去に `paused` になった経路とで、実行モードまたは設定解決に差がないか
5. 期待仕様として「approval 対象ツールは実行前に必ず pause すべき」なのか、それとも「実行後に最終応答を止めればよい」なのか

## 期待する回答

- 原因の切り分け
- 想定仕様と現行挙動のどちらが正しいか
- 必要なら修正方針
- 再現用の最小ケース

## 関連文書

- `/home/user/source/repos/ai-platform-poc/docs/11_技術課題検証/A-04-03_SV型LangGraph独自実装の検証.md`
- `/home/user/source/repos/ai-platform-poc/docs/11_技術課題検証/00_検証文書台帳.md`

## ai-chat-util チーム回答

### 原因

- 現行の approval 停止制御は、`tool_selected` / `tool_result_received` に記録される `approval_status` へ直接連動していなかった。
- 実際の `paused` 収束条件は、supervisor の最終出力が question になり、かつ approval HITL として解釈された場合に限られていた。
- そのため、approval 対象ツールで `approval_status: required` が監査ログへ残っても、ツール実行自体はコード上ブロックされず、supervisor がそのまま complete を返すと `sufficiency_judged` は `answerable` へ倒れ、`final_status: completed` に収束し得る状態だった。
- 今回の completed 側 trace はこの経路に一致し、過去の paused 側 trace はモデルがプロンプトどおりに approval 質問を返したケースだった。つまり、同一実装上でモデル応答依存の揺れが残っていた。

### 判断

- 現行プロンプト文言と `hitl_approval_tools` の意味から見ると、approval 対象ツールは実行前に pause すべき、が自然との回答だった。
- 少なくとも completed へ収束してしまう従来挙動は、設定意図に対してモデル依存が強すぎる状態と判断された。

### 最小修正

- approval 対象ツールは未承認のまま実行せず、tool guard で deterministic にブロックする。
- approval-required シグナルが evidence に現れた場合、supervisor が complete を返していても `paused` へ強制収束させる。
- `APPROVE TOOL_NAME` を受けた再開ターンでは、そのツールのみ実行を許可する。
- 上記を固定する回帰テストを追加する。

### 修正ファイル

- `/home/user/source/repos/ai-chat-util/app/src/ai_chat_util/base/agent/tool_limits.py`
- `/home/user/source/repos/ai-chat-util/app/src/ai_chat_util/base/agent/agent_client.py`
- `/home/user/source/repos/ai-chat-util/app/src/ai_chat_util/base/agent/agent_client_util.py`
- `/home/user/source/repos/ai-chat-util/app/src/ai_chat_util/base/agent/agent_builder.py`
- `/home/user/source/repos/ai-chat-util/app/src/ai_chat_util/base/agent/_test_/test_tool_guard_wrapping.py`

### テスト

- approval 回帰テスト 2 件を個別実行して成功した。
- 同一テストファイル全体には今回の変更と無関係な既存失敗が混在するため、フルファイル通しではなく新規ケースを対象に確認した。

## PoC 側 follow-up 確認結果

### 確認できたこと

- targeted test 2 件は PoC 側でも再実行し、`2 passed, 118 deselected` を確認した。
- structured-routing + HITL 設定で、明示ファイルパス付き問い合わせを使って `general_tool_agent -> analyze_files` を踏ませた場合は、live でも期待どおり `paused` へ収束した。
- このときの trace は `afb42032789e438ebe1293680edfb66d` で、`tool_result_received.reason_code: hitl.tool_approval_required`、`payload.blocked: true`、`sufficiency.approval_required`、`hitl_requested`、`final_status: paused` を確認した。

### なお残った論点

- もともとの generic な問い合わせ `work ディレクトリを確認してください` は、修正後の live 追試では `trace_id=4343d83097174ac9b16e4815d9a97e27` で `deep_agent` へ route した。
- このケースでは approval 対象の `general_tool_agent -> analyze_files` 経路に入らず、`final_status: completed` で終了した。
- したがって、今回の最小修正が無効というより、検証入力によって route 自体が変わるため、approval 停止を安定検証するには explicit file path を含む問い合わせなど、`general_tool_agent` 側へ寄せるシナリオ固定が必要である。

補足:

- 上記の route 揺れは approval 停止制御そのものとは別論点として切り出し、`ai-chat-utilチーム調査依頼_完了_A-04-03_workディレクトリ問い合わせのroute揺れ.md` に整理した。
