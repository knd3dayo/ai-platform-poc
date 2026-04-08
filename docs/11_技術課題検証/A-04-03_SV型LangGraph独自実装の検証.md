# A-04-03_SV型LangGraph独自実装の検証

## 検証目的

本検証の主目的は、サブ課題 A-04-03「SV型エージェントの実装検証（LangGraphベースの独自実装）」について、PoC 環境で成立性を確認することである。

最終的には、A-04 の完了判定に必要な材料として、`agent_chat` を主入口とする Supervisor、structured routing、approval による pause、同一 `trace_id` を使う再開、監査証跡を備えた SV 型を LangGraph 独自実装で構成できるか、その正常系、異常系、運用上の制約を明確にすることを目指す。

ただし本書で正本として扱うのは、SV 型として pause 応答に `trace_id` を返し、A-02-02 で確認済みの same `trace_id` resume 契約へ接続できることまでとする。resume の end-to-end 厳密検証自体は [A-02-02_Resumeプロトコルの検証.md](./A-02-02_Resumeプロトコルの検証.md) を正本とする。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| A-04 | A-04-03 | `agent_chat` を主入口とする SV 型で、routing、tool 実行、approval による pause、再開、監査証跡が成立するかを確認する。 |

必要に応じて、副次的に A-01-02、A-02-01、A-02-02、A-02-03、T-01-01 の前提整理にも利用する。

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
- [A-02-02_Resumeプロトコルの検証.md](./A-02-02_Resumeプロトコルの検証.md)
  - `trace_id` を使った再開契約と CLI / API の差分を参照する。
- [T-01-01_コーディングエージェントのMCPサーバー化検証.md](./T-01-01_コーディングエージェントのMCPサーバー化検証.md)
  - `run-ai-chat-util.sh`、`show_config`、MCP 接続前提を参照する。
- [A-04-05_自律型コーディングエージェント呼び出しの検証.md](./A-04-05_自律型コーディングエージェント呼び出しの検証.md)
  - coding-agent 単体契約は本書の対象外であり、参照先として切り分ける。
- [A-04-06_自律型DeepAgents実装の検証.md](./A-04-06_自律型DeepAgents実装の検証.md)
  - DeepAgents 明示入口の成立性は別文書で扱い、本書では route 境界のみ確認する。

## 検証で確認したいこと

### 1. 正常系

- `agent_chat` が SV 型の主入口として成立し、`run-ai-chat-util.sh` 経由で現行設定を読み込めること。
- absolute path を含む directory 確認要求が `general_tool_agent -> analyze_files` 経路へ入り、approval 必要時に deterministic に `paused` へ収束すること。
- pause 応答で `trace_id` を追跡でき、[A-02-02_Resumeプロトコルの検証.md](./A-02-02_Resumeプロトコルの検証.md) で確認済みの same `trace_id` resume 契約へ接続できること。
- 深掘り要求では `deep_agent` へ切り替わり、単発確認要求との境界を維持できること。

### 2. 異常系

- approval 対象ツールが未承認のまま実行完了し、`completed` に収束しないこと。
- 単発 directory 確認要求が不必要に `deep_agent` へ流れず、SV 型の責務と自律型の責務が混ざらないこと。
- generic な directory 問い合わせの reason code 差異を、route と最終状態の成立性と混同しないこと。

### 3. 運用系

- `trace_id`、route、tool 選択、approval 状態、`final_status` を audit log から再構成できること。
- `structured-routing` と `structured-routing-hitl` の設定切替で検証観点を切り分けられること。
- resume は API / ライブラリ経路を正本とし、CLI 単体のプロセス跨ぎ再開には制約があることを明示できること。

## 対象構成

