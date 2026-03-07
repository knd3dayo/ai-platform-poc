# Application層の実装方針

## 前提
* [AIエージェントの業務適用を見据えた生成AIアプリケーション層の検討](../01_アーキテクチャ検討/AIエージェントの業務適用を見据えた生成AIアプリケーション層の検討.md)をベースとする。

## 概要
### 自律型エージェント
* SV型エージェントから呼び出される、自律型エージェントの実装検証
  * WF型のように手順が固定できず、タスク解決のための道筋が探索的になる領域に適用する。
  * 最小単位は「目標」と「利用可能なツール群」であり、AIが自身で計画と実行を繰り返す。

### SV型エージェント
* SV型は「正解が一つではない」「責任の所在が重い」領域において、自律型の「予測不能さ」という弱点を克服し、安全に業務適用するために用いられる。
* ここで言う「SV（スーパーバイザー）」には、**AIと人間の2つのレイヤー**が存在する。
  1. **AIのSupervisor（統制役）**：各専門AIワーカーの働きを監視し、品質が基準に達するまでやり直し（ループ）を命じる。
  2. **人間のSupervisor（最終責任者）**：AIが起案（下書き）した結果に対して、最終的な意思決定を下す。

* **SV型の設計指針：**
AIエージェントの一般的な用語として「スーパーバイザー」はAIの司令塔を指すが、業務適用においては**「SV型アーキテクチャを採用する場合は、必ず人間が結果を判断・承認するプロセス（非同期HITL）を組み込むべき」**という原則を置く。



## 実装方針
### SV型エージェント
* SV型エージェントはLangGraphで実装し、コーディングエージェントのコンテナをPython経由で起動し、
指示とタスクIDを渡す。なおタスクIDはワークスペースのパスの一部にもなる。
* SV型エージェントが自律型エージェントに渡すタスクIDはシステム全体で一意の値となるトレースIDを使用する。
* 自律型エージェントが呼び出すMCPツールには認証情報(Bearerトークンなど)を渡す必要がある場合がある。
その場合、自律型エージェントは引数または環境変数としてそれらの情報を受け取り、ワークスペース内のMCPの定義を記述した設定ファイルに反映する。
* 自律型エージェントの処理状況は`TaskStatus`として逐次受け取り、それをユーザーまたは非同期連携基盤へと通知する。
* 自律型エージェントの結果には「もっと情報が必要」「この後どうしますか？」といった、ユーザーによる判断が必要となる回答もある。
その場合に、ユーザーからの入力を待つ機能(Human in the loop)を実装する必要がある。

* サンプル実装の方針
   * 自律型エージェントの処理はPythonから行うサンプル実装[ai_platform_samplelib/application/autonomous](../../app/ai-platform-samplelib/src/ai_platform_samplelib/application/autonomous)を使用することで実現する。
   * SV型エージェントのサンプル実装は[ai_platform_samplelib/application/super_visor](../../app/ai-platform-samplelib/src/ai_platform_samplelib/application/super_visor/)に作成する。
   * SV型エージェントの検証は、まずコマンドライン（`ai_platform_samplelib.application.super_visor.cli.main`）から実行する。
   * コマンドライン起動用のテストクライアント(シェルスクリプト)を[test/application/super-visor](../../test/application/super-visor)に配置する。
   * CLIは `run` / `resume` を提供する。`-y/--yes` 指定時は承認をスキップし、未指定時はサブタスク単位で承認/停止（セッション保存）を行う。

* 重要
  * SV型エージェントで設定した環境変数が自律型エージェントに確実に渡されること。
  * SV型エージェントと自律型エージェントの情報共有、進捗管理のためのファイルをワークスペース上に配置して、各々がそれを参照したうえで処理を進めること。
  
#### 現状との乖離（暫定・SV型エージェント）

3. 「トレースID = task_id」伝播（SV→自律）が未達（thread_id/task_id が分断）
   * 方針/期待: SVが自律型へ渡す task_id は、全体で一意な trace_id を使用する。
   * 現状:
       * SV（PoCはCLI実行）は処理単位のIDを採番するが、Executor 実行の `task_id` は別採番になっており統一されていない。
   * 影響: trace_id を task_id として統一しづらく、横断トレーシング/運用の一貫性が落ちる。

