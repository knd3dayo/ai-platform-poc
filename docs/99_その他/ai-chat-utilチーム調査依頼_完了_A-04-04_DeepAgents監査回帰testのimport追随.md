# ai-chat-util チーム調査依頼: DeepAgents 監査回帰 test が現行 import 構成に追随できていない件

## 想定する issue タイトル

`test_mcp_client_chat_emits_deep_agent_audit_events` が旧 module path を前提としており、現行 ai-chat-util で `ModuleNotFoundError` になる

## 概要

PoC 側で A-04-04 の残件整理として DeepAgents の監査回帰 test を単体再実行したところ、現行 ai-chat-util では

- `ai_chat_util.base.agent.mcp_client`
- `ai_chat_util.base.llm.llm_client`

を前提にした test 実装が現行モジュール構成に追随しておらず、`ModuleNotFoundError` により失敗した。

live 実行では DeepAgents 明示入口・SV 型内部 route の双方で audit contract 自体は成立しているため、今回の事象は DeepAgents 機能不成立ではなく、回帰 test の import 前提が古くなっている可能性が高い。

## 背景

- 対象検証: A-04-04 SV型DeepAgents実装の検証
- PoC 側では 2026-04-08 に以下を確認済み
  - DeepAgents 明示入口 trace_id `b1d564912a1347eb9dc396293edfbb85` で `explicit_user_directory_paths=["/home/user/source/repos/ai-platform-poc/docs"]`、`analyze_files` 成功、`final_status=completed`
  - SV 型内部 route trace_id `cc93fa4661c84c6d8cad0713cb7a746d` でも同様に `final_status=completed`
- そのため、残件としては live 挙動ではなく audit 回帰 test の保守有無を切り分けたい

## 再現手順

```bash
cd ${HOME}/source/repos/ai-chat-util/app
uv run pytest src/ai_chat_util/base/agent/_test_/test_tool_guard_wrapping.py -q \
  -k 'mcp_client_chat_emits_deep_agent_audit_events'
```

実測結果:

- exit code: `1`
- pytest summary:

```text
FAILED src/ai_chat_util/base/agent/_test_/test_tool_guard_wrapping.py::test_mcp_client_chat_emits_deep_agent_audit_events - ModuleNotFoundError: No module named 'ai_chat_util.base.agent.mcp_client'
1 failed, 126 deselected in 6.67s
```

## 確認できたこと

### 1. 失敗 test の import 前提

該当 test は次の前提で動いている。

- `sys.modules.pop("ai_chat_util.base.agent.mcp_client", None)`
- `sys.modules["ai_chat_util.base.llm.llm_client"] = stub_llm_client_module`
- `importlib.import_module("ai_chat_util.base.agent.mcp_client")`

### 2. 現行モジュール構成との差分

現行 `src/ai_chat_util/base/agent/` には `mcp_client.py` が存在しない。

存在する主なモジュール:

- `agent_client.py`
- `agent_client_util.py`
- `agent_builder.py`
- `agent_batch_client.py`

また、現行 `src/ai_chat_util/base/agent/__init__.py` は以下の symbol を公開している。

- `AgentClient`
- `DeepAgentMCPClient`
- `CodingAgentMCPClient`

これらはいずれも `agent_client.py` から export されている。

### 3. 現行 class 定義位置

実測では次を確認した。

- `src/ai_chat_util/base/agent/agent_client.py:895` に `class DeepAgentMCPClient(AgentClient)`
- `src/ai_chat_util/base/agent/agent_client.py:900` に `class CodingAgentMCPClient(AgentClient)`

一方で `MCPClient` という module/class は現行コードベース上で見当たらなかった。

### 4. live 監査契約は別途成立している

PoC 側の live 実測では、DeepAgents 自体の監査契約は維持されている。

- standalone 明示入口 trace_id `b1d564912a1347eb9dc396293edfbb85`
- SV 型内部 route trace_id `cc93fa4661c84c6d8cad0713cb7a746d`

いずれも `route_decided`、`tool_catalog_resolved`、`tool_selected.tool_name=analyze_files`、`final_answer_validated.reason_code=sufficiency.answer_supported_by_evidence`、`final_status=completed` を確認済みである。

## 期待結果

- `test_mcp_client_chat_emits_deep_agent_audit_events` が現行モジュール構成で再び実行可能であること
- test が obsolete な module path に依存しないこと
- live で成立している DeepAgents audit contract を regression test でも担保できること

## 主な原因候補

1. `mcp_client.py` から `agent_client.py` / package export へ実装が再編されたが、test が旧 module path を参照したままになっている
2. `ai_chat_util.base.llm.llm_client` を前提にした monkeypatch も、現行 import 経路と乖離している可能性がある
3. test 名は「audit event 検証」だが、実際には古い import 配線へ強く依存しており、目的より実装詳細に結び付きすぎている

## 修正の方向性候補

1. test の import 先を現行 public API に合わせて `ai_chat_util.base.agent` または `agent_client.py` ベースへ更新する
2. obsolete module path を前提にした monkeypatch をやめ、現在の依存点に対して stub を当てる
3. import 配線への依存を減らし、監査 event が emit されること自体を検証対象に絞る

