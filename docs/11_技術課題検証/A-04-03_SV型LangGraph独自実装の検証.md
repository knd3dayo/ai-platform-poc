# A-04-03_SV型LangGraph独自実装の検証

## 検証目的

本検証の主目的は、サブ課題 A-04-03「SV型エージェントの実装検証（LangGraphベースの独自実装）」について、PoC 環境で成立性を確認することである。

最終的には、A-04 の完了判定に必要な材料として、Supervisor、状態永続化、非同期HITL、再開を備えた SV 型を LangGraph 独自実装で構成できるか、その正常系、異常系、運用上の制約を明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| A-04 | A-04-03 | Supervisor、状態永続化、非同期HITL、再開を備えた SV 型を LangGraph 独自実装で構成できるかを確認する。 |

必要に応じて、副次的に A-01-02、A-02-01、A-02-02、A-02-03 の前提整理にも利用する。

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../03_検証準備/01_技術課題と対応方針.md)
  - A-04-03 に対応し、LangGraph 独自実装が SV 型の基盤として成立するかを確認する。
- [Application層の実装方針](../03_検証準備/12_Application層実装方針.md)
  - SV 型は LangGraph で実装し、自律型エージェントを MCP 経由で呼び出す前提を参照する。
- [生成AIアプリケーション層の実現方式](../02_アーキテクチャ実現方式/02_生成AIアプリケーション層の実現方式.md)
  - SV 型は合議、評価、承認、例外判断を扱う状態機械として実装する整理を参照する。
- [A-01-02_スーパーバイザーのツール選択とMCP結果判断の検証.md](./A-01-02_スーパーバイザーのツール選択とMCP結果判断の検証.md)
  - Supervisor の判断品質とツール選択の既存検証を参照する。
- [A-02-01_interruptとCheckpointer保存の検証.md](./A-02-01_interruptとCheckpointer保存の検証.md)
  - interrupt と Checkpointer を使った状態永続化前提を参照する。

## 検証で確認したいこと

### 1. 正常系

- `agent_chat` が SV 型の主入口として成立していること。
- supervisor が tool agent 群を束ね、結果評価と追加照会を制御できること。
- pause / resume、approval、clarification を備えた状態遷移が成立すること。

### 2. 異常系

- ツール結果が不十分な場合に、そのまま断定回答しないこと。
- 状態永続化がないまま長時間待機する構成に退化しないこと。
- SV 型の責務と自律型の責務が混ざり、探索的処理をすべて supervisor に抱え込まないこと。

### 3. 運用系

- trace_id、監査イベント、pause / resume 状態を追跡できること。
- 設定で routing や sufficiency check を切り替えられること。
- API / CLI / MCP 入口を横断して同じ契約で扱えること。

## 対象構成

| 観点 | 主な既存実装 / 入口 | 備考 |
| --- | --- | --- |
| CLI 入口 | `${HOME}/source/repos/ai-chat-util/app/src/ai_chat_util/cli/__main__.py` の `agent_chat` | SV 型の主入口 |
| API 入口 | `${HOME}/source/repos/ai-chat-util/app/src/ai_chat_util/api/api_server.py` の `agent_chat` | FastAPI 経由 |
| MCP / facade | `${HOME}/source/repos/ai-chat-util/app/src/ai_chat_util/core/app.py` の `run_agent_chat` | 共通 facade |
| Supervisor 本体 | `${HOME}/source/repos/ai-chat-util/app/src/ai_chat_util/base/agent/agent_client.py`、`agent_client_util.py` | route 選択、tool 実行、統合 |
| 既存検証 | [A-01-02_スーパーバイザーのツール選択とMCP結果判断の検証.md](./A-01-02_スーパーバイザーのツール選択とMCP結果判断の検証.md) | 判断品質の詳細 |

## 既存実装と入口の対応づけ

1. CLI

- `uv --directory ./app run -m ai_chat_util.cli agent_chat`

2. API

- `POST /api/ai_chat_util/agent_chat`

3. MCP / ライブラリ

- `run_agent_chat`
- `MCPClient.chat()`

4. 内部制御

