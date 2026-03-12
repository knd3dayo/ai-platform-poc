# Application層の実装方針

## 前提
* [AIエージェントの業務適用を見据えた生成AIアプリケーション層の検討](../01_アーキテクチャ検討/AIエージェントの業務適用を見据えた生成AIアプリケーション層の検討.md)をベースとする。

## 概要
### 全体概要
* 最終的には
  * Claude Code、Cline CLI、OpenCodeのようなコーディングエージェントを自律型エージェントとし、サンドボックス内で実行する。  
    サンドボックスとしてDockerコンテナを使用する。
  * 自律型エージェント/サンドボックス起動用のMCPサーバーを用意する。サンドボックス起動用のAPIもDockerで実行可能なようにする。
  * Super-VisorとなるエージェントはLangGraphを用いて実装する。
  * Super-Visor実行用のAPIを用意する。これもDockerで実行可能なようにする。
  * クライアント -> BFF -> Super-Visor API ->  自律型エージェント/サンドボックス起動用のMCP という一連の流れを実現する。

Dockerコンテナの作成、API連携により攻勢が複雑となるため、まずはホスト上で一連の流れを実現する。

* 初期段階では
  * コーディングエージェントはホスト上にインストールする。
   * 自律型エージェント/サンドボックス起動用のMCPサーバーを用意する（必要に応じてAPIも提供）。コーディングエージェントをホスト上のサブプロセス/コンテナとして起動する。
  * Super-VisorとなるエージェントはLangGraphを用いて実装する。
  * Super-Visor実行用のAPIを用意する。Super-Visor実行用のAPIはホスト上のプロセスとして実行する。

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

### 自律型エージェントの実装方針
#### 初期段階
* コーディングエージェントには、ソースコードやログファイル、実行の前提となるデータファイルを格納したワークスペースのパスをSV型エージェント側から渡す。
* ワークスペースにはAGENT.mdや利用可能なMCPの定義を記述した設定ファイルも格納する。
* コアとなるライブラリと、CLI、API、MCPを提供する。
* SV型エージェントからの呼び出しは、自律型エージェント用のMCPサーバー経由で行う。
* 自律型エージェントの `task_id` は外部から指定可能で、未指定の場合はUUID等で自動採番する。
* 自律型エージェント用のMCPサーバーには`execute`、`cancel`、`status`のエンドポイント/MCPツールを準備する。
* 自律型エージェント用のMCPサーバーにはHTTPヘッダ`Authorization`,`trace_id`を受け取り、バックエンドの処理やトレース処理に使用可能にする。

##### 初期段階：設計 ↔ 現状実装の対応（自律型）

| 設計項目（初期段階） | 現状 | 実装箇所（例） | 備考 / 乖離 |
| --- | --- | --- | --- |
| SVから executor に `workspace_path`（絶対パス）を渡す | **概ね実装済み** | `ai_platform_samplelib/application/autonomous/core/endopoint.py`（workspace path 検証/作成） | `EXECUTOR_ALLOWED_WORKSPACE_ROOT` を設定すると、許可ルート外を 403 で拒否できる（ガードレール）。 |
| workspace に `AGENT.md` と MCP 定義ファイルを格納する | **未整備** | （AGENT.md の生成/配置ロジックは見当たらない） | **乖離**: リポジトリ内に `AGENT.md` が無い。MCP 定義も「実行時注入」経路が薄く、workspace 側に何を置くかが運用依存になっている。 |
| コアライブラリ + CLI + API を提供 | **実装済み** | `ai_platform_samplelib/application/autonomous/api/api_server.py` / `.../mcp/mcp_server.py` / `.../cli/main.py` | API は FastAPI、MCP は FastMCP（stdio/sse/http）を提供。API は `--sync_mode` で `/execute` を同期実行に切替可能。CLI は `--sync-mode/--async-mode`（`--wait/--no-wait` のエイリアス）を提供。 |
| SV→自律の呼び出しは API/MCP サーバー経由 | **実装済み（MCPに統一）** | SV: `ai_platform_samplelib/application/super_visor/core/tools.py` / executor MCP: `.../application/autonomous/mcp/mcp_server.py` | **運用方針**: SV→executor は MCP（streamable-http）を既定経路とする。 |
| `task_id` は外部指定可能（未指定なら自動採番） | **実装済み** | `ai_platform_samplelib/application/autonomous/model/models.py`（ExecuteRequest.task_id / TaskStatus.create） | ExecuteRequest に `task_id`（任意）を持つ。 |
| `execute` / `cancel` / `status` を用意 | **実装済み** | `ai_platform_samplelib/application/autonomous/api/api_server.py` / `.../mcp/mcp_server.py` | HTTP API: `/execute` `/status/{task_id}` `/cancel/{task_id}`（+ `/healthz`）。 |
| HTTPヘッダ `Authorization` / `trace_id` を受け取って利用可能にする | **実装済み（下流へenvで伝播）** | `ai_platform_samplelib/application/common/request_headers.py` / `.../application/autonomous/mcp/mcp_server.py` / `.../application/autonomous/core/endopoint.py` | **方針**: 秘匿値は永続化せず、タスクごとの環境変数（例: `AUTHORIZATION`）として下流（subprocess/コンテナ）へ引き継ぐ。 |