PoC 側の見立てでは 1 と 3 の組み合わせが自然だが、test の責務境界は ai-chat-util 側の設計判断に委ねたい。

## PoC への影響

- A-04-04 の live 受け入れ判定自体は阻害しない
- ただし DeepAgents audit contract の regression guard が壊れているため、将来の refactor で監査イベント退行を検知しにくい
- A-04-06 の自律型 DeepAgents 文書でも、同系統の監査追跡性を live 実測へ依存しているため、test 復旧の価値は高い

## 確認したいこと

1. この test failure は既知か
2. `ai_chat_util.base.agent.mcp_client` 廃止は意図的な module 再編か
3. 現行 public API に追随させるなら、どの import 面を test の正本とすべきか
4. 修正後、この test を CI / regression へ戻す想定があるか

## 関連文書

- [A-04-04_SV型DeepAgents実装の検証.md](../11_技術課題検証/A-04-04_SV型DeepAgents実装の検証.md)
- [A-04-06_自律型DeepAgents実装の検証.md](../11_技術課題検証/A-04-06_自律型DeepAgents実装の検証.md)
- /home/user/source/repos/ai-chat-util/app/src/ai_chat_util/base/agent/_test_/test_tool_guard_wrapping.py
- /home/user/source/repos/ai-chat-util/app/src/ai_chat_util/base/agent/__init__.py
- /home/user/source/repos/ai-chat-util/app/src/ai_chat_util/base/agent/agent_client.py

## ai-chat-util チーム回答

ご連絡の事象は ai-chat-util 側でも再現しました。結論として、DeepAgents 本体の監査契約が壊れていたのではなく、回帰 test が旧 module path に依存したまま残っていたことが原因です。

### 1. 再現結果

ご提示の系統を現行コードベースで確認したところ、まず `test_mcp_client_chat_emits_deep_agent_audit_events` は旧 `ai_chat_util.base.agent.mcp_client` を import しようとして `ModuleNotFoundError` になりました。

その後、同じ論点に関係する以下のテストを現行 import 構成に合わせてまとめて確認しました。

- `test_mcp_client_chat_emits_deep_agent_audit_events`
- `test_mcp_client_chat_emits_selected_server_key_for_coding_agent_route`
- `test_deepagent_mcp_client_forces_deep_route_without_prompt`
- `test_get_loaded_runtime_config_path_returns_existing_config`
- `test_get_loaded_runtime_config_path_returns_none_for_missing_config`

最終確認結果は以下の通りです。

```text
5 passed, 122 deselected in 6.28s
```

### 2. 原因

主因は test 側の import / monkeypatch 前提が現行実装からずれていたことです。

- 旧 `ai_chat_util.base.agent.mcp_client` 前提の import が残っていた
- 旧 `ai_chat_util.base.agent.mcp_client_util` 前提の monkeypatch が残っていた
- 現行 `AgentClient.chat()` が渡す routing / workflow の追加 keyword 引数に対して、test double の fake 関数シグネチャが追随していなかった

現行の正本は `agent_client.py` と `agent_client_util.py` であり、DeepAgents の audit event 自体は live 実行系で成立している状態でした。

### 3. 実施した修正

回帰 test を現行 public / 実装構成へ追随させました。

- import 先を旧 `mcp_client` 依存から現行 `agent_client` 系へ更新
- monkeypatch 対象を旧 `mcp_client_util` から現行 `agent_client_util` へ更新
- `AgentClient` / `DeepAgentMCPClient` を使う形に test を寄せ直し
- fake `decide_route` / fake `create_workflow` などの test double を、現行呼び出しシグネチャに追随できるよう `**kwargs` 含めて拡張

### 4. 判断

今回の failure は既知機能の退行ではなく、module 再編後に test が追随できていなかった保守ずれとして整理するのが適切です。PoC 側で確認済みの live DeepAgents audit contract と、今回復旧した regression test は整合しています。

### 5. 補足

`ai_chat_util.base.agent.mcp_client` は現行コードベースでは正本ではありません。今後同系統の test を追加・修正する場合も、`agent_client.py` / `agent_client_util.py` を基準に追随するのが妥当です。

## PoC 側再確認

PoC 側でも ai-chat-util チーム回答受領後に同系統の 5 テストを現行ブランチで再実行し、次の結果を確認した。

```bash
cd ${HOME}/source/repos/ai-chat-util/app
uv run pytest src/ai_chat_util/base/agent/_test_/test_tool_guard_wrapping.py -q \
  -k 'mcp_client_chat_emits_deep_agent_audit_events or mcp_client_chat_emits_selected_server_key_for_coding_agent_route or deepagent_mcp_client_forces_deep_route_without_prompt or get_loaded_runtime_config_path_returns_existing_config or get_loaded_runtime_config_path_returns_none_for_missing_config'
```

実測結果:

```text
5 passed, 122 deselected in 6.35s
```

したがって、本件は DeepAgents 監査契約の機能不成立ではなく、回帰 test の追随漏れとして upstream / PoC の双方で解消済みと判断する。