| 観点 | 主な既存実装 / 入口 | 備考 |
| --- | --- | --- |
| CLI 入口 | `${HOME}/source/repos/ai-chat-util/app/src/ai_chat_util/cli/__main__.py` の `agent_chat` | SV 型の主入口 |
| API 入口 | `${HOME}/source/repos/ai-chat-util/app/src/ai_chat_util/api/api_server.py` の `agent_chat` | FastAPI 経由 |
| MCP / facade | `${HOME}/source/repos/ai-chat-util/app/src/ai_chat_util/core/app.py` の `run_agent_chat` | 共通 facade |
| Supervisor 本体 | `${HOME}/source/repos/ai-chat-util/app/src/ai_chat_util/base/agent/agent_client.py`、`agent_client_util.py` | route 選択、tool 実行、統合 |
| 通常ツール MCP | `${HOME}/source/repos/ai-chat-util/app/src/ai_chat_util/mcp/mcp_server.py` | `get_loaded_config_info`、`analyze_files` などを公開 |
| coding-agent MCP | `${HOME}/source/repos/ai-chat-util/app/src/ai_chat_util/agent/coding/mcp/mcp_server.py` | `coding-agent` route の委譲先 |
| PoC runner | `${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/run-ai-chat-util.sh` | `.env` から鍵を読み、`ai_chat_util.cli` を起動 |
| structured routing 設定 | `${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.poc.yml` | `deep_agent` 境界確認用 |
| structured routing + HITL 設定 | `${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.hitl.poc.yml` | `analyze_files` の approval 停止確認用 |

## 前提条件

- `${HOME}/source/repos/ai-chat-util/app` の依存が導入済みであること。
- `${HOME}/source/repos/ai-platform-poc/infra/02-litellm/.env` に `LITELLM_MASTER_KEY` と `LLM_API_KEY` が存在すること。
- LiteLLM Proxy が `http://localhost:4000` で利用可能であること。
- `${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/mcp_servers.local.json` で `normal-tools` と `coding-agent` の server key が解決できること。
- approval 停止の固定回帰シナリオでは `structured-routing-hitl` 設定を使い、deep_agent 境界確認では `structured-routing` 設定を使うこと。
- same `trace_id` を使う再開の厳密な契約確認は [A-02-02_Resumeプロトコルの検証.md](./A-02-02_Resumeプロトコルの検証.md) を正本とし、本書では SV 型上の pause と再開接続点を確認対象にする。

## 検証手順

検証は、設定確認、approval 固定シナリオ、pause 後の再開キー確認、補助シナリオ、deep_agent 境界確認の順で実施する。`fresh run` と `same trace_id resume` は混ぜずに記録する。

### 1. 事前準備

```bash
export AI_CHAT_UTIL_ROOT="${HOME}/source/repos/ai-chat-util/app"
export AI_PLATFORM_POC_ROOT="${HOME}/source/repos/ai-platform-poc"
export AI_CHAT_UTIL_RUNNER="$AI_PLATFORM_POC_ROOT/infra/31-ai-chat-util-mcp/run-ai-chat-util.sh"
export AI_CHAT_UTIL_CONFIG_HITL="$AI_PLATFORM_POC_ROOT/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.hitl.poc.yml"
export AI_CHAT_UTIL_CONFIG_ROUTING="$AI_PLATFORM_POC_ROOT/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.poc.yml"

cd "$AI_CHAT_UTIL_ROOT"
uv sync
```

期待結果:

- `ai-chat-util` の依存同期に失敗しない。
- 以降の手順で使う runner と config の場所を固定できる。

### 2. 設定読み込みを確認する

```bash
"$AI_CHAT_UTIL_RUNNER" --config "$AI_CHAT_UTIL_CONFIG_HITL" show_config
```

期待結果:

- 設定ファイルの読み込みに失敗しない。
- `routing_mode: structured`、`audit_log_enabled: true`、`hitl_approval_tools: [analyze_files]` を確認できる。
- `mcp_config_path` と `coding_agent_endpoint.mcp_server_name` が意図した値になっている。

### 3. approval 停止の固定シナリオを確認する

approval 停止は generic な問い合わせではなく、absolute path を含む directory 確認要求を正本シナリオとする。これは `general_tool_agent -> analyze_files -> paused` の再現性が最も高いためである。

```bash
"$AI_CHAT_UTIL_RUNNER" \
  --config "$AI_CHAT_UTIL_CONFIG_HITL" \
  agent_chat \
  -p "/home/user/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/work ディレクトリを確認してください"
```

期待結果:

- `general_tool_agent` が選択される。
- `analyze_files` が approval 対象として扱われる。
- 最終状態が `completed` ではなく `paused` になる。
- 応答またはログから `trace_id` を取得できる。

### 4. audit log で停止理由を確認する

```bash
tail -n 20 "${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/work/structured-routing-hitl-audit.jsonl"
```

期待結果:

- `route_decided.route_name: general_tool_agent` を確認できる。
- `route_decided.reason_code: route.explicit_directory_path_request` を確認できる。
- `tool_selected.tool_name: analyze_files` を確認できる。
- `tool_result_received.reason_code: hitl.tool_approval_required` を確認できる。
- `final_status: paused` を確認できる。

### 5. pause 後の再開接続点を確認する

SV 型としては、pause 応答で返された `trace_id` を使って次ターンへ接続できることを確認対象にする。厳密な resume 契約の live / test は [A-02-02_Resumeプロトコルの検証.md](./A-02-02_Resumeプロトコルの検証.md) を併用する。

確認ポイント:

- pause 応答に `trace_id` が含まれること。
- same `trace_id` による再送が必要な運用であることを説明できること。
- CLI 単体のプロセス跨ぎ再開ではなく、API / ライブラリ利用を正本とすること。

### 6. generic な directory 確認要求を補助確認する

```bash
"$AI_CHAT_UTIL_RUNNER" \
  --config "$AI_CHAT_UTIL_CONFIG_HITL" \
  agent_chat \
  -p "work ディレクトリを確認してください"
```

期待結果:

- 現行実装では `general_tool_agent -> analyze_files -> paused` が再現する。
- ただし reason code は `route.general_tool_sufficient` 系になる場合があり、absolute path シナリオと同一のラベルを合格条件にはしない。

### 7. deep_agent との境界を確認する

探索要求は approval 固定シナリオと分離し、`structured-routing` 設定で境界のみ確認する。

```bash
"$AI_CHAT_UTIL_RUNNER" \
  --config "$AI_CHAT_UTIL_CONFIG_ROUTING" \
  agent_chat \
  -p "work ディレクトリ全体を起点に深く調査してください"
```

期待結果:

- `deep_agent` が選択される。
- `route_decided.reason_code: route.multi_step_investigation_needed` を確認できる。
- 単発確認要求と異なる経路に入ることを確認できる。

補足:

- 現行実装では、`deep_agent` 側の directory path 解釈により `final_status: paused` や `needs_user_input` に倒れる場合があるため、このステップでは route 境界の確認を主判定とする。

## 判定基準

| 観点 | 判定基準 |
| --- | --- |
| 構造成立性 | `agent_chat`、structured routing、HITL 設定、MCP 接続、audit log 出力先が現行構成で噛み合っている。 |
| 制御成立性 | absolute path を含む directory 確認要求で `general_tool_agent -> analyze_files -> paused` が成立し、探索要求では `deep_agent` へ切り替わる。deep_agent 側の内容品質評価は A-04-04 / A-04-06 の対象として切り分けられている。 |
| 運用成立性 | `trace_id`、route、tool 名、approval 理由、`final_status` を監査ログから再構成でき、resume 接続点は [A-02-02_Resumeプロトコルの検証.md](./A-02-02_Resumeプロトコルの検証.md) の正本契約と矛盾しない。 |

## 検証結果記録欄

### 2026-04-07 仕様追随整理

ai-chat-util チームへの調査結果と PoC 側の追加再検証を反映し、A-04-03 の受け入れ条件を更新した。

確認済みの要点:

- approval 停止制御は、`analyze_files` を approval 対象にした場合に deterministic に `paused` へ寄せる修正方針が共有され、PoC 側でも targeted test と live シナリオで追随確認できている。
- approval の固定回帰シナリオとしては、absolute path を含む directory 確認要求を正本にするのが最も安定している。
- generic な `work ディレクトリ` 問い合わせも現行実装では `paused` へ入るが、reason code は explicit-directory 系に揃わないことがある。
- 深掘り要求では `deep_agent` に寄る境界が維持されている。

| 項目 | 結果 | 補足 |
| --- | --- | --- |
| `agent_chat` 主入口 | 確認済み | `run-ai-chat-util.sh` と `show_config` で現行設定を読み込める。 |
| approval 停止固定シナリオ | 確認済み | absolute path 付き問い合わせで `general_tool_agent -> analyze_files -> paused` を再現できる。 |
| generic directory 問い合わせ | 一部確認済み | route と `paused` は再現したが、reason code は汎用ラベルになる場合がある。 |
| deep_agent 境界 | 一部確認済み | 深掘り要求では `route.multi_step_investigation_needed` で `deep_agent` に入るが、deep_agent 側の path 解釈により `completed` ではなく `paused` に倒れる場合がある。 |
| same `trace_id` resume | 参照あり | 契約の正本は A-02-02 とし、本書では pause と再開接続点の確認まで扱う。 |