#### 最終段階
* コンテナによるサンドボックス化
* Egress 制御（firewall + Squid Proxy）
   * 方針「LiteLLM Proxy を経由しない不正な LLM 通信のネットワーク遮断（Egress制御）」を実行時ゲートとして担保。
   * 実行コンテナ側: `all-in-on-image` の `init-firewall.sh` で `iptables -P OUTPUT DROP` を既定にし、`127.0.0.0/8` と「コンテナ所属の Docker サブネット」宛のみ許可する（サブネットはデフォルトルートのIFから自動検出）。
   * Proxy 経路: 外向き HTTP(S) が必要な処理は、`HTTP_PROXY` / `HTTPS_PROXY` を `http://squid:3128` に設定して Squid を経由させる
   * Proxy サービス: Squid は `infra/00-network/`（`docker-compose.yml` / `squid.conf`）で提供し、到達先や許可ポートは Squid 側の設定で調整する。

#### 最終段階の実装(初期段階の検証後)
* サンプル実装の方針
   * Dockerコンテナのサンプル実装を[all-in-on-image](../../app/docker/autonomous-agent-executor/images/all-in-on-image)に作成する。
   * Dockerコンテナの操作をPythonから行うサンプル実装を[ai_platform_samplelib/application/autonomous](../../app/ai-platform-samplelib/src/ai_platform_samplelib/application/autonomous)に作成する。
   * Dockerコンテナの操作をPythonから行うサンプル実装のテストクライアント(シェルスクリプト)を[test/application/autonomous](../../test/application/autonomous)に配置する。


#### 乖離点の列挙（暫定・優先判断は別途）
* Egress 制御（firewall + Squid Proxy・暫定）
   * 方針/期待: 「LiteLLM Proxy を経由しない不正な LLM 通信のネットワーク遮断（Egress制御）」を実行時ゲートとして担保。
   * 現状:
      * 実行コンテナ側: `all-in-on-image` の `init-firewall.sh` で `iptables -P OUTPUT DROP` を既定にし、`127.0.0.0/8` と「コンテナ所属の Docker サブネット」宛のみ許可する（サブネットはデフォルトルートのIFから自動検出）。
      * Proxy 経路: 外向き HTTP(S) が必要な処理（例: 一部のツールが起動時に行う外部アクセス）は、`HTTP_PROXY` / `HTTPS_PROXY` を `http://squid:3128` に設定して Squid を経由させる（実行コンテナから `squid` を名前解決/到達できるネットワーク構成が前提。設定例: `all-in-on-image/env_compose`）。
      * Proxy サービス: Squid は `infra/00-network/`（`docker-compose.yml` / `squid.conf`）で提供し、到達先や許可ポートは Squid 側の設定で調整する。
   * 影響/評価:
      * サンドボックスから外部インターネット等への「直接通信」（Docker サブネット外宛）は遮断される。
      * Dockerネットワーク内（例: LiteLLM Proxy / Squid 等）へのアクセスは可能。
      * 外向き HTTP(S) は「Squid へ到達できる + 対象プロセスが Proxy 環境変数に従う」範囲で成立する（暫定）。