4. `TaskStatus` の逐次通知がSV経路に乗っていない
   * 方針/期待: 自律型エージェントの処理状況を `TaskStatus` として逐次受け取り、ユーザーまたは非同期連携基盤へ通知する。
    * 現状:
       * SV側の状態管理は `TaskStatus` に統一済み。ただしSV APIは削除しており、ユーザー向け取得手段は現状CLI表示が中心。
       * SV内部では `TaskStatus` を `publish_task_status()` で発行している（例: started/configured/progress/finished/error）。ただしEventBusは PoC 向けモック（`noop/stdout/memory`）のみで、既定値は `noop`（環境変数 `SV_EVENT_BUS_TYPE` 未設定の場合）。そのため PoC の標準実行経路（CLI / テストクライアント）では、外部の非同期連携基盤へは実質的に通知されない。
       * なお “逐次通知の観測” 自体は、`SV_EVENT_BUS_TYPE=stdout` により標準出力へJSONイベントとして出せる（外部Pushではなくローカル観測）。
      * Webhook送信などのデモは別途検討対象だが、`TaskStatus` の逐次通知として統合された実装は未整備。
    * 影響:
       * “逐次通知（非同期連携基盤へPush）”に寄せる場合は、通知先（Webhook/Event Bus）とイベント粒度（status/sub_status/ログ/成果物）を設計し、EventBus の実装（例: Redis/Kafka/HTTP など）と設定注入（compose/env）を追加する必要がある。

5. HITL（Human in the loop）はCLI統合は進んだが、非同期HITLは計画境界まで
   * 方針/期待: 「もっと情報が必要」「この後どうしますか？」等の回答に対し、ユーザー入力待ち（非同期HITL）を実装する。
   * 現状:
       * PoCはCLI実行に寄せており、実行前承認（HITL相当）はCLI側に統合済み（`-y/--yes` でスキップ可）。
       * `-y` 未指定時は、計画から抽出したサブタスク単位で「承認/却下/一時停止（セッション保存）」を行い、一時停止した場合はセッションJSONを保存して `resume` で続きから再開できる（保存先は `--session-dir`、省略時は `.sv_sessions`）。
       * ただし現状の pause/resume は「サブタスク実行の境界」での停止であり、コーディングエージェント（executor）実行の“途中”での入力待ち・再開（コンテナ/作業状態のチェックポイント復元）までは扱っていない。
   * 影響: “コーディング実行の途中で承認待ち→再開”を目指す場合、executor の中断/再開戦略（チェックポイント、workspace状態、コンテナ継続/再起動）と、ユーザー入力チャネル（CLI/GUI/API）を含めたワークフロー統合が必要。

6. MCP認証（Bearer等）の「受け取り→workspace内設定反映」の経路が確認できない
   * 方針/期待: Bearer等を引数/環境変数で受け取り、workspace 内の MCP 定義へ反映する。
   * 現状: SV→Executor のツール引数は `prompt`/`zip`/`initial_files`/`timeout` が中心で、Bearer等を受け取って workspace 設定（MCP定義）へ反映する処理が見当たらない。
   * 影響: “実行時に注入された認証情報で MCP を呼ぶ”ユースケースが、現状のSV経路では成立しにくい。


### 自律型エージェント
* Claude Code、Cline CLI、OpenCodeのようなコーディングエージェントをDockerコンテナ上で実行する。
  * コーディングエージェントには、ソースコードやログファイル、実行の前提となるデータファイルを格納したワークスペースを
ホスト側から渡す。
  * ワークスペースにはAGENT.mdや利用可能なMCPの定義を記述した設定ファイルも格納する。

* サンプル実装の方針
   * Dockerコンテナのサンプル実装を[all-in-on-image](../../app/docker/autonomous-agent-executor/images/all-in-on-image)に作成する。
   * Dockerコンテナの操作をPythonから行うサンプル実装を[ai_platform_samplelib/application/autonomous](../../app/ai-platform-samplelib/src/ai_platform_samplelib/application/autonomous)に作成する。
   * Dockerコンテナの操作をPythonから行うサンプル実装のテストクライアント(シェルスクリプト)を[test/application/autonomous](../../test/application/autonomous)に配置する。


#### 方針 vs 実装 整合性レビュー（自律型エージェントSandbox）

