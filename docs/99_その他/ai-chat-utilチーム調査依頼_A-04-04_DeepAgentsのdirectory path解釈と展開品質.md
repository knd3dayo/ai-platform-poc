# ai-chat-util チーム調査依頼: DeepAgents が既存ディレクトリを空または未検出と返す件

## 想定する issue タイトル

DeepAgents 入口 / `deep_agent` route で既存 directory path を与えても、空ディレクトリまたは未検出として扱われる条件を整理したい

## 概要

ai-platform-poc 側の A-04-04 検証で、DeepAgents の明示入口 `run_deepagent_chat` と SV 型内部 route の `deep_agent` を live 追試した。

その結果、route と audit contract 自体は期待どおり成立した一方、既存の `docs` ディレクトリを対象にした調査要求で、応答本文が「ファイルが見つからない」または「空です」と収束し、期待した調査結果に至らなかった。

DeepAgents 実装の成立性とは別に、directory path の解釈・展開品質の論点として切り出して確認したい。

## 背景

- 対象検証: A-04-04 SV 型 DeepAgents 実装の検証
- 既に確認できていること:
  - `run_deepagent_chat` の CLI / API / MCP 入口テスト 10 件は通過
  - structured routing 配下で `deep_agent` route が live に選択される
  - `tool_catalog_resolved` には `deep_agent` 側へ公開したツール一覧が記録される
  - `deep_agent` route は `execute` / `status` / `get_result` を使わない設計になっている

今回の論点は route 選択ではなく、DeepAgents が directory path をどう解釈し、配下の探索や `analyze_files` への引き渡しをどう行っているか、に限定される。

## 再現手順

### 1. SV 型内部 route としての DeepAgents

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

### 2. DeepAgents 明示入口

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

### 3. DeepAgents 明示入口 + absolute path

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

## 期待結果

- 既存 directory path が与えられた場合、DeepAgents がその directory を空または不存在と誤判定しないこと
- `build_deep_agent_system_prompt()` の意図どおり、directory 指定を配下探索し、対象ファイルへ展開してから解析へ進むこと
- 少なくとも `docs` のような既存 directory に対しては、空判定ではなく何らかの配下ファイル解析結果へ到達すること

## 実装上の確認済み前提

- `deep_agent_support.py` の system prompt には、次が明記されている
  - absolute path が存在する場合はそのまま使う
  - directory path が指定された場合、file 指定として却下せず、存在確認のうえで配下を探索し、対象ファイルへ展開してから解析する
- `agent_client_util.py` では、`deep_agent` route に対して `healthz`, `get_loaded_config_info`, `analyze_files`, `analyze_pdf_files`, `analyze_image_files` が公開される

## 確認したいこと

1. DeepAgents 明示入口や `deep_agent` route で、directory path が `docs/**` のような glob へ変形される条件は何か
2. `working_directory` 配下の相対 path 解釈と absolute path 解釈で、directory 展開処理に差があるか
3. `analyze_files` に渡す前段で、directory の存在確認や配下探索がどこで失敗しているか
4. DeepAgents 側の planner / tool 呼び出しで、directory path を「空」と要約してしまう誤推論が入り込んでいないか
5. 最小修正で改善するなら、prompt 側・tool wrapper 側・directory expansion 側のどこを直すのが妥当か

## 期待する回答

- 原因の切り分け
- 期待仕様に対して現行挙動がどこで外れているか
- 必要なら最小修正方針
- 再現用の最小ケース

## 関連文書

- `/home/user/source/repos/ai-platform-poc/docs/11_技術課題検証/A-04-04_SV型DeepAgents実装の検証.md`
- `/home/user/source/repos/ai-chat-util/README_FOR_EXPERTS.md`
- `/home/user/source/repos/ai-chat-util/app/src/ai_chat_util/base/agent/deep_agent_support.py`
