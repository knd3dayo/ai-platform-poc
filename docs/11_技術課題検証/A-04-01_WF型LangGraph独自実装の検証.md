# A-04-01_WF型LangGraph独自実装の検証

## 検証目的

本検証の主目的は、サブ課題 A-04-01「WF型エージェントの実装検証（LangGraphベースの独自実装）」について、PoC 環境で成立性を確認することである。

最終的には、A-04 の完了判定に必要な材料として、LangGraph ベースの独自実装を WF 型の実装基盤として採用できるか、その正常系、代表的な異常系、運用上の制約を明確にすることを目指す。

## 対応する課題とサブ課題

| 親課題 | サブ課題 | この文書で主に確認すること |
| --- | --- | --- |
| A-04 | A-04-01 | 固定フロー化した LangGraph 実装で、分岐、再実行性、監査可能性を備えた WF 型を構成できるかを確認する。 |

必要に応じて、副次的に A-01-01、A-01-02、A-02-01 の前提整理にも利用する。

## 関連するアーキテクチャ検討文書

- [技術課題と対応方針](../03_検証準備/01_技術課題と対応方針.md)
  - A-04-01 に対応し、WF 型の実装基盤として LangGraph 独自実装が成立するかを確認する。
- [Application層の実装方針](../03_検証準備/12_Application層実装方針.md)
  - 初期段階の Application 層構成における WF 型 / SV 型 / 自律型の分担前提を参照する。
- [生成AIアプリケーション層の実現方式](../02_アーキテクチャ実現方式/02_生成AIアプリケーション層の実現方式.md)
  - WF 型は Dify または固定構成の LangGraph で実装するという整理を参照する。
- [A-01-01_型選択基準の定義検証.md](./A-01-01_型選択基準の定義検証.md)
  - WF 型の代表実装として LangGraph workflow を前提に型選択基準を整理している。

## 検証で確認したいこと

### 1. 正常系

- Markdown / Mermaid から WF 型 workflow を実行できること。
- plan mode、durable 実行、resume を含む基本的な実行契約が成立すること。
- CLI、API、MCP のいずれかから LangGraph workflow 実装へ到達できること。

### 2. 異常系

- workflow 定義が不正な場合に、誤った実行ではなくエラーまたは clarification へ遷移すること。
- workflow 定義なしの要求を、LangGraph WF 型へ無理に載せないこと。
- WF 型で扱うべきでない探索的要求を、SV 型や自律型へ逃がす余地が残っていること。

### 3. 運用系

- workflow 定義ファイル、trace_id、plan mode の結果を後追いできること。
- workflow 資産をファイルとして保守できること。
- 再実行や差し戻し時に、同じ workflow 定義を再利用できること。

## 対象構成

| 観点 | 主な既存実装 / 入口 | 備考 |
| --- | --- | --- |
| CLI 入口 | `${HOME}/source/repos/ai-chat-util/app/src/ai_chat_util/cli/__main__.py` の `run_workflow` / `run_workflow_durable` | WF 型の主入口 |
| API / facade | `${HOME}/source/repos/ai-chat-util/app/src/ai_chat_util/core/app.py` の `run_mermaid_workflow_from_file` | Markdown / Mermaid から workflow 実行へ接続 |
| workflow 実装 | `${HOME}/source/repos/ai-chat-util/app/src/ai_chat_util/workflow/chat_client.py`、`${HOME}/source/repos/ai-chat-util/app/src/ai_chat_util/workflow/workflow/runner.py` | LangGraph ベースの実行本体 |
| サンプル資産 | `${HOME}/source/repos/ai-chat-util/app/src/ai_chat_util/workflow/samples/data/sample2.md` | WF 型の検証用定義 |
| Coordinator 経由 | `${HOME}/source/repos/ai-chat-util/app/src/ai_chat_util/core/app.py` の `run_coordinated_chat` | workflow_file_path 指定時の WF 型選択 |

## 既存実装と入口の対応づけ

1. CLI

- `uv run -m ai_chat_util.cli run_workflow`
- `uv run -m ai_chat_util.cli run_workflow_durable`