PoC手順・技術課題と対応方針・本ドキュメントを一次ソースとして、(1) Sandbox構築/起動フロー、(2) 自律型エージェント実行（Python→Docker）、(3) Egress/機密/トレース/MCP注入の観点で実装を棚卸しし、乖離点を根拠付きで列挙する。優先順位付け（方針優先か実装優先か）は後段で検討できる形に整理する。

#### Steps
1. 方針抽出（一次ソース3点）
   * [docs/03_PoC手順/01_生成AI基盤インフラ構築手順.md](../03_PoC手順/01_生成AI基盤インフラ構築手順.md) から「Sandboxの構築方法（build.sh 事前ビルド、run.sh 実行、外部ネットワーク ai_platform_net）」を抽出
   * [docs/01_アーキテクチャ検討/技術課題と対応方針.md](../01_アーキテクチャ検討/技術課題と対応方針.md) から「Ephemeral/ウォームプール/機密注入/Egress制御」等の要件を抽出
   * 本ドキュメントから「Docker上でのコーディングエージェント、Pythonからの起動、workspaceへAGENT.md/MCP定義配置、trace ID を task_id として使用、MCPにBearer等注入」を抽出
2. 実装の責務分解と対応付け
   * CLI系: `test/application/autonomous/test_client.sh` と環境変数（`.env`）の役割確認
   * Sandboxイメージ: `app/docker/autonomous-agent-executor/images/all-in-on-image`（Dockerfile/build.sh/run.sh/entrypoint.sh/compose/config/workspace）を確認
   * 実行基盤: `ai-platform-samplelib` の autonomous 実装（ComposeConfig/CodingAgentConfig, CodingAgentRunner, TaskService/TaskManager）を確認
   * API/補助: `app/docker/autonomous-agent-executor/api`（start_server.sh、envファイル）を確認
3. 方針ごとのチェックリストで棚卸し
   * ビルド方針（compose buildを避け build.sh で事前ビルド）
   * コンテナライフサイクル（requestごと起動・回収・破棄）
   * workspace受け渡し（ソース/ログ/データ/設定）
   * trace ID と task_id（全体で一意、外部から注入できるか）
   * Egress制御（LiteLLM Proxy以外遮断）
   * 機密注入（envやworkspaceファイルへの反映、ハードコードの有無）
   * MCP定義と認証（Bearer等を受け取りworkspace設定へ反映）
4. 乖離点の列挙（根拠・影響・暫定評価）
   * 乖離点ごとに「どの方針に対して」「現状の実装は何をしているか」「想定される影響（動作/運用/セキュリティ/保守）」を1段落で整理
5. 次アクション案（必要になったら）
   * 乖離を解消するためのTODO（どのファイルをどう変えるか）と検証項目を追加

#### Relevant files
* `test/application/autonomous/test_client.sh` — CLI実行の入口（COMPOSE_COMMAND選択、samplelib CLI呼び出し）
* `test/application/autonomous/.env` — COMPOSE_DIRECTORY 等のcompose設定、CODE_AGENT_CONFIG_PATH指定
* `app/docker/autonomous-agent-executor/images/all-in-on-image/Dockerfile` — Sandboxに入るツール/権限（sudo/NET_ADMIN 等）
* `app/docker/autonomous-agent-executor/images/all-in-on-image/build.sh` — 事前ビルドの方針（build context へのコピー）
* `app/docker/autonomous-agent-executor/images/all-in-on-image/run.sh` — 実行フロー（workspaceへconfigコピー、docker compose run）
* `app/docker/autonomous-agent-executor/images/all-in-on-image/entrypoint.sh` — UID/GID調整、firewall初期化、opencode.json生成
* `app/docker/autonomous-agent-executor/images/all-in-on-image/init-firewall.sh` — Egress制御の実体
* `app/docker/autonomous-agent-executor/images/all-in-on-image/config/common/opencode.jsonc` — MCP定義（現状は固定値）
* `app/ai-platform-samplelib/src/ai_platform_samplelib/application/autonomous/model/models.py` — ComposeConfig/CodingAgentConfig
* `app/ai-platform-samplelib/src/ai_platform_samplelib/application/autonomous/core/coding_agent_runner.py` — Pythonからdocker compose run、workspace作成
* `app/ai-platform-samplelib/src/ai_platform_samplelib/application/autonomous/core/task_service.py` — 監視・完了後のremove、detached monitor
* [docs/03_PoC手順/01_生成AI基盤インフラ構築手順.md](../03_PoC手順/01_生成AI基盤インフラ構築手順.md) — PoC手順（事前ビルド方針、all-in-on-image 例）
* [docs/01_アーキテクチャ検討/技術課題と対応方針.md](../01_アーキテクチャ検討/技術課題と対応方針.md) — Egress制御/Ephemeral/注入方針