3. 機密情報の「注入」よりも「ハードコード/配布ファイルへの固定値」が中心
   * 方針/期待: ウォームプール等を見据えた「実行直前の機密注入」（永続化しない）を志向。
   * 現状: `.env_template` や `opencode.jsonc` などに API key が固定値として記載されている箇所がある（PoC用と推測されるが、方針とは方向性が異なる）。
   * 影響: 誤って別環境へ持ち出す/ログ等へ露出するリスクが上がる。将来の「注入方式」への移行時に差し替えコストが発生し得る。

4. workspace に置く想定の `AGENT.md` が見当たらない
   * 方針/期待: workspace に `AGENT.md`（エージェント運用ルール等）を格納して渡す。
   * 現状: リポジトリ内に `AGENT.md` が見当たらず、現行フロー上どこで生成/配置するかも不明。
   * 影響: “何をしてよいか/だめか”の制約を workspace 側で与えづらく、運用ポリシーの具体化が進みにくい。

5. MCP 認証情報の「受け取り→workspace内設定反映」の経路が薄い（部分解消）
   * 方針/期待: Bearer トークン等を引数/環境変数で受け取り、workspace 内の MCP 定義へ反映。
   * 現状（部分解消 → docker(opencode) 経路は解消）:
      * executor は `Authorization` / `trace_id` を受領し、下流（subprocess/コンテナ）へ **タスク単位の環境変数**として注入できる。
      * docker で `opencode` を実行する経路では、workspace 内に **タスク専用の OpenCode 設定**（`workspace/.opencode/opencode.task.json`）を生成し、コンテナ実行時に `OPENCODE_CONFIG=/workspace/.opencode/opencode.task.json` を注入する。
         * 設定ファイル内の値は `{env:...}` プレースホルダで参照し、**Authorization 等の秘匿値をファイルへ永続化しない**。
         * これにより、opencode が起動する MCP（local servers）へ request-scoped な `AI_PLATFORM_AUTHORIZATION` / `AI_PLATFORM_TRACE_ID` を渡せる。
      * 一方で、`create_opencode_json.py` は LLM 接続設定（provider/model/baseURL）中心で、`config/common/opencode.jsonc` は PoC 用の固定値/不整合を含みうるため、上記のタスク専用設定生成を既定経路とする。
   * 未対応:
      * subprocess（ホスト上）で `opencode` を起動する経路の「workspace 内設定への動的反映」は未整備（コンテナ内パス前提の MCP 定義をそのまま使えないため、分岐や別定義が必要）。

6. ウォームプール/Speculative Boot 等の性能方針は未実装（PoC段階）
   * 方針/期待: コールドスタート遅延を隠蔽するための投機起動・ウォームプール。
   * 現状: タスクごとに workspace を切り、コンテナ起動・監視・終了後 remove までの基本線はあるが、ウォームプール等は未実装。
   * 影響: コールドスタート時間がそのままユーザー体験に跳ねる。将来拡張の設計余地を残す必要がある。


### SV型エージェントの実装方針
#### 初期段階
* SV型エージェントはLangGraphで実装し、コーディングエージェントをMCPサーバー経由で起動し、指示とタスクIDを渡す。なおタスクIDはワークスペースのパスの一部にもなる。
* SV型エージェントは実行全体で一意の `trace_id` を採番し、自律型エージェント実行結果の `TaskStatus.trace_id` として伝播する。
   * 実装メモ:
      * SV→自律の呼び出し引数として `trace_id` を渡し、自律側の `TaskStatus.trace_id` に保存する（相関ID）。
      * executor の `task_id` は、サブタスクごとに別採番（UUID等）する（workspace/compose project 名の衝突回避のため）。
      * pause/resume のためのHITLセッションJSONにも `trace_id` を保存し、再開後も同一 `trace_id` を引き継ぐ。
   * 補足: `task_id` と `trace_id` は役割が異なるため、strict に `trace_id = task_id` は要件としない（必要になった場合は別途設計する）。
