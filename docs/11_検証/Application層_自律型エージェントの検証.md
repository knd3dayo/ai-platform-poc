# Application層 自律型エージェントの検証

## 概要
* SV型エージェントから呼び出される、自律型エージェントの実装検証
* WF型のように手順が固定できず、タスク解決のための道筋が探索的になる領域に適用する。
* 最小単位は「目標」と「利用可能なツール群」であり、AIが自身で計画と実行を繰り返す。

## 方針
* Claude Code、Cline CLI、OpenCodeのようなコーディングエージェントをDockerコンテナ上で実行する。
* コーディングエージェントには、ソースコードやログファイル、実行の前提となるデータファイルを格納したワークスペースを
ホスト側から渡す。
* ワークスペースにはAGENT.mdや利用可能なMCPの定義を記述した設定ファイルも格納する。
* SV型エージェントはLangGraphで実装し、コーディングエージェントのコンテナをPython経由で起動し、
指示とタスクIDを渡す。なおタスクIDはワークスペースのパスの一部にもなる。
* SV型エージェントが自律型エージェントに渡すタスクIDはシステム全体で一意の値となるトレースIDを使用する。
* 自律型エージェントが呼び出すMCPツールには認証情報(Bearerトークンなど)を渡す必要がある場合がある。
その場合、自律型エージェントは引数または環境変数としてそれらの情報を受け取り、ワークスペース内のMCPの定義を記述した設定ファイルに反映する。

## 方針 vs 実装 整合性レビュー（自律型エージェントSandbox）

PoC手順・技術課題と対応方針・本ドキュメントを一次ソースとして、(1) Sandbox構築/起動フロー、(2) 自律型エージェント実行（Python→Docker）、(3) Egress/機密/トレース/MCP注入の観点で実装を棚卸しし、乖離点を根拠付きで列挙する。優先順位付け（方針優先か実装優先か）は後段で検討できる形に整理する。

### Steps
1. 方針抽出（一次ソース3点）
   * [docs/03_PoC手順/01_生成AI基盤インフラ構築手順.md](../03_PoC手順/01_生成AI基盤インフラ構築手順.md) から「Sandboxの構築方法（build.sh 事前ビルド、run.sh 実行、外部ネットワーク ai_platform_net）」を抽出
   * [docs/01_アーキテクチャ検討/技術課題と対応方針.md](../01_アーキテクチャ検討/技術課題と対応方針.md) から「Ephemeral/ウォームプール/機密注入/Egress制御」等の要件を抽出
   * 本ドキュメントから「Docker上でのコーディングエージェント、Pythonからの起動、workspaceへAGENT.md/MCP定義配置、trace ID を task_id として使用、MCPにBearer等注入」を抽出
2. 実装の責務分解と対応付け
   * CLI系: `app/cli/autonomous-agent-executor/test_client.sh` と環境変数（`.env`）の役割確認
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

### Relevant files
* `app/cli/autonomous-agent-executor/test_client.sh` — CLI実行の入口（COMPOSE_COMMAND選択、samplelib CLI呼び出し）
* `app/cli/autonomous-agent-executor/.env` — COMPOSE_DIRECTORY 等のcompose設定、CODE_AGENT_CONFIG_PATH指定
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

### Verification
1. ドキュメント上の期待フローに従い、all-in-on-image の build.sh→run.sh が動く前提（環境変数/ネットワーク/イメージ名）が揃っているか点検する。
2. samplelib CLI（`python -m ai_platform_samplelib.application.autonomous.cli.main run ...`）が参照する環境変数（COMPOSE_DIRECTORY/FILE/SERVICE_NAME/COMMAND 等）と、各 `.env` のキーが一致しているか確認する。
3. 乖離点のうち「動作上の致命傷（パス不整合/存在しないディレクトリ参照）」と「将来方針未達（Egress/機密注入/AGENT.md）」を分けてリスト化する。

### 乖離点の列挙（暫定・優先判断は別途）

1. 手順書にあるCLIパスが存在しない
   * 方針/期待: PoC手順に `app/docker/autonomous-agent-executor/cli` が登場する。
   * 現状: 当該ディレクトリは存在せず、CLI相当は `app/cli/autonomous-agent-executor` 配下（例: `test_client.sh`）にある。
   * 影響: 手順通りに実行すると詰まる（オンボーディング/再現性の低下）。

2. `CODE_AGENT_CONFIG_PATH` が指すディレクトリが存在しない
   * 方針/期待: 「workspace に AGENT.md や MCP 定義など設定ファイルを格納」のため、CLI から config ディレクトリを `-s` で渡せること。
   * 現状: `app/cli/autonomous-agent-executor/.env(.env_template)` は `CODE_AGENT_CONFIG_PATH=.../config/common` を指すが、`app/cli/autonomous-agent-executor/config/common` が存在しない。
   * 影響: `test_client.sh` の `-s ${CODE_AGENT_CONFIG_PATH}` が実質無効となり、「設定ファイルを workspace に渡す」方針が実行経路に乗らない。

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
   * 現状: `app/cli/autonomous-agent-executor/src-updated/` に過去の `.env_*` が残っており、`COMPOSE_PROJECT_DIRECTORY` のように実装が参照しないキーも含まれる。
   * 影響: 人手運用時に誤って参照/コピーされやすく、トラブルシュートが難しくなる。

8. ウォームプール/Speculative Boot 等の性能方針は未実装（PoC段階）
   * 方針/期待: コールドスタート遅延を隠蔽するための投機起動・ウォームプール。
   * 現状: タスクごとに workspace を切り、コンテナ起動・監視・終了後 remove までの基本線はあるが、ウォームプール等は未実装。
   * 影響: コールドスタート時間がそのままユーザー体験に跳ねる。将来拡張の設計余地を残す必要がある。

### Decisions
* 今回は「逸脱の列挙（影響/根拠付き）」までで止め、修正TODO化や優先順位付けは別途行う。
* 方針の一次ソースは上記3ドキュメント（＋必要に応じて補助資料）とする。
