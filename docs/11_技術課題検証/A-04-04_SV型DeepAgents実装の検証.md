# A-04-04_SV型DeepAgents実装の検証

## 検証目的

本検証の主目的は、サブ課題 A-04-04「SV型エージェントの実装検証（DeepAgents実装）」について、PoC 環境で成立性を確認することである。

最終的には、A-04 の完了判定に必要な材料として、DeepAgents を用いた Supervisor 型構成で、役割分担、合議、探索制御、制約付与がどこまで成立するかを明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| A-04 | A-04-04 | DeepAgents を用いた Supervisor 型構成で、役割分担、合議、探索制御、制約付与が成立するかを確認する。 |

必要に応じて、副次的に A-01-02、A-03-02 の前提整理にも利用する。

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../03_検証準備/01_技術課題と対応方針.md)
  - A-04-04 に対応し、DeepAgents を SV 型の実装基盤として採用できるかを確認する。
- [生成AIアプリケーション層の実現方式](../02_アーキテクチャ実現方式/02_生成AIアプリケーション層の実現方式.md)
  - SV 型の代表基盤として LangGraph に加えて上位ライブラリ活用余地がある整理を参照する。
- [02_AIエージェントの業務適用を見据えた生成AIアプリケーション層の検討.md](../01_アーキテクチャ検討/02_AIエージェントの業務適用を見据えた生成AIアプリケーション層の検討.md)
  - SV 型 / 自律型の基盤候補として DeepAgents を挙げている。
- `${HOME}/source/repos/ai-chat-util/README_FOR_EXPERTS.md`
  - `run_deepagent_chat` と `deep_agent` route の記述を既存実装根拠として参照する。

## 検証で確認したいこと

### 1. 正常系

- DeepAgents を明示的な入口として起動できること。
- Supervisor 的な役割分担や複数段の調査を DeepAgents で実行できること。
- 利用可能ツールの allowlist や制約条件を付与できること。

### 2. 異常系

- すべての要求を DeepAgents へ流し込む運用に退化しないこと。
- 非同期ジョブ系や外部作用の強い要求で fallback 条件を説明できること。
- DeepAgents が使えるからといって、監査や停止条件が不要になるわけではないことを明示できること。

### 3. 運用系

- `deep_agent` route の選択理由と使用ツールを監査できること。
- extra dependency の導入条件や有効化設定を整理できること。
- LangGraph 独自実装との差分を、開発効率と制御性の観点で説明できること。

## 対象構成

| 観点 | 主な既存実装 / 入口 | 備考 |
| --- | --- | --- |
| 明示入口 | `${HOME}/source/repos/ai-chat-util/README_FOR_EXPERTS.md` に記載の `run_deepagent_chat` | CLI / API / FastMCP 入口 |
| supervisor 内 route | `${HOME}/source/repos/ai-chat-util/app/src/ai_chat_util/base/agent/agent_client_util.py` の `deep_agent` route | SV 型内部の委譲先 |
| 追加依存 | `${HOME}/source/repos/ai-chat-util/README.md` の `uv sync --extra deepagents` | DeepAgents 有効化条件 |
| 設定 | structured routing config、`enable_deep_agent: true`、`preferred_coding_route: deep_agent` | route 制御に利用 |

## 既存実装と入口の対応づけ

1. 明示入口

- `run_deepagent_chat` は DeepAgents を明示的に起動する入口として README_FOR_EXPERTS で整理されている。

2. SV 型内部 route

- `agent_chat` の structured routing で `deep_agent` route を選択できる。
- これは SV 型内部で DeepAgents を利用する構成であり、純粋な standalone 自律型とは別である。

3. 制約付与

- allowlist されたツール群のみを DeepAgents 側へ渡す前提である。
- async job 型の `execute` / `status` / `get_result` は初期実装では対象外としている。

## 前提条件

- `${HOME}/source/repos/ai-chat-util/app` で `uv sync --extra deepagents` が完了していること。
- structured routing 設定を利用できること。
- 必要に応じて MCP / LiteLLM が起動済みであること。

## 検証手順

### 1. 事前準備

```bash
cd ${HOME}/source/repos/ai-chat-util/app
uv sync --extra deepagents
```

### 2. 正常系確認