- `AgentClientUtil.create_workflow()` が supervisor 配下の tool agents を構成する。
- sufficiency check、tool catalog、audit event により SV 型の判断責務を支える。

## 前提条件

- `${HOME}/source/repos/ai-chat-util/app` の依存が導入済みであること。
- MCP 連携付き設定ファイルを利用できること。
- 必要に応じて LiteLLM と関連 MCP が起動済みであること。

## 検証手順

### 1. 事前準備

```bash
cd ${HOME}/source/repos/ai-chat-util/app
uv sync
```

### 2. 正常系確認

```bash
cd ${HOME}/source/repos/ai-chat-util
uv --directory ./app run -m ai_chat_util.cli \
  --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.normal-only.poc.yml \
  agent_chat -p "読み込まれている設定ファイルの場所を教えてください"
```

期待結果:

- `agent_chat` が supervisor 型入口として動作する。
- 適切な tool agent が選ばれ、結果が統合される。

### 3. HITL / 再開確認

固定回帰シナリオ:

- approval 停止制御の固定回帰シナリオは、absolute path を含む local directory / file 問い合わせを採用する。
- 特に local directory 確認では、absolute path を含む問い合わせの方が `route.explicit_directory_path_request` まで含めて再現性が高い。

```bash
cd ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp
./run-ai-chat-util.sh --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.hitl.poc.yml \
  agent_chat -p "次の Markdown ファイルを確認して検証目的を要約してください: /home/user/source/repos/ai-platform-poc/docs/11_技術課題検証/A-01-02_スーパーバイザーのツール選択とMCP結果判断の検証.md"
```

期待結果:

- `general_tool_agent -> analyze_files` が選択され、未承認のままツール実行は行われない。
- approval が必要なケースで `paused` が返る。
- trace_id を維持して再送できる。

補足:

- generic な `work ディレクトリを確認してください` も現時点では `general_tool_agent -> analyze_files -> paused` を再現できているが、reason code が `route.explicit_directory_path_request` に固定されない。
- そのため、approval 停止制御の固定検証ケースとしては、absolute path を含む問い合わせを優先採用する。

### 4. 異常系確認

期待結果:

- 不十分なツール結果を検知し、再照会または HITL へ遷移する。
- 追加照会ループが無制限に続かない。

## 判定基準

| 観点 | 判定基準 |
| --- | --- |
| 構造成立性 | LangGraph ベースの supervisor 実装が独立した SV 型入口として存在する。 |
| 制御成立性 | tool 選択、結果評価、pause / resume、HITL の基本制御を確認できる。 |
| 運用成立性 | trace_id、監査イベント、設定切替で運用上の追跡と制御が可能である。 |

## 検証結果記録欄

### 2026-04-05 実測結果

初回実行コマンド:

```bash
cd ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp
./run-ai-chat-util.sh --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.normal-only.poc.yml \
  agent_chat -p "読み込まれている設定ファイルの場所を教えてください"
```

初回実行結果:

- `agent_chat` の起動自体は始まるが、normal-tools 用 MCP 子プロセスの初期化で失敗した。
- 主要な観測結果は次のとおり。
  - `Creating normal agent for MCP server 'normal-tools'...`
  - `error: No such file or directory (os error 2)`
  - `mcp.shared.exceptions.McpError: Connection closed`

初回考察:

- `uv` 自体はホスト上で解決できたため、失敗点は stdio で起動する MCP 子プロセス側の引数解決と見られる。
- 現行の `mcp_servers.normal-only.json` は `${HOME}` を含む文字列をそのまま保持しており、stdio 子プロセス起動時にシェル展開されず、ディレクトリまたは設定ファイル解決に失敗している可能性が高い。

修正内容:

- `infra/31-ai-chat-util-mcp/mcp_servers.normal-only.json` の `${HOME}` を絶対パスへ置換した。
- あわせて `mcp_servers.local.json` と `mcp_servers.coding-only.json` も同様に修正した。
- LiteLLM Proxy の公開モデル名に合わせて、`infra/31-ai-chat-util-mcp/ai-chat-util-config*.yml` の `completion_model` を `poc-chat-model`、`embedding_model` を `poc-embedding-model` へ統一した。