### 2026-04-08 live 実測結果

実行コマンド:

```bash
export AI_PLATFORM_POC_ROOT="${HOME}/source/repos/ai-platform-poc"
export AI_CHAT_UTIL_RUNNER="$AI_PLATFORM_POC_ROOT/infra/31-ai-chat-util-mcp/run-ai-chat-util.sh"
export AI_CHAT_UTIL_CONFIG_HITL="$AI_PLATFORM_POC_ROOT/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.hitl.poc.yml"
export AI_CHAT_UTIL_CONFIG_ROUTING="$AI_PLATFORM_POC_ROOT/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.poc.yml"

"$AI_CHAT_UTIL_RUNNER" --config "$AI_CHAT_UTIL_CONFIG_HITL" show_config
"$AI_CHAT_UTIL_RUNNER" --config "$AI_CHAT_UTIL_CONFIG_HITL" agent_chat -p "/home/user/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/work ディレクトリを確認してください"
"$AI_CHAT_UTIL_RUNNER" --config "$AI_CHAT_UTIL_CONFIG_HITL" agent_chat -p "work ディレクトリを確認してください"
"$AI_CHAT_UTIL_RUNNER" --config "$AI_CHAT_UTIL_CONFIG_ROUTING" agent_chat -p "work ディレクトリ全体を起点に深く調査してください"
```

実行結果:

- `show_config` は `/home/user/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.hitl.poc.yml` を返し、`routing_mode: structured`、`audit_log_enabled: true`、`hitl_approval_tools: [analyze_files]` を確認できた。
- absolute path シナリオでは trace_id `5d8c0fc51d3a4078895d0196ea06b924` を確認した。
  - 標準出力では `Approval-required tool evidence detected; forcing paused HITL response` が出力された。
  - audit log では `route_decided.route_name: general_tool_agent`、`route_decided.reason_code: route.explicit_directory_path_request`、`tool_selected.tool_name: analyze_files`、`tool_result_received.reason_code: hitl.tool_approval_required`、`final_status: paused` を確認した。
- generic シナリオでは trace_id `1ff4a515816a4b62b95bef3178c0f07c` を確認した。
  - audit log では `route_decided.route_name: general_tool_agent`、`route_decided.reason_code: route.general_tool_sufficient`、`tool_selected.tool_name: analyze_files`、`final_status: paused` を確認した。
  - したがって、経路と停止状態は再現したが、reason code は explicit-directory 系に揃わなかった。
- deep investigation シナリオでは trace_id `e4e63e84e13a4d0eb8f07c29d48d1ad2` を確認した。
  - audit log では `route_decided.route_name: deep_agent`、`route_decided.reason_code: route.multi_step_investigation_needed` を確認した。
  - その後 `deep_agent` が `/home/user/source/repos/ai-platform-poc/work` を対象に `analyze_files` を呼び、`Path not found` により `sufficiency.missing_user_context`、`final_status: paused` へ収束した。
  - したがって、route 境界は確認できたが、`completed` 収束は deep_agent 側の path 解釈品質に依存する現状を再確認した。

### 2026-04-08 ai-chat-util チーム回答反映

[ai-chat-utilチーム調査依頼_完了_A-04-04_DeepAgentsのdirectory path解釈と展開品質.md](../99_その他/ai-chat-utilチーム調査依頼_完了_A-04-04_DeepAgentsのdirectory path解釈と展開品質.md) への回答により、DeepAgents 側の absolute directory path 問題は directory expansion 本体ではなく、`explicit_user_directory_paths` が DeepAgents 実行経路へ十分に伝播していなかったことが主因と整理された。

本書への含意:

- A-04-03 の deep_agent 境界確認で観測した内容品質の不安定さは、少なくとも今回の absolute path ケースについては upstream で root cause と修正方針が特定済みである。
- upstream 追試では trace_id `62638961c2e440dda57eade28caa7468` で `analyze_files` が `docs` 配下 20 件を解析し、共通見出し要約まで到達している。
- したがって、本書の deep_agent 関連残件は「原因不明の品質問題」ではなく、「修正版 ai-chat-util 取り込み後に SV 型 route 境界シナリオを再測定すること」に更新する。

