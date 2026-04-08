# ai-chat-util チーム調査依頼: A-02-02 resume targeted test が circular import で収集失敗する件

## 想定する issue タイトル

workflow resume の targeted test が `ai_chat_util.base.agent` と `WorkflowChatClient` の circular import により collection error になる

## 概要

PoC 側で A-02-02 の正本根拠を最新化するため、従来通っていた workflow resume の targeted test を再実行したところ、現行 ai-chat-util では test collection の時点で `ImportError` になり、resume 契約の targeted rerun ができなかった。

失敗は workflow resume 機能そのものの assertion failure ではなく、`WorkflowChatClient` と `ai_chat_util.base.agent` パッケージ初期化の間に circular import が発生していることによる import error である。

## 背景

- 対象検証: A-02-02 Resume プロトコルの検証
- PoC 文書では 2026-04-05 時点で次の targeted test が `3 passed, 6 deselected` で通過していた

```bash
cd ${HOME}/source/repos/ai-chat-util/app
uv run pytest src/ai_chat_util/workflow/_test_/test_langgraph_workflow.py -k "trace_id or plan or pause or resume" -q
```

- 2026-04-08 に同じコマンドを再実行すると、現行コードでは collection error になる

## 再現手順

```bash
cd ${HOME}/source/repos/ai-chat-util/app
uv run pytest src/ai_chat_util/workflow/_test_/test_langgraph_workflow.py -k "trace_id or plan or pause or resume" -q
```

実測結果:

- exit code: `2`
- pytest summary:

```text
ERROR src/ai_chat_util/workflow/_test_/test_langgraph_workflow.py
Interrupted: 1 error during collection
```

- traceback の要点:

```text
src/ai_chat_util/workflow/_test_/test_langgraph_workflow.py
  -> ai_chat_util.workflow.__init__
  -> ai_chat_util.workflow.chat_client
  -> ai_chat_util.workflow.workflow.runner
  -> ai_chat_util.base.agent.agent_builder
  -> ai_chat_util.base.agent.__init__
  -> ai_chat_util.base.agent.agent_batch_client
  -> ai_chat_util.base.agent.agent_client_factory
  -> ai_chat_util.base.agent.agent_client
  -> ai_chat_util.workflow.chat_client

ImportError: cannot import name 'WorkflowChatClient' from partially initialized module 'ai_chat_util.workflow.chat_client'
```

## 確認できたこと

### 1. import 連鎖

- `ai_chat_util.workflow.__init__` は `WorkflowChatClient` を eager import している
- `workflow/chat_client.py` は `workflow/workflow/runner.py` を import している
- `workflow/workflow/runner.py` は `ai_chat_util.base.agent.agent_builder` を import している
- `ai_chat_util.base.agent.__init__` は `agent_batch_client`、`agent_client_factory`、`agent_client` などを eager import している
- `agent_client.py` は再び `ai_chat_util.workflow.chat_client.WorkflowChatClient` を import している

### 2. 失敗点

- `WorkflowChatClient` の import 完了前に `agent_client.py` 側から同じ symbol を逆参照しており、partially initialized module error になる
- そのため workflow resume の targeted test が実行前に collection error で止まる

## 期待結果

- 上記 targeted test が collection error なく実行できること
- 少なくとも `test_workflow_chat_client_resumes_after_approval`、`test_runner_pauses_and_resumes_approval_node` を含む resume 系 test が現行コードで再実行可能であること
- workflow / agent package の import 順序に依存した循環参照が解消されること

## 主な原因候補

1. `ai_chat_util.base.agent.__init__` が package import 時に広範囲の symbol を eager import している
2. `agent_client.py` が top-level import で `WorkflowChatClient` を参照している
3. workflow 側 test が `ai_chat_util.workflow` package 経由で import するため、package 初期化時の循環が露出しやすい

## 修正の方向性候補

1. `ai_chat_util.base.agent.__init__` の eager import をやめ、必要 symbol を lazy import 化する
2. `agent_client.py` の `WorkflowChatClient` 参照を局所 import または type-check only import へ寄せる
3. workflow 側の公開 API と agent 側の公開 API の依存方向を見直し、package 初期化で相互参照しないようにする

PoC 側としては 1 の package 初期化軽量化が最小修正に見えるが、適切な修正箇所は ai-chat-util 側の設計判断に委ねたい。

## PoC への影響

- A-02-02 の historical result 自体は 2026-04-05 の実測で成立しているため、Resume プロトコルの設計・既存実績を直ちに否定するものではない
- ただし現行 ai-chat-util では同じ targeted test を fresh rerun できず、resume 契約の regression check が壊れている
- A-04-03 では A-02-02 正本参照で受け入れ判断を行ったが、resume 正本の継続検証性を回復するためにはこの import 問題の解消が望ましい

## 確認したいこと

1. 現行ブランチでこの circular import が既知か
2. `ai_chat_util.base.agent.__init__` の eager import は意図的か、それとも副作用か
3. 最小修正で targeted test の collection error を解消するにはどこを直すのが妥当か
4. 修正後に workflow resume targeted test を CI / regression の観点で再度有効化できるか

## 関連文書