* 自律型エージェントが呼び出すMCPツールには認証情報(Bearerトークンなど)を渡す必要がある場合がある。
   * 現状はまず、executor が受領した `Authorization` 等を **タスク単位の環境変数**として下流へ注入する（永続化しない）。
   * docker で `opencode` を使う経路は、workspace にタスク専用 OpenCode 設定を生成し、`OPENCODE_CONFIG` を注入して反映する（設定内は `{env:...}` 参照）。
   * subprocess（ホスト実行）での反映は別途対応が必要。
* 自律型エージェントの処理状況は`TaskStatus`として逐次受け取り、それをユーザーまたは非同期連携基盤へと通知する。
* 自律型エージェントの結果には「もっと情報が必要」「この後どうしますか？」といった、ユーザーによる判断が必要となる回答もある。
その場合に、ユーザーからの入力を待つ機能(Human in the loop)を実装する必要がある。
* 重要
  * SV型エージェントと自律型エージェントの情報共有、進捗管理のためのファイルをワークスペース上に配置して、各々がそれを参照したうえで処理を進めること。

##### 初期段階：設計 ↔ 現状実装の対応（SV型）

| 設計項目（初期段階） | 現状 | 実装箇所（例） | 備考 / 乖離 |
| --- | --- | --- | --- |
| SVは LangGraph で実装 | **実装済み** | `ai_platform_samplelib/application/super_visor/core/parallel_agent_workflow.py` | Planner→worker 並列実行→要約の PoC ワークフローを実装。 |
| SV→自律の呼び出しは API/MCP サーバー経由 | **実装済み（MCPに統一）** | `ai_platform_samplelib/application/super_visor/core/tools.py` / `.../core/autonomous_executor_mcp_client.py` | SV→executor は MCP（streamable-http）を既定経路とする。 |
| `trace_id` 採番・伝播（pause/resume でも維持） | **実装済み** | `ai_platform_samplelib/application/super_visor/cli/main.py` / `.../model/hitl_session.py` / `.../core/parallel_agent_workflow.py` | SV が `trace_id` を生成し、executor 実行結果（TaskStatus.trace_id）へ渡せる。HITL セッションJSONにも保持可能。 |
| `TaskStatus` を逐次受け取り、ユーザー/イベント基盤へ通知 | **実装済み（既定は外部通知なし）** | `ai_platform_samplelib/application/super_visor/core/parallel_agent_workflow.py` + `ai_platform_samplelib/event_bus/*` | `publish_task_status()` は行うが、EventBus既定は `noop`。`SV_EVENT_BUS_TYPE=redis` 等で外部化可能。 |
| HITL（承認・一時停止・resume） | **実装済み（CLI中心）** | `ai_platform_samplelib/application/super_visor/cli/main.py` / `.../model/hitl_session.py` / `.../core/parallel_agent_workflow.py` | **乖離（非同期HITL）**: pause/resume は「サブタスク境界」で、executor 実行途中のチェックポイント復元は扱っていない。 |
| SV API を用意（ホスト上プロセス） | **未実装（CLIのみ）** | （SVの FastAPI/HTTP サーバ実装が見当たらない） | **乖離**: `run`/`resume` の CLI が中心。BFF からの HTTP 呼び出しフローは未成立。 |
| workspace 上に「情報共有・進捗管理ファイル」を配置して協調 | **未整備** | executor: `stdout.log` 等は workspace に残るが、SV↔自律で参照する共通ファイル仕様は未定 | **乖離**: SV側は主に in-memory/job store や `.sv_sessions`（セッションJSON）で管理しており、workspace を“共有状態ストア”として扱う設計が薄い。 |
| MCP 認証（Bearer等）の受け取り→workspace 内設定へ反映 | **部分解消（docker(opencode)は対応）** | executor: `ai_platform_samplelib/application/common/request_headers.py` / `.../application/autonomous/core/docker/docker_coding_agent_runner.py` / `.../application/autonomous/core/utils.py` | **現状**: Authorization 等は受領して下流へ環境変数で注入できる。docker で `opencode` を起動する経路は、workspace にタスク専用 OpenCode 設定を生成し、`OPENCODE_CONFIG` 注入で `{env:...}` 参照として反映できる。**未対応**: subprocess（ホスト実行）の設定反映は別途。 |