```bash
cd ${HOME}/source/repos/ai-chat-util
uv --directory ./app run -m ai_chat_util.cli \
  --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.poc.yml \
  agent_chat -p "deep-agent を使って docs 配下の共通見出しを段階的に調査してください"
```

期待結果:

- `deep_agent` route が選択される。
- 複数段の調査が DeepAgents 系実装で実行される。

### 3. 異常系確認

期待結果:

- 非同期ジョブ系や強い副作用を要する要求では fallback 条件が説明できる。
- DeepAgents が不適切な場合に別経路へ逃がせる。

## 判定基準

| 観点 | 判定基準 |
| --- | --- |
| 構造成立性 | DeepAgents を SV 型の一実装基盤として位置付ける入口と設定が存在する。 |
| 制御成立性 | route 選択、allowlist、fallback 条件を含めた制御を説明できる。 |
| 運用成立性 | 追加依存、設定、監査観点を文書化し、LangGraph 独自実装との差分を整理できる。 |

## 検証結果記録欄

### 2026-04-05 実測結果

実行コマンド:

```bash
cd ${HOME}/source/repos/ai-chat-util/app
uv run pytest src/ai_chat_util/_test_/test_deepagent_entrypoints.py -q
```

実行結果:

- `10 passed in 6.68s`
- 次の観点を確認した。
  - `run_deepagent_chat` が DeepAgent factory を利用すること。
  - CLI parser が `run_deepagent_chat` と batch 系コマンドを受理すること。
  - API router に `run_deepagent_chat` / batch 系 route が登録されること。
  - MCP 側に `run_deepagent_chat` と batch 系 tool が公開されること。

補足:

- 今回の実測は入口契約の確認が中心であり、structured routing から `deep_agent` route が選ばれる end-to-end 実行までは行っていない。

| 項目 | 結果 | 補足 |
| --- | --- | --- |
| 正常系 | 一部確認済み | DeepAgents の CLI / API / MCP 入口テスト 10 件が通過した。 |
| 異常系 | 一部確認済み | 入口未登録や parser 未対応のような基本破綻がないことは確認済み。fallback 条件の end-to-end 確認は未実施。 |
| 運用系 | 一部確認済み | 追加依存導入後の公開契約は確認済み。監査出力や route 選択結果の実測は未実施。 |

### 2026-04-07 追試結果

実装・設定の確認:

- `README_FOR_EXPERTS.md` には、`run_deepagent_chat` を CLI / API / FastMCP から利用できること、`deep_agent` route でも `route_decided` / `tool_catalog_resolved` / `final_answer_validated` の audit event が維持されることが明記されている。
- `deep_agent_support.py` では、`deep_agent` route に `deepagents` パッケージが必須であり、system prompt 上も `execute` / `status` / `get_result` / `workspace_path` / `cancel` を使わない制約が固定されている。
- `agent_client_util.py` では、`routing_decision.selected_route == "deep_agent"` の場合に `create_deep_agent_workflow()` を構築し、`tool_catalog_resolved` に DeepAgents 側へ公開したツール一覧を記録する実装になっている。

回帰テスト実行コマンド 1:

```bash
cd ${HOME}/source/repos/ai-chat-util/app
uv run pytest src/ai_chat_util/_test_/test_deepagent_entrypoints.py -q
```

実行結果:

- `10 passed in 11.76s`
- CLI / API / MCP の明示入口契約は引き続き維持されている。

回帰テスト実行コマンド 2:

```bash
cd ${HOME}/source/repos/ai-chat-util/app
uv run pytest src/ai_chat_util/base/agent/_test_/test_tool_guard_wrapping.py -q \
  -k 'mcp_client_chat_emits_deep_agent_audit_events or default_routing_prefers_deep_agent_for_explicit_request_when_enabled or default_routing_does_not_select_deep_agent_when_disabled'
```

実行結果:

- `2 passed, 1 failed, 120 deselected`
- `default_routing_prefers_deep_agent_for_explicit_request_when_enabled`
- `default_routing_does_not_select_deep_agent_when_disabled`
  は通過した。
- 一方で `test_mcp_client_chat_emits_deep_agent_audit_events` は `ModuleNotFoundError: No module named 'ai_chat_util.base.agent.mcp_client'` で失敗した。

評価:

- DeepAgents の route 優先・無効化境界の回帰は維持されている。
- ただし audit event の自動テストには、現行モジュール構成に追随できていない既存失敗が残っている。

live 実行コマンド 1: supervisor 内 route としての DeepAgents

```bash
cd ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp
./run-ai-chat-util.sh --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.poc.yml \
  agent_chat -p "deep-agent を使って docs 配下の共通見出しを段階的に調査してください"
```

実行結果:

- `trace_id=86aa28f636f14b27bfae1d6dc883979a`
- `route_decided.route_name=deep_agent`
- `route_decided.reason_code=route.multi_step_investigation_needed`
- `tool_catalog_resolved.payload.tool_agent_names=["deep_agent"]`
- `tool_catalog_resolved.payload.tool_catalog[0].tool_names=["healthz", "get_loaded_config_info", "analyze_files", "analyze_pdf_files", "analyze_image_files"]`
- `final_status=completed`

評価:

- structured routing 配下で `deep_agent` backend が live に選択され、監査ログにも DeepAgents 専用の tool catalog が記録されることを確認した。
- 一方で最終応答は `docs` 配下を見つけられず、内容面では期待した「共通見出しの段階的調査」には至らなかった。

live 実行コマンド 2: DeepAgents 明示入口

```bash
cd ${HOME}/source/repos/ai-chat-util
uv --directory ./app run -m ai_chat_util.cli \
  --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.poc.yml \
  run_deepagent_chat -p "docs 配下の共通見出しを段階的に調査してください"
```

実行結果:

- `trace_id=76e8ccfaf36c4d0796c6fcbe5dfc7c9e`
- `route_decided.route_name=deep_agent`
- `route_decided.payload.forced_route=deep_agent`
- `tool_catalog_resolved.payload.tool_agent_names=["deep_agent"]`
- `final_status=completed`

評価:

- `run_deepagent_chat` の明示入口でも、supervisor 内 route ではなく forced deep route として実行されることを監査ログで確認した。
- 明示入口と SV 型内部 route の使い分けは、`forced_route=deep_agent` の有無で区別できる。

live 実行コマンド 3: DeepAgents 明示入口 + absolute path

```bash
cd ${HOME}/source/repos/ai-chat-util
uv --directory ./app run -m ai_chat_util.cli \
  --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.poc.yml \
  run_deepagent_chat -p "/home/user/source/repos/ai-platform-poc/docs ディレクトリを段階的に調査し、共通見出しの傾向を説明してください"
```

実行結果:

- `trace_id=eacb0a96bb2c4b59a8c234d4f9ba9412`
- `route_decided.route_name=deep_agent`
- `route_decided.payload.forced_route=deep_agent`
- `route_decided.payload.explicit_user_directory_paths=["/home/user/source/repos/ai-platform-poc/docs"]`
- `tool_catalog_resolved.payload.tool_agent_names=["deep_agent"]`
- `final_status=completed`

評価:

- absolute path を明示しても、DeepAgents 明示入口は expected route と audit contract を維持した。
- ただし当時の応答本文は `docs` ディレクトリを空と見なしており、PoC 追試時点では DeepAgents 実行経路に追加確認事項が残っていた。

### 2026-04-08 ai-chat-util チーム回答反映

PoC 側から起票した [ai-chat-utilチーム調査依頼_完了_A-04-04_DeepAgentsのdirectory path解釈と展開品質.md](../99_その他/ai-chat-utilチーム調査依頼_完了_A-04-04_DeepAgentsのdirectory path解釈と展開品質.md) に対する回答を受領した。

回答要旨:

- root cause は directory expansion 本体ではなく、DeepAgents 実行経路で `explicit_user_directory_paths` が `create_deep_agent_workflow()` と tool 解決経路へ十分に伝播していなかったことだった。
- `deep_agent_support.py` の prompt 意図に対して、実行文脈側で concrete target が弱く、`analyze_files` を打たずに「空」「未検出」と要約できてしまう余地があった。
- さらに sufficiency 判定も、実質的な tool evidence が弱い absence claim を `complete` とみなしやすく、誤結論を残しやすかった。

upstream 修正内容:

- DeepAgents 作成時に `explicit_user_directory_paths` を伝播
- system prompt に明示 directory path を concrete target として埋め込み
- directory path を `analyze_files` へそのまま渡すよう指示を明確化
- tool evidence の弱い「空」「未検出」断定を `complete` 扱いしにくいよう sufficiency 判定を補強

