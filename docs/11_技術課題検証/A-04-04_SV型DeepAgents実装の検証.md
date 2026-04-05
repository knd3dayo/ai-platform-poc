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

## 残課題

- `run_deepagent_chat` を使った明示入口と、SV 型内部 route としての利用をどう使い分けるか整理が必要である。
- DeepAgents を SV 型として採用する場合の停止条件、予算上限、監査出力は追加検証が必要である。
- 自律型としての DeepAgents は A-04-06 で別途整理する。