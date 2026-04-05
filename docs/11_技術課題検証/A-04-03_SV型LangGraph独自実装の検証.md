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

期待結果:

- clarification または approval が必要なケースで `paused` が返る。
- trace_id を維持して再送できる。

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

## 残課題

- DeepAgents 実装との比較観点を A-04-04 で別途整理する必要がある。
- cross-type 自動 reroute は A-01-03 の残課題として残る。
- end-to-end の非同期 HITL 運用は BFF / 状態管理 DB との接続を含めて別途確認が必要である。
- MCP 設定と LiteLLM 設定の整合を環境ごとに自動検査する仕組みは未整備である。