再実行結果:

- supervisor 起動、normal-tools MCP 接続、tool catalog 解決、LiteLLM 応答、tool 呼び出しまで成功した。
- 主要な観測結果は次のとおり。
  - `Creating normal agent for MCP server 'normal-tools'...`
  - `litellm.acompletion(model=openai/poc-chat-model) 200 OK`
  - `config_path=/home/user/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.normal-only.poc.yml`
- 最終応答として、設定ファイルの実パスを返した。

再実行時の回答:

```text
設定ファイルは次の場所にあります：
/home/user/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.normal-only.poc.yml
```

| 項目 | 結果 | 補足 |
| --- | --- | --- |
| 正常系 | 確認済み | `agent_chat` が supervisor、MCP tool 呼び出し、LiteLLM 応答まで到達し、設定ファイル実パスを返した。 |
| 異常系 | 確認済み | 修正前は stdio 子プロセス起動時に `No such file or directory` と `Connection closed` で失敗することを観測した。 |
| 運用系 | 一部確認済み | PoC 設定では `${HOME}` や LiteLLM 公開モデル名との不整合が実行成立性に影響するため、絶対パスと公開モデル名へ揃える運用が必要である。 |

### 2026-04-07 追試結果

実行コマンド 1:

```bash
cd ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp
./run-ai-chat-util.sh --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.normal-only.poc.yml \
  agent_chat -p "読み込まれている設定ファイルの場所を教えてください"
```

実行結果:

- `Creating normal agent for MCP server 'normal-tools'...` を確認した。
- `Resolved tool catalog: route=general_tool_agent ...` を確認した。
- `litellm.acompletion(model=openai/poc-chat-model) 200 OK` を確認した。
- `Post-close evidence check ... config_path=/home/user/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.normal-only.poc.yml` を確認した。
- 最終応答として、設定ファイル実パス `/home/user/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.normal-only.poc.yml` を返した。

評価:

- 2026-04-05 時点で確認した normal-only 正常系は、現在の PoC 環境でも再現した。
- A-04-03 の主入口である `agent_chat` と normal-tools MCP の接続、supervisor による tool catalog 解決、LiteLLM 応答、最終統合応答までは継続して成立している。

実行コマンド 2:

```bash
cd ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp
./run-ai-chat-util.sh --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.hitl.poc.yml \
  agent_chat -p "work ディレクトリを確認してください"
```

実行結果:

- `route_name=general_tool_agent` で `analyze_files` が選択された。
- `tool_selected` / `tool_result_received` では `approval_status: "required"` を記録した。
- しかし同じ trace (`11cb5b423e3744528057d64740716392`) の監査ログでは、その後 `sufficiency_judged` が `decision: "answerable"`、`requires_hitl: false`、`requires_approval: false` となり、`final_status: "completed"` で終了した。
- CLI 出力も `paused` ではなく、`work` ディレクトリの内容要約を返して完了した。

評価:

- approval 対象ツールを設定しても、現行の CLI `agent_chat` 経路では `paused` へ収束せず、結果的に supervisor が回答完了まで進んでしまうケースを観測した。
- したがって、A-04-03 の normal-only 正常系は確認済みだが、主入口 `agent_chat` における approval / 非同期 HITL 制御まで「確認済み」とはまだ言えない。
- 過去の `structured-routing-hitl-audit.jsonl` には `hitl_requested` と `final_status: "paused"` の記録も残っており、少なくとも環境または実装差分により挙動が揺れている。

### ai-chat-util チーム調査結果と修正内容

ai-chat-util チームに確認したところ、現行の approval 停止制御は `tool_selected` / `tool_result_received` に記録される `approval_status` へ直接連動しておらず、実際の `paused` 収束条件は supervisor 最終出力が question かつ approval HITL として解釈された場合に限られていた。

