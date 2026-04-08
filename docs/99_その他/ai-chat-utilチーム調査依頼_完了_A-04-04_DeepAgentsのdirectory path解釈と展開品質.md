# ai-chat-util チーム調査依頼: DeepAgents が実在する absolute directory path を空または未検出と返す件

## 想定する issue タイトル

DeepAgents 入口 / `deep_agent` route で、実在する absolute directory path を与えても、空ディレクトリまたは未検出として扱われる条件を整理したい

## 概要

ai-platform-poc 側の A-04-04 検証で、DeepAgents の明示入口 `run_deepagent_chat` と SV 型内部 route の `deep_agent` を live 追試した。

その結果、route と audit contract 自体は期待どおり成立した一方、実在する absolute path `/home/user/source/repos/ai-platform-poc/docs` を対象にした調査要求で、応答本文が「ファイルが見つからない」または「空です」と収束し、期待した調査結果に至らなかった。

DeepAgents 実装の成立性とは別に、absolute directory path の解釈・展開品質の論点として切り出して確認したい。

## 背景

- 対象検証: A-04-04 SV 型 DeepAgents 実装の検証
- 既に確認できていること:
  - `run_deepagent_chat` の CLI / API / MCP 入口テスト 10 件は通過
  - structured routing 配下で `deep_agent` route が live に選択される
  - `tool_catalog_resolved` には `deep_agent` 側へ公開したツール一覧が記録される
  - `deep_agent` route は `execute` / `status` / `get_result` を使わない設計になっている

今回の論点は route 選択ではなく、DeepAgents が実在する absolute directory path をどう解釈し、配下の探索や `analyze_files` への引き渡しをどう行っているか、に限定される。

## 再現手順

### 1. DeepAgents 明示入口 + absolute path

absolute path の実在性が明確であり、相対パス解釈や working_directory の論点が混ざらない主再現ケースとして扱う。

```bash
cd ${HOME}/source/repos/ai-chat-util
uv --directory ./app run -m ai_chat_util.cli \
  --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.poc.yml \
  run_deepagent_chat -p "/home/user/source/repos/ai-platform-poc/docs ディレクトリを段階的に調査し、共通見出しの傾向を説明してください"
```

実測結果:

- trace_id: `eacb0a96bb2c4b59a8c234d4f9ba9412`
- `route_decided.route_name: deep_agent`
- `route_decided.payload.forced_route: deep_agent`
- `route_decided.payload.explicit_user_directory_paths: ["/home/user/source/repos/ai-platform-poc/docs"]`
- `tool_catalog_resolved.payload.tool_agent_names: ["deep_agent"]`
- `final_status: completed`
- CLI 応答本文:
  - `/home/user/source/repos/ai-platform-poc/docs ディレクトリは空です。ファイルが存在しないため、共通見出しの傾向を調査することはできません。`

評価:

- absolute path 自体は route payload に明示的に残っており、入力が欠落したわけではない。
- にもかかわらず、実在する `docs` ディレクトリが「空」と要約され、配下探索へ進めていない。

### 2. SV 型内部 route としての DeepAgents

relative path 由来の曖昧さを避けるため、ここでは absolute path が応答本文に現れる補助ケースとして扱う。

```bash
cd ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp
./run-ai-chat-util.sh --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.poc.yml \
  agent_chat -p "deep-agent を使って docs 配下の共通見出しを段階的に調査してください"
```

実測結果:

- trace_id: `86aa28f636f14b27bfae1d6dc883979a`
- `route_decided.route_name: deep_agent`
- `tool_catalog_resolved.payload.tool_agent_names: ["deep_agent"]`
- `final_status: completed`
- CLI 応答本文:
  - `指定されたディレクトリ "/home/user/source/repos/ai-platform-poc/docs" 内にファイルが見つかりませんでした。`

補足:

- 入力は `docs` だが、応答本文では absolute path `/home/user/source/repos/ai-platform-poc/docs` が参照されている。
- したがって、少なくとも最終段では absolute path を対象に未検出判定していることが分かる。

### 3. 相対パス入力の参考ケース

以下は挙動の参考として残すが、主論点にはしない。`docs` は `working_directory` 基準の相対パスとして解釈され得るため、absolute path 問題とは切り分ける。

```bash
cd ${HOME}/source/repos/ai-chat-util
uv --directory ./app run -m ai_chat_util.cli \
  --config ${HOME}/source/repos/ai-platform-poc/infra/31-ai-chat-util-mcp/ai-chat-util-config.structured-routing.poc.yml \
  run_deepagent_chat -p "docs 配下の共通見出しを段階的に調査してください"
```

実測結果:

- trace_id: `76e8ccfaf36c4d0796c6fcbe5dfc7c9e`
- `route_decided.route_name: deep_agent`
- `route_decided.payload.forced_route: deep_agent`
- `tool_catalog_resolved.payload.tool_agent_names: ["deep_agent"]`
- `final_status: completed`
- CLI 応答本文:
  - `指定されたパス 'docs/**' に一致するファイルやディレクトリは見つかりませんでした。パスを確認して再度お試しください。`

## 期待結果

- 実在する absolute directory path が与えられた場合、DeepAgents がその directory を空または不存在と誤判定しないこと
- `build_deep_agent_system_prompt()` の意図どおり、directory 指定を配下探索し、対象ファイルへ展開してから解析へ進むこと
- 少なくとも `/home/user/source/repos/ai-platform-poc/docs` のような実在する absolute directory に対しては、空判定ではなく何らかの配下ファイル解析結果へ到達すること

## 実装上の確認済み前提

- `deep_agent_support.py` の system prompt には、次が明記されている
  - absolute path が存在する場合はそのまま使う
  - directory path が指定された場合、file 指定として却下せず、存在確認のうえで配下を探索し、対象ファイルへ展開してから解析する
- `agent_client_util.py` では、`deep_agent` route に対して `healthz`, `get_loaded_config_info`, `analyze_files`, `analyze_pdf_files`, `analyze_image_files` が公開される

## 確認したいこと

1. DeepAgents 明示入口や `deep_agent` route で、実在する absolute directory path `/home/user/source/repos/ai-platform-poc/docs` が空または未検出と扱われる分岐はどこか
2. `analyze_files` に渡す前段で、directory の存在確認や配下探索がどこで失敗しているか
3. DeepAgents 側の planner / tool 呼び出しで、absolute directory path を「空」と要約してしまう誤推論が入り込んでいないか
4. absolute path の場合でも内部で `docs/**` のような glob 展開へ変形される条件は何か
5. 最小修正で改善するなら、prompt 側・tool wrapper 側・directory expansion 側のどこを直すのが妥当か

## 期待する回答

- 原因の切り分け
- 期待仕様に対して現行挙動がどこで外れているか
- 必要なら最小修正方針
- 再現用の最小ケース

## ai-chat-util チーム回答要約（2026-04-08）

結論:

- 今回の事象の主因は、directory path の存在判定や配下展開の実装そのものではなく、DeepAgents 実行経路で `explicit_user_directory_paths` の文脈が十分に引き継がれていなかったことである。
- `AnalysisService.resolve_existing_file_paths` による directory 展開本体は正常であり、absolute directory path 単体の処理系には直接の不具合は確認されなかった。

原因の整理:

1. DeepAgents 側で directory 文脈が落ちていた

- `agent_client_util.py` の DeepAgents 作成経路では、従来 `explicit_user_file_paths` は伝播していた一方、`explicit_user_directory_paths` は `create_deep_agent_workflow()` と `_resolve_deep_agent_tools()` に渡していなかった。
- そのため `route_decided` には absolute directory path が残っていても、DeepAgents 実行時には concrete target として弱く、`analyze_files` を呼ばずに「空」「未検出」と要約してしまう余地があった。