- [A-02-02_Resumeプロトコルの検証.md](../11_技術課題検証/A-02-02_Resumeプロトコルの検証.md)
- [A-04-03_SV型LangGraph独自実装の検証.md](../11_技術課題検証/A-04-03_SV型LangGraph独自実装の検証.md)
- /home/user/source/repos/ai-chat-util/app/src/ai_chat_util/workflow/_test_/test_langgraph_workflow.py
- /home/user/source/repos/ai-chat-util/app/src/ai_chat_util/workflow/chat_client.py
- /home/user/source/repos/ai-chat-util/app/src/ai_chat_util/workflow/workflow/runner.py
- /home/user/source/repos/ai-chat-util/app/src/ai_chat_util/base/agent/__init__.py
- /home/user/source/repos/ai-chat-util/app/src/ai_chat_util/base/agent/agent_client.py

## ai-chat-util チーム回答

調査ありがとうございます。こちらで現行ブランチ上で再現確認と最小修正の適用、再検証を行いました。

### 結論

- ご報告の circular import は現行ブランチで再現しました。
- 直接の原因は `ai_chat_util.base.agent.agent_client` が top-level import で `WorkflowChatClient` を参照していたことです。
- 最小修正として、`agent_client.py` 側の `WorkflowChatClient` import を遅延解決に変更し、workflow_backend 分岐でのみ解決する形にしました。
- 修正後、resume targeted test は collection error なく再実行でき、報告の targeted test は `3 passed, 6 deselected` で通過しました。

### 1. 現行ブランチでこの circular import が既知か

少なくとも今回の調査時点では、現行ブランチ上で未解消の状態として再現しました。こちらでも以下コマンドで同じ collection error を確認しています。

```bash
cd ${HOME}/source/repos/ai-chat-util/app
/home/user/source/repos/ai-chat-util/app/.venv/bin/python -m pytest src/ai_chat_util/workflow/_test_/test_langgraph_workflow.py -k "trace_id or plan or pause or resume" -q
```

実測結果:

- exit code: `2`
- `ImportError: cannot import name 'WorkflowChatClient' from partially initialized module 'ai_chat_util.workflow.chat_client'`

### 2. `ai_chat_util.base.agent.__init__` の eager import は意図的か、それとも副作用か

今回の障害を直接起こしていたのは `ai_chat_util.base.agent.__init__` 単体というより、次の組み合わせです。

- `ai_chat_util.workflow.__init__` が `WorkflowChatClient` を eager import
- `workflow/chat_client.py` が `workflow/workflow/runner.py` を import
- `runner.py` が `ai_chat_util.base.agent.agent_builder` を import
- その過程で `ai_chat_util.base.agent.__init__` が `agent_client` を含む複数 symbol を eager import
- `agent_client.py` が再び top-level で `WorkflowChatClient` を import

したがって、`base.agent.__init__` の eager import は循環を露出しやすくする要因ではありますが、今回の最短経路の根本は `agent_client.py` の top-level `WorkflowChatClient` import です。

### 3. 最小修正で targeted test の collection error を解消するにはどこを直すのが妥当か

最小修正としては、PoC 側で挙げていただいた候補 2 が最も妥当でした。

具体的には、以下を実施しています。

- `app/src/ai_chat_util/base/agent/agent_client.py` から top-level の `from ai_chat_util.workflow.chat_client import WorkflowChatClient` を除去
- 代わりに、workflow_backend 分岐に到達した時だけ `WorkflowChatClient` を遅延解決する helper を追加
- monkeypatch 互換性を壊さないよう、module 変数経由で解決する構成に変更

この方法だと、`workflow_backend` を使わない import collection 時点では workflow 側に逆参照しないため、今回の circular import を解消できます。

なお、`ai_chat_util.base.agent.__init__` の package 初期化軽量化も中長期的には有効ですが、今回の collection error を最短で直すには `agent_client.py` 側の遅延化が最小でした。

### 4. 修正後に workflow resume targeted test を CI / regression の観点で再度有効化できるか

少なくともローカル再検証では有効化可能です。修正後に以下を確認しました。

1. 報告の targeted test

```bash
cd ${HOME}/source/repos/ai-chat-util/app
/home/user/source/repos/ai-chat-util/app/.venv/bin/python -m pytest src/ai_chat_util/workflow/_test_/test_langgraph_workflow.py -k "trace_id or plan or pause or resume" -q
```

結果:

```text
...                                                                      [100%]
3 passed, 6 deselected in 6.72s
```

2. workflow_backend の既存 entrypoint 回帰

```bash
cd ${HOME}/source/repos/ai-chat-util/app
/home/user/source/repos/ai-chat-util/app/.venv/bin/python -m pytest src/ai_chat_util/_test_/test_workflow_backend_entrypoints.py -q
```

結果:

```text
......                                                                   [100%]
6 passed in 7.12s
```

そのため、Resume 系 targeted test の継続検証性は回復したと見てよいです。

### 補足

- 今回の修正は import 依存の循環解消に限定しています。
- workflow resume 機能自体のロジック変更は入れていません。
- したがって、A-02-02 の historical result を崩さず、fresh rerun を可能にする修正と位置付けられます。