upstream 再現確認結果:

- trace_id `62638961c2e440dda57eade28caa7468`
- `route_decided.route_name=deep_agent`
- `explicit_user_directory_paths=["/home/user/source/repos/ai-platform-poc/docs"]`
- `analyze_files` が実際に呼び出され、`docs` 配下 20 件を解析
- 最終応答は「空です」「見つかりませんでした」ではなく、共通見出し傾向の要約に到達

評価:

- A-04-04 で切り出していた absolute directory path 問題は、DeepAgents 実行経路の文脈伝播不足が主因だったことが確認できた。
- したがって、本サブ課題の残件は「原因不明の path 品質問題」ではなく、「修正版 ai-chat-util を PoC 側へ取り込んだうえで同一シナリオを再実測すること」に整理し直す。

総合評価:

- DeepAgents の CLI / API / MCP 明示入口、SV 型内部 route、audit contract、enable/disable の基本境界は確認できた。
- `deep_agent` route が `execute` / `status` / `get_result` を使わず、非同期ジョブ系を `coding_agent` 側へ残す設計根拠も、README と system prompt 実装で確認できた。
- 既存ディレクトリを空または未検出と返した live 事象については、upstream から root cause と修正内容の回答を受領した。PoC 側では修正版取り込み後の再実測が残る。

### 2026-04-08 修正版取り込み後の PoC 再実測

absolute directory path 問題の残件として、修正版 ai-chat-util を取り込んだ現行環境で PoC 側の同一シナリオを再実行した。

実行コマンド 1: DeepAgents 明示入口 + absolute path

```bash
cd ${HOME}/source/repos/ai-chat-util
uv --directory ./app run -m ai_chat_util.cli \
  --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.poc.yml \
  run_deepagent_chat -p "/home/user/source/repos/ai-platform-poc/docs ディレクトリを段階的に調査し、共通見出しの傾向を説明してください"
```

実行結果:

- `trace_id=b1d564912a1347eb9dc396293edfbb85`
- `route_decided.route_name=deep_agent`
- `route_decided.payload.forced_route=deep_agent`
- `route_decided.payload.explicit_user_directory_paths=["/home/user/source/repos/ai-platform-poc/docs"]`
- `tool_selected.tool_name=analyze_files`
- `tool_result_received.payload.success=true`
- `final_answer_validated.reason_code=sufficiency.answer_supported_by_evidence`
- `final_status=completed`

評価:

- `run_deepagent_chat` の明示入口で、absolute directory path が `explicit_user_directory_paths` として監査ログへ残り、`analyze_files` による 20 件解析の後に共通見出し傾向の要約まで到達した。
- 2026-04-07 時点で観測していた「`docs` を空または未検出とみなす」事象は、この PoC 再実測では再現しなかった。

実行コマンド 2: SV 型内部 route + absolute path

```bash
cd ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp
./run-ai-chat-util.sh \
  --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.poc.yml \
  agent_chat -p "deep-agent を使って /home/user/source/repos/ai-platform-poc/docs ディレクトリを段階的に調査し、共通見出しの傾向を説明してください"
```

実行結果:

- `trace_id=cc93fa4661c84c6d8cad0713cb7a746d`
- `route_decided.route_name=deep_agent`
- `route_decided.reason_code=route.multi_step_investigation_needed`
- `route_decided.payload.forced_route=null`
- `route_decided.payload.explicit_user_directory_paths=["/home/user/source/repos/ai-platform-poc/docs"]`
- `tool_selected.tool_name=analyze_files`
- `tool_result_received.payload.success=true`
- `final_answer_validated.reason_code=sufficiency.answer_supported_by_evidence`
- `final_status=completed`

評価:

- supervisor 内 route としての `deep_agent` でも、同じ absolute directory path が正しく伝播し、`analyze_files` 実行結果に基づく要約応答まで到達した。
- `forced_route=deep_agent` を持つ明示入口と異なり、SV 型内部 route では `forced_route=null` のまま `route.multi_step_investigation_needed` で選択されており、両経路の使い分けも引き続き監査できる。

回帰テスト実行コマンド:

```bash
cd ${HOME}/source/repos/ai-chat-util/app
uv run pytest src/ai_chat_util/base/agent/_test_/test_tool_guard_wrapping.py -q \
  -k 'mcp_client_chat_emits_deep_agent_audit_events'
```

実行結果:

- `1 failed, 126 deselected`
- `test_mcp_client_chat_emits_deep_agent_audit_events` は `ModuleNotFoundError: No module named 'ai_chat_util.base.agent.mcp_client'` で失敗した。

評価:

- live の監査契約は明示入口・SV 型内部 route の両方で確認できており、absolute directory path 問題に関する PoC 側残件は解消した。
- 一方で監査回帰テストは、現行モジュール構成に追随できていない既存失敗が残る。これは live 挙動の不成立ではなく、テスト保守の残件として切り分ける。
- なお、2026-04-08 追加追試結果で観測した `/home/user/source/repos/ai-platform-poc/work` の `Path not found` は、現行 PoC ワークスペースに当該ディレクトリ自体が存在しないため、absolute directory path 修正の未解消根拠には使わない。

### 2026-04-08 ai-chat-util チーム回答反映（監査回帰 test）

[ai-chat-utilチーム調査依頼_完了_A-04-04_DeepAgents監査回帰testのimport追随.md](../99_その他/ai-chat-utilチーム調査依頼_完了_A-04-04_DeepAgents監査回帰testのimport追随.md) への回答により、`test_mcp_client_chat_emits_deep_agent_audit_events` 系の failure は DeepAgents 本体の監査契約不成立ではなく、旧 `mcp_client` / `mcp_client_util` 前提の test が現行 module 再編へ追随できていなかったことが主因と整理された。

確認できた点:

- test の import 先は現行 `agent_client.py` / `agent_client_util.py` を正本とすべきこと
- fake `decide_route` / `create_workflow` などの test double も現行呼び出しシグネチャへ追随が必要だったこと
- ai-chat-util チーム側では関連 5 テストが `5 passed, 122 deselected` で再通過したこと
- PoC 側でも同じ 5 テストを fresh rerun し、`5 passed, 122 deselected in 6.35s` を確認したこと

評価:

- A-04-04 の残件として切り分けていた DeepAgents 監査回帰 test 保守は解消した。
- absolute directory path 問題と監査回帰 test 問題の両方について、PoC 側の受け入れ判断を阻害する残件はなくなった。

### 2026-04-08 追加追試結果

SV 型の主入口 [A-04-03_SV型LangGraph独自実装の検証.md](./A-04-03_SV型LangGraph独自実装の検証.md) の追試として、structured routing 配下の deep investigation シナリオを再実行した。

実行コマンド:

```bash
cd ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp
./run-ai-chat-util.sh \
  --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.poc.yml \
  agent_chat -p "work ディレクトリ全体を起点に深く調査してください"
```

実行結果:

- `trace_id=e4e63e84e13a4d0eb8f07c29d48d1ad2`
- `route_decided.route_name=deep_agent`
- `route_decided.reason_code=route.multi_step_investigation_needed`
- `tool_catalog_resolved.payload.tool_agent_names=["deep_agent"]`
- `tool_selected.tool_name=analyze_files`
- `tool_result_received.reason_code=sufficiency.tool_result_error_only`
- `final_answer_validated.reason_code=sufficiency.missing_user_context`
- `final_status=paused`

評価:

- `deep_agent` への route 境界自体は live で再確認できた。
- 一方で DeepAgents 側は `/home/user/source/repos/ai-platform-poc/work` を対象に `analyze_files` を呼び、`Path not found` により user input 要求へ収束した。
- したがって、既知の「docs を空または未検出と返す」事象に加えて、`work` のような directory 指定でも path 解釈・展開品質に起因する失敗が再現した。
- 本文書では route と audit contract の成立性は維持すると判断するが、directory path の解釈品質は継続課題として扱う。

## 残課題

- A-04-04 の受け入れ条件に対する残課題はなし。DeepAgents 明示入口と SV 型内部 route の両方で、absolute directory path を含む `docs` 調査シナリオが PoC 側 live で再成立した。
- `run_deepagent_chat` と `agent_chat` の使い分け指針、停止条件、予算上限、監査出力の詳細運用基準は、別論点として継続整理の余地がある。
- 自律型としての DeepAgents は A-04-06 で別途整理する。