#### 最終段階の実装(初期段階の後)
* サンプル実装の方針
   * 自律型エージェントの処理はPythonから行うサンプル実装[ai_platform_samplelib/application/autonomous](../../app/ai-platform-samplelib/src/ai_platform_samplelib/application/autonomous)を使用することで実現する。
   * SV型エージェントのサンプル実装は[ai_platform_samplelib/application/super_visor](../../app/ai-platform-samplelib/src/ai_platform_samplelib/application/super_visor/)に作成する。
   * SV型エージェントの検証は、まずコマンドライン（`ai_platform_samplelib.application.super_visor.cli.main`）から実行する。
   * コマンドライン起動用のテストクライアント(シェルスクリプト)を[test/application/super-visor](../../test/application/super-visor)に配置する。
   * CLIは `run` / `resume` を提供する。`-y/--yes` 指定時は承認をスキップし、未指定時はサブタスク単位で承認/停止（セッション保存）を行う。


#### 現状との乖離（暫定・SV型エージェント）
3. `TaskStatus` の逐次通知は既定では外部通知されない（`SV_EVENT_BUS_TYPE` 未設定時）
   * 方針/期待: 自律型エージェントの処理状況を `TaskStatus` として逐次受け取り、ユーザーまたは非同期連携基盤へ通知する。
   * 現状:
      * SV内部では `TaskStatus` を `publish_task_status()` で発行している（例: started/configured/progress/finished/error）。
      * 既定の EventBus は `noop`（環境変数 `SV_EVENT_BUS_TYPE` 未設定の場合）で、PoC の標準実行経路（CLI / テストクライアント）ではイベントは転送されない。
      * EventBus 実装（用途別）:
         * `noop`: 何もしない（既定）。
         * `stdout`: 標準出力へJSONイベントとして出力（外部Pushではなくローカル観測）。
         * `memory`: テスト用（プロセス内のバッファ）。
         * `redis`（Redis Streams）: PoC向けの逐次通知経路（`SV_EVENT_BUS_TYPE=redis`）。
            * 例: `SV_EVENT_BUS_TYPE=redis`
            * 接続先: `SV_EVENT_BUS_REDIS_URL`（最優先）
            * 実行場所による切替（推奨）: `SV_EVENT_BUS_REDIS_URL_IN_HOST` / `SV_EVENT_BUS_REDIS_URL_IN_CONTAINER`
            * Stream名: `SV_EVENT_BUS_REDIS_STREAM`（省略時: `sv.task_status`）
            * 到達性メモ: PoC の docker ネットワーク `ai_platform_internal` は `internal: true`（保護領域）を想定する。
               * Redis を保護領域（internal network）にのみ配置した場合、ホスト実行のSVからRedisへ到達できるとは限らない（環境依存。WSL2/Linuxでは docker bridge のIP直指定で到達できる場合がある一方、Docker Desktop（Windows/Mac）では到達できないことが多い）。
               * PoCではワンセットDoODでSVをコンテナ内に閉じる方針のため、`SV_EVENT_BUS_REDIS_URL_IN_CONTAINER` を優先して運用する。
               * 将来方針: SV を保護領域に閉じたい場合は、(a) executor を別サービス化して SV は HTTP クライアント化する、または (b) 境界でイベントを中継する adapter/bridge（dual-homed）を別コンポーネントとして設ける（アプリ層自身は閉域のまま）。
            * PoCの方針: “逐次通知の外部化” は Redis Streams（`SV_EVENT_BUS_TYPE=redis`）に寄せ、Webhook送信など（HTTP Push）として統合された実装はスコープ外とする。