### 2026-04-08 resume 正本参照更新

same `trace_id` resume については、本書単独の live 完走ではなく、A-02-02 の正本判定と PoC 側 BFF 実装整合で受け入れ判断する。

確認内容:

- [A-02-02_Resumeプロトコルの検証.md](./A-02-02_Resumeプロトコルの検証.md) では、2026-04-05 実施の targeted test により、approval pause 後に同一 `trace_id` / `thread_id` で再開できることを確認済みである。
- [app/ai-platform-samplelib/src/ai_platform_samplelib/bff/api/api_server.py](../../app/ai-platform-samplelib/src/ai_platform_samplelib/bff/api/api_server.py#L34) では execute 時に BFF 発行 `trace_id` を LangGraph 側 `thread_id` へマップし、[app/ai-platform-samplelib/src/ai_platform_samplelib/bff/api/api_server.py](../../app/ai-platform-samplelib/src/ai_platform_samplelib/bff/api/api_server.py#L102) では同じ `trace_id` を resume API の `thread_id` として再送する実装になっている。
- したがって、A-04-03 として要求するのは「SV 型 pause 応答から same `trace_id` resume 契約へ接続できること」までであり、その正当性は A-02-02 正本と PoC BFF 実装で担保される。

| 項目 | 結果 | 補足 |
| --- | --- | --- |
| 設定読み込み確認 | 確認済み | `show_config` で HITL 用 config の concrete value を確認した。 |
| absolute path approval 停止 | 確認済み | trace_id `5d8c0fc51d3a4078895d0196ea06b924`。`general_tool_agent -> analyze_files -> paused` を live で再現した。 |
| generic directory 停止 | 確認済み | trace_id `1ff4a515816a4b62b95bef3178c0f07c`。`paused` は再現した。reason code のラベル差は隣接論点だが、本書の成立判定は満たす。 |
| deep_agent route 境界 | 確認済み | trace_id `e4e63e84e13a4d0eb8f07c29d48d1ad2` で route 境界を確認した。deep_agent 側の内容品質は A-04-04 / A-04-06 へ切り分ける。 |
| pause 後の再開接続点 | 確認済み | absolute path / generic の両シナリオで pause 応答と trace_id を確認した。same `trace_id` resume 契約の正本は A-02-02 と BFF 実装整合で確認した。 |

### 2026-04-09 A-03-03 checklist 適用

本書の evidence を [A-03-03_テスト再現評価ハーネスの検証.md](./A-03-03_テスト再現評価ハーネスの検証.md) の review checklist に沿って整理すると、次のとおりである。

| 観点 | 記録内容 | 判定 |
| --- | --- | --- |
| 相関情報 | trace_id `5d8c0fc51d3a4078895d0196ea06b924`、`1ff4a515816a4b62b95bef3178c0f07c`、`e4e63e84e13a4d0eb8f07c29d48d1ad2`、config path を記録済み | OK |
| 自動テスト | 本書の主眼は live route / pause 契約であり、resume 正本は A-02-02、deep_agent 内容品質は A-04-04 / A-04-06 を参照する構成を明示済み | OK |
| 再現材料 | `show_config`、absolute path、generic、deep investigation の具体 command と audit 観点を記録済み | OK |
| 成果物 | route_name、reason_code、tool_selected、final_status、pause 応答 trace_id を回収済み | OK |
| 副作用統制 | approval 対象ツールは `paused` に収束し、resume 契約は A-02-02 正本へ接続する整理 | OK |
| レビュー判断 | SV 型 LangGraph 主入口として acceptance 条件を満たす | Accept |

判断理由:

- 本書の対象は route / approval / pause / resume 接続点の成立性であり、live 実測と正本参照先の切り分けが明確である。
- deep_agent 側の内容品質や cross-cutting な停止条件は別文書へ切り分け済みであり、本書スコープの implementation acceptance は成立すると判断できる。

## 残課題

- A-04-03 の受け入れ条件に対する残課題はなし。
- なお、generic な directory 問い合わせの reason code ラベル整理は別論点であり、routing ラベル設計として扱う。
- deep_agent 側の directory path 解釈品質と内容品質は A-04-04 / A-04-06 側で継続確認する。
- same `trace_id` resume の厳密な end-to-end 検証は A-02-02 の正本として継続管理する。