2. prompt の意図と実行文脈にズレがあった

- `deep_agent_support.py` には「absolute path はそのまま使う」「directory path は配下探索して解析する」という意図が記載されていた。
- しかし実行時 prompt には、今回の `explicit_user_directory_paths` 自体が concrete target として十分に埋め込まれていなかった。

3. sufficiency 判定が誤った absence claim を通しやすかった

- 具体的な tool evidence が弱くても本文があれば `complete` に寄りやすい条件があり、誤った「空」「未検出」結論が最終応答に残りやすい状態だった。

修正内容:

- DeepAgents 作成時に `explicit_user_directory_paths` を伝播するよう修正
- DeepAgents の system prompt に、明示された directory path を concrete target として埋め込むよう修正
- directory path はその path 自体を `analyze_files` に渡し、`docs/**` のような glob や child path へ勝手に変形しないよう指示を明確化
- 実質的な tool evidence がないのに「空」「未検出」と断定した `complete` を answerable 扱いしないよう sufficiency 判定を補強

修正ファイル:

- `agent_client_util.py`
- `deep_agent_support.py`
- `tool_limits.py`

追加テスト:

- `test_deep_agent_support.py`
- `test_tool_guard_wrapping.py`

修正後の再現確認:

- trace_id: `62638961c2e440dda57eade28caa7468`
- `route_decided.route_name: deep_agent`
- `explicit_user_directory_paths: ["/home/user/source/repos/ai-platform-poc/docs"]`
- DeepAgents が `analyze_files` を実際に呼び出すことを確認
- `analyze_files` は `docs` 配下 20 件を対象に解析を実行
- 最終応答は「空です」「見つかりませんでした」ではなく、共通見出し傾向の要約に到達

今回の論点に対する回答:

1. 実在 absolute directory path が空または未検出になる主分岐

- DeepAgents 実行時に `explicit_user_directory_paths` の文脈が落ちていた箇所が主因であり、directory expansion 本体ではなかった。

2. `analyze_files` 前段の失敗点

- directory の存在確認や配下探索そのものではなく、DeepAgents がその directory を `analyze_files` に適切に渡す前の文脈伝播不足だった。

3. planner / tool 呼び出しの誤推論有無

- concrete target が弱かったため、tool evidence なしに「空」「未検出」へ寄る誤推論余地が存在していた。

4. absolute path が `docs/**` のような glob へ変形される条件

- 少なくとも今回の根本原因はそこではなく、directory 自体を `analyze_files` に渡すべき場面で DeepAgents 側が適切な呼び出しへ到達していなかったことが主因だった。

5. 最小修正の妥当箇所

- prompt 単独ではなく、DeepAgents の tool wrapper / workflow 作成経路で `explicit_user_directory_paths` を渡す修正が本命だった。
- これに加えて、誤った absence claim を `complete` で通しにくくする sufficiency 側補強が妥当と整理された。

PoC 側の含意:

- A-04-04 / A-04-06 / A-04-03 で観測した DeepAgents の directory path 品質課題は、少なくとも今回の absolute path ケースについては root cause と修正方針が upstream で特定された。
- PoC 側の次アクションは、修正版 ai-chat-util の取り込み後に同一シナリオを再実行し、`deep_agent` route 配下でも `analyze_files` 実呼び出しと内容要約到達を再確認することである。

## 関連文書

- `/home/user/source/repos/ai-platform-poc/docs/11_技術課題検証/A-04-04_SV型DeepAgents実装の検証.md`
- `/home/user/source/repos/ai-platform-poc/docs/11_技術課題検証/A-04-03_SV型LangGraph独自実装の検証.md`
- `/home/user/source/repos/ai-chat-util/README_FOR_EXPERTS.md`
- `/home/user/source/repos/ai-chat-util/app/src/ai_chat_util/base/agent/deep_agent_support.py`