4. HITL（Human in the loop）はCLI統合は進んだが、非同期HITLは計画境界まで
   * 方針/期待: 「もっと情報が必要」「この後どうしますか？」等の回答に対し、ユーザー入力待ち（非同期HITL）を実装する。
   * 現状:
       * PoCはCLI実行に寄せており、実行前承認（HITL相当）はCLI側に統合済み（`-y/--yes` でスキップ可）。
       * `-y` 未指定時は、計画から抽出したサブタスク単位で「承認/却下/一時停止（セッション保存）」を行い、一時停止した場合はセッションJSONを保存して `resume` で続きから再開できる（保存先は `--session-dir`、省略時は `.sv_sessions`）。
       * ただし現状の pause/resume は「サブタスク実行の境界」での停止であり、コーディングエージェント（executor）実行の“途中”での入力待ち・再開（コンテナ/作業状態のチェックポイント復元）までは扱っていない。
   * 影響: “コーディング実行の途中で承認待ち→再開”を目指す場合、executor の中断/再開戦略（チェックポイント、workspace状態、コンテナ継続/再起動）と、ユーザー入力チャネル（CLI/GUI/API）を含めたワークフロー統合が必要。

5. MCP認証（Bearer等）の「受け取り→workspace内設定反映」は経路により成熟度が異なる
   * 方針/期待: Bearer等を実行時に注入（永続化しない）し、workspace 内の MCP 定義へ反映してツール呼び出しで利用できるようにする。
   * 現状:
      * SV→Executor で `Authorization` / `trace_id` はヘッダとして渡せており、executor はタスク単位 env へ注入できる。
      * docker で `opencode` を起動する経路は、workspace にタスク専用 OpenCode 設定を生成し、`OPENCODE_CONFIG` の注入で opencode 側の MCP 定義へ反映できる。
      * subprocess（ホスト実行）での opencode 設定反映は未整備。
   * 影響/論点:
      * PoC の既定を docker(opencode) 経路に寄せることで “実行時に注入された認証情報で MCP を呼ぶ” ユースケースは成立する。
      * ホスト実行も対象にする場合は、opencode の設定（MCP 定義のパス/起動方式）をホスト用に分岐する必要がある。

## その他 最終段階にいたるまでの実行携帯検討（ワンセットDoOD）
* PoC段階では、SV型エージェントと自律型エージェント（Executor API/ランナー）をワンセットでコンテナ化し、DoOD（docker.sock）で実行コンテナ（all-in-on-image）を起動する方式を採用する。
   * 目的: ホスト実行/SV分離などの本番設計を先送りしつつ、閉域ネットワーク（`ai_platform_internal`）内での実行・疎通を最短で成立させる。
   * 注意: docker.sock をマウントする方式はホストDocker操作権限を強く委譲する（PoCとして受容し、ガードレールで被害面を絞る）。
* 共有workspaceはホスト上の固定ルート配下に作成し、SVと自律と実行コンテナが同じディレクトリを参照する。
   * PoC固定: workspace ルートは `/srv/ai_platform/workspaces` とし、ホストとバンドルコンテナで同一絶対パスにミラーリング（bind mount）する。
   * `workspace_path` は上記ルート配下のホスト絶対パスを使用し、ZIP upload/download は用いない。
   * ルートの環境変数による変更は今後の検討課題とする（変更する場合も同一絶対パスのミラーリングが前提）。
* ガードレール（PoC最低限）
   * Executor API では `EXECUTOR_ALLOWED_WORKSPACE_ROOT=/srv/ai_platform/workspaces` を設定し、許可ルート外の `workspace_path` を拒否する。