そのため、approval 対象ツールに対して `approval_status: required` が監査ログへ残っていても、ツール実行自体はコード上ブロックされず、supervisor がそのまま complete を返すと `sufficiency_judged` は `answerable` へ倒れ、`final_status: completed` に収束し得る状態だった。今回の completed 側 trace はこの経路と一致し、過去の paused 側 trace はモデルがプロンプトどおりに approval 質問を返したケースだった。すなわち、同一実装上で挙動がモデル応答依存になっていた。

チーム判断としては、現行プロンプト文言と `hitl_approval_tools` の意味から、approval 対象ツールは実行前に pause すべきである。これを踏まえ、次の最小修正を ai-chat-util 側へ適用したとの回答を得た。

- approval 対象ツールは未承認のまま実行せず、tool guard で deterministic にブロックする。
- approval-required シグナルが evidence に現れた場合、supervisor が complete を返していても `paused` へ強制収束させる。
- `APPROVE TOOL_NAME` を受けた再開ターンでは、そのツールのみ実行を許可する。
- 上記を固定する回帰テストを追加する。

修正対象ファイル:

- `app/src/ai_chat_util/base/agent/tool_limits.py`
- `app/src/ai_chat_util/base/agent/agent_client.py`
- `app/src/ai_chat_util/base/agent/agent_client_util.py`
- `app/src/ai_chat_util/base/agent/agent_builder.py`
- `app/src/ai_chat_util/base/agent/_test_/test_tool_guard_wrapping.py`

テスト結果:

- approval 回帰テスト 2 件を個別実行して成功した。
- 同一テストファイル全体には今回の変更と無関係な既存失敗が混在するため、フルファイル通しではなく新規ケース単位で確認した。

### 2026-04-07 修正反映後の live 再追試

実行コマンド 3:

```bash
cd ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp
./run-ai-chat-util.sh --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.hitl.poc.yml \
  agent_chat -p "work ディレクトリを確認してください"
```

実行結果:

- `trace_id=4343d83097174ac9b16e4815d9a97e27` では、route が `general_tool_agent` ではなく `deep_agent` に決定された。
- 監査ログ上、`tool_selected` / `tool_result_received` の approval 系イベントは発生せず、`sufficiency_judged` は `answerable`、`final_status` は `completed` だった。
- CLI 出力も `paused` ではなく完了応答だった。

評価:

- 同じ structured-routing + HITL 設定でも、generic な `work ディレクトリ` 問い合わせは route 判定次第で `deep_agent` へ流れ、今回修正した `general_tool_agent -> analyze_files` の approval 停止経路を通らない。
- したがって、この問い合わせ文だけでは approval 停止修正の live 検証ケースとして安定しない。

実行コマンド 4:

```bash
cd ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp
./run-ai-chat-util.sh --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.hitl.poc.yml \
  agent_chat -p "次の Markdown ファイルを確認して検証目的を要約してください: /home/user/source/repos/ai-platform-poc/docs/11_技術課題検証/A-01-02_スーパーバイザーのツール選択とMCP結果判断の検証.md"
```

実行結果:

- `trace_id=afb42032789e438ebe1293680edfb66d` では、route が `general_tool_agent` に決定された。
- `tool_selected` で `analyze_files` に `approval_status: required` が記録された。
- `tool_result_received` は `reason_code: hitl.tool_approval_required`、`payload.success: false`、`blocked: true` となり、未承認のままツール実行は行われなかった。
- 続く `sufficiency_judged` は `reason_code: sufficiency.approval_required`、`requires_hitl: true`、`requires_approval: true` となり、`hitl_requested`、`final_status: paused` へ収束した。
- CLI でも `ツール analyze_files の実行には承認が必要です。` と表示され、`HITL> ` プロンプトで停止した。

評価:

- `general_tool_agent -> analyze_files` の approval 対象経路では、今回の最小修正により deterministic な事前ブロックと `paused` 収束が live でも確認できた。
- 一方で、A-04-03 の generic なディレクトリ調査問い合わせは route が `deep_agent` へ揺れるため、approval 停止修正そのものとは別に、検証シナリオの固定化または route 条件の整理が必要である。

### 2026-04-07 追加再検証