#### Verification
1. ドキュメント上の期待フローに従い、all-in-on-image の build.sh→run.sh が動く前提（環境変数/ネットワーク/イメージ名）が揃っているか点検する。
2. samplelib CLI（`python -m ai_platform_samplelib.application.autonomous.cli.main run ...`）が参照する環境変数（COMPOSE_DIRECTORY/FILE/SERVICE_NAME/COMMAND 等）と、各 `.env` のキーが一致しているか確認する。
3. 乖離点のうち「動作上の致命傷（パス不整合/存在しないディレクトリ参照）」と「将来方針未達（Egress/機密注入/AGENT.md）」を分けてリスト化する。

#### 乖離点の列挙（暫定・優先判断は別途）


3. Egress 制御（LiteLLM Proxy 以外遮断）の実装が未達
   * 方針/期待: 「LiteLLM Proxy を経由しない不正な LLM 通信のネットワーク遮断（Egress制御）」を実行時ゲートとして担保。
   * 現状: `all-in-on-image` の `init-firewall.sh` はルール初期化後に `iptables -P OUTPUT ACCEPT`（許可全開）で、遮断ルールはコメント例のみ。
   * 影響: サンドボックスから任意の外部通信が可能になり得る（方針上の“隔離/統制”とギャップ）。

4. 機密情報の「注入」よりも「ハードコード/配布ファイルへの固定値」が中心
   * 方針/期待: ウォームプール等を見据えた「実行直前の機密注入」（永続化しない）を志向。
   * 現状: `.env_template` や `opencode.jsonc` などに API key が固定値として記載されている箇所がある（PoC用と推測されるが、方針とは方向性が異なる）。
   * 影響: 誤って別環境へ持ち出す/ログ等へ露出するリスクが上がる。将来の「注入方式」への移行時に差し替えコストが発生し得る。

5. workspace に置く想定の `AGENT.md` が見当たらない
   * 方針/期待: workspace に `AGENT.md`（エージェント運用ルール等）を格納して渡す。
   * 現状: リポジトリ内に `AGENT.md` が見当たらず、現行フロー上どこで生成/配置するかも不明。
   * 影響: “何をしてよいか/だめか”の制約を workspace 側で与えづらく、運用ポリシーの具体化が進みにくい。

6. MCP 認証情報の「受け取り→workspace内設定反映」の経路が薄い
   * 方針/期待: Bearer トークン等を引数/環境変数で受け取り、workspace 内の MCP 定義へ反映。
   * 現状: `create_opencode_json.py` は LLM 接続設定（provider/model/baseURL）中心で、`config/common/opencode.jsonc` の MCP 定義は固定値になっている。
   * 影響: “実行時に注入された認証情報で MCP を呼ぶ”ユースケースが、今の default 設定では成立しにくい。

7. 生成物（`src-updated`）内に環境ファイルが混在し、設定キーも揺れている
   * 方針/期待: 実行時に参照される env キー（例: `COMPOSE_DIRECTORY`）が一貫していること。
   * 現状: `test/application/autonomous/src-updated/` に過去の `.env_*` が残っており、`COMPOSE_PROJECT_DIRECTORY` のように実装が参照しないキーも含まれる。
   * 影響: 人手運用時に誤って参照/コピーされやすく、トラブルシュートが難しくなる。

8. ウォームプール/Speculative Boot 等の性能方針は未実装（PoC段階）
   * 方針/期待: コールドスタート遅延を隠蔽するための投機起動・ウォームプール。
   * 現状: タスクごとに workspace を切り、コンテナ起動・監視・終了後 remove までの基本線はあるが、ウォームプール等は未実装。
   * 影響: コールドスタート時間がそのままユーザー体験に跳ねる。将来拡張の設計余地を残す必要がある。

#### Decisions
* 今回は「逸脱の列挙（影響/根拠付き）」までで止め、修正TODO化や優先順位付けは別途行う。
* 方針の一次ソースは上記3ドキュメント（＋必要に応じて補助資料）とする。