2. API / ライブラリ

- `run_mermaid_workflow_from_file`
- `execute_workflow_markdown`

3. MCP / Coordinator 経由

- `run_coordinated_chat` に `workflow_file_path` を与えた場合、WF 型候補として選択される。
- 明示的な workflow 定義なしでは、WF 型へ自動接続しない制約がある。

## 前提条件

- `${HOME}/source/repos/ai-chat-util/app` の依存が導入済みであること。
- workflow サンプル Markdown を利用できること。
- 必要に応じて LiteLLM 接続先が設定されていること。

## 検証手順

### 1. 事前準備

```bash
cd ${HOME}/source/repos/ai-chat-util/app
uv sync
```

### 2. 正常系確認

```bash
cd ${HOME}/source/repos/ai-chat-util/app
uv run -m ai_chat_util.cli run_workflow \
  -f src/ai_chat_util/workflow/samples/data/sample2.md \
  -m "work ディレクトリを確認してください"
```

期待結果:

- LangGraph workflow が起動する。
- 事前定義した手順に沿って処理が進む。
- WF 型の独自実装入口が成立していることを確認できる。

### 3. durable / plan mode 確認

```bash
cd ${HOME}/source/repos/ai-chat-util/app
uv run -m ai_chat_util.cli run_workflow_durable \
  -f src/ai_chat_util/workflow/samples/data/sample2.md \
  -m "work ディレクトリを確認してください" \
  --plan-mode
```

期待結果:

- plan mode により承認待ちへ遷移できる。
- durable 実行と resume 前提の契約が確認できる。

### 4. 異常系確認

```bash
cd ${HOME}/source/repos/ai-chat-util/app
uv run -m ai_chat_util.cli run_workflow -f ./not-found.md -m "test"
```

期待結果:

- 不正な workflow 定義で即時に失敗する。
- 誤った WF 実行が開始されない。

## 判定基準

| 観点 | 判定基準 |
| --- | --- |
| 構造成立性 | LangGraph workflow 実装が独立した WF 型入口として存在する。 |
| 制御成立性 | 固定フロー、plan mode、durable 実行、resume の基本契約を確認できる。 |
| 運用成立性 | workflow 定義をファイル資産として管理し、再利用できる。 |

## 検証結果記録欄

### 2026-04-05 実測結果

実行コマンド 1:

```bash
cd ${HOME}/source/repos/ai-chat-util/app
uv run pytest src/ai_chat_util/workflow/_test_/test_langgraph_workflow.py -q
```

実行結果:

- `9 passed in 6.79s`
- LangGraph workflow 実装本体のテストが通過し、durable workflow、plan、pause / resume 前提の基本挙動が崩れていないことを確認した。

実行コマンド 2:

```bash
cd ${HOME}/source/repos/ai-chat-util/app
uv run pytest src/ai_chat_util/_test_/test_coordinator_entrypoints.py -q
```

実行結果:

- `7 passed in 18.73s`
- `workflow_file_path` 指定時の WF 型選択、`cross_type_route_decided` 監査イベント、clarification 遷移を確認した。

補足:

- 今回は workflow 実装本体と Coordinator 入口の実測を優先し、実 LLM を使った `run_workflow` CLI の end-to-end 実行までは行っていない。

| 項目 | 結果 | 補足 |
| --- | --- | --- |
| 正常系 | 一部確認済み | workflow 実装テスト 9 件、Coordinator 入口テスト 7 件が通過した。 |
| 異常系 | 一部確認済み | 型選択競合時の clarification は確認済み。CLI での不正 workflow ファイル実行は未確認。 |
| 運用系 | 一部確認済み | `trace_id` と `cross_type_route_decided` 監査イベントは確認済み。workflow 資産管理の運用設計は未確認。 |

## 残課題

- generic request から適切な workflow 定義へ自動接続する仕組みは別途必要である。
- Dify と LangGraph のどちらを WF 型の既定実装とするかはユースケースごとに整理が必要である。
- 本文書では実行基盤の成立性を扱い、業務ごとの workflow 資産管理規約までは扱わない。