ai-chat-util チームが推奨した追加 live 確認ケース 3 件を、現行の structured-routing + HITL 設定で再実行した。なお現在の routing prompt には、ローカルディレクトリパスや `working_directory` 配下で解決できるディレクトリ名の単発調査は `general_tool_agent` を優先する旨が入っている。

実行コマンド 5:

```bash
cd ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp
./run-ai-chat-util.sh --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.hitl.poc.yml \
  agent_chat -p "work ディレクトリを確認してください"
```

実行結果:

- `trace_id=f0a4abbe22ad4e40b67b62a9b88c03ff` の初回 turn では、route が `general_tool_agent` に決定された。
- `route_decision_model_output.reason_code` は ai-chat-util チーム想定の `route.explicit_directory_path_request` ではなく `route.directory_check`、`route_decided.reason_code` は `route.general_tool_sufficient` だった。
- `tool_selected.tool_name=analyze_files`、`tool_result_received.reason_code=hitl.tool_approval_required`、`final_status=paused` を確認した。

評価:

- generic な `work ディレクトリ` 問い合わせでも、現在は `general_tool_agent -> analyze_files -> paused` の approval 検証経路へ入ることを live で再確認した。
- 一方で、reason code は期待されていた explicit-directory 系ではなく、より汎用的な `general_tool_sufficient` 系に分類されている。

実行コマンド 6:

```bash
cd ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp
./run-ai-chat-util.sh --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.hitl.poc.yml \
  agent_chat -p "/home/user/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/work ディレクトリを確認してください"
```

実行結果:

- `trace_id=3ac7c869887d4012afa6525889d50187` の初回 turn では、route が `general_tool_agent` に決定された。
- `route_decided.reason_code=route.explicit_directory_path_request` を確認した。
- `tool_selected.tool_name=analyze_files`、`tool_result_received.reason_code=hitl.tool_approval_required`、`final_status=paused` を確認した。

評価:

- absolute path を明示した local directory 確認は、ai-chat-util チームの期待どおり `general_tool_agent` と explicit-directory 系 reason code へ安定して寄り、approval 検証ケースとして引き続き利用できる。

実行コマンド 7:

```bash
cd ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp
./run-ai-chat-util.sh --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.hitl.poc.yml \
  agent_chat -p "work ディレクトリ全体を起点に深く調査してください"
```

実行結果:

- `trace_id=23695bee2d404b4fb8ba5f217b619f4d` では、route が `deep_agent` に決定された。
- `route_decided.reason_code=route.multi_step_investigation_needed`、`sufficiency_judged.reason_code=sufficiency.answer_supported_by_evidence`、`final_status=completed` を確認した。

評価:

- 単発確認要求と「深く調査してください」の境界は live でも分かれており、深掘り依頼では `deep_agent` に寄る余地が維持されている。

総合評価:

- ai-chat-util チームが示した受け入れ基準のうち、「単発の local directory 確認要求が stable に `general_tool_agent -> analyze_files` 経路へ入ること」は、generic 問い合わせと absolute path 問い合わせの両方で概ね満たされた。
- 残差は、generic な `work ディレクトリ` 問い合わせで reason code が `route.explicit_directory_path_request` ではなく `route.general_tool_sufficient` 系に分類される点である。
- approval 検証の固定シナリオとしては、absolute path 問い合わせを正式採用する。generic な `work ディレクトリ` 問い合わせは補助的な確認ケースとして扱う。

## 残課題

残件は、A-04-03 本体で追うものと他論点へ切り出すものを次のように整理する。

### A-04-03 本体に残る論点

- `general_tool_agent -> analyze_files` の approval 停止制御は live で確認できたが、generic な `work ディレクトリ` 問い合わせは reason code が explicit-directory 系に固定されていない。残差は route 分類ラベルの整理である。

### 別論点として扱うもの

- DeepAgents 実装との差分整理は A-04-04 で扱う。
- cross-type 自動 reroute は A-01-03 の残課題として扱う。
- end-to-end の非同期 HITL 運用は、BFF / 状態管理 DB との接続を含むため別途の運用検証で扱う。
- MCP 設定と LiteLLM 設定の整合を環境ごとに自動検査する仕組みは、実装改善として別途検討する。