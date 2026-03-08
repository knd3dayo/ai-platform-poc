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
### SV型エージェントの実装方針
* SV型エージェントはLangGraphで実装し、コーディングエージェントのコンテナをPython経由で起動し、
指示とタスクIDを渡す。なおタスクIDはワークスペースのパスの一部にもなる。
* SV型エージェントは実行全体で一意の `trace_id` を採番し、自律型エージェント実行結果の `TaskStatus.trace_id` として伝播する。
   * 実装メモ:
      * SV→自律の呼び出し引数として `trace_id` を渡し、自律側の `TaskStatus.trace_id` に保存する（相関ID）。
      * executor の `task_id` は、サブタスクごとに別採番（UUID等）する（workspace/compose project 名の衝突回避のため）。
      * pause/resume のためのHITLセッションJSONにも `trace_id` を保存し、再開後も同一 `trace_id` を引き継ぐ。
   * 補足: `task_id` と `trace_id` は役割が異なるため、strict に `trace_id = task_id` は要件としない（必要になった場合は別途設計する）。
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
  * SV型エージェントで設定したLLM_MODELなどの環境変数が自律型エージェントに確実に渡されること。
  * SV型エージェントと自律型エージェントの情報共有、進捗管理のためのファイルをワークスペース上に配置して、各々がそれを参照したうえで処理を進めること。
  
#### 現状との乖離（暫定・SV型エージェント）
3. `TaskStatus` の逐次通知がSV経路に乗っていない
   * 方針/期待: 自律型エージェントの処理状況を `TaskStatus` として逐次受け取り、ユーザーまたは非同期連携基盤へ通知する。
    * 現状:
       * SV側の状態管理は `TaskStatus` に統一済み。ただしSV APIは削除しており、ユーザー向け取得手段は現状CLI表示が中心。
       * SV内部では `TaskStatus` を `publish_task_status()` で発行している（例: started/configured/progress/finished/error）。ただしEventBusは PoC 向けモック（`noop/stdout/memory`）のみで、既定値は `noop`（環境変数 `SV_EVENT_BUS_TYPE` 未設定の場合）。そのため PoC の標準実行経路（CLI / テストクライアント）では、外部の非同期連携基盤へは実質的に通知されない。
       * なお “逐次通知の観測” 自体は、`SV_EVENT_BUS_TYPE=stdout` により標準出力へJSONイベントとして出せる（外部Pushではなくローカル観測）。
      * Webhook送信などのデモは別途検討対象だが、`TaskStatus` の逐次通知として統合された実装は未整備。
    * 影響:
       * “逐次通知（非同期連携基盤へPush）”に寄せる場合は、通知先（Webhook/Event Bus）とイベント粒度（status/sub_status/ログ/成果物）を設計し、EventBus の実装（例: Redis/Kafka/HTTP など）と設定注入（compose/env）を追加する必要がある。

4. HITL（Human in the loop）はCLI統合は進んだが、非同期HITLは計画境界まで
   * 方針/期待: 「もっと情報が必要」「この後どうしますか？」等の回答に対し、ユーザー入力待ち（非同期HITL）を実装する。
   * 現状:
       * PoCはCLI実行に寄せており、実行前承認（HITL相当）はCLI側に統合済み（`-y/--yes` でスキップ可）。
       * `-y` 未指定時は、計画から抽出したサブタスク単位で「承認/却下/一時停止（セッション保存）」を行い、一時停止した場合はセッションJSONを保存して `resume` で続きから再開できる（保存先は `--session-dir`、省略時は `.sv_sessions`）。
       * ただし現状の pause/resume は「サブタスク実行の境界」での停止であり、コーディングエージェント（executor）実行の“途中”での入力待ち・再開（コンテナ/作業状態のチェックポイント復元）までは扱っていない。
   * 影響: “コーディング実行の途中で承認待ち→再開”を目指す場合、executor の中断/再開戦略（チェックポイント、workspace状態、コンテナ継続/再起動）と、ユーザー入力チャネル（CLI/GUI/API）を含めたワークフロー統合が必要。

5. MCP認証（Bearer等）の「受け取り→workspace内設定反映」の経路が確認できない
   * 方針/期待: Bearer等を引数/環境変数で受け取り、workspace 内の MCP 定義へ反映する。
   * 現状: SV→Executor のツール引数は `prompt`/`zip`/`initial_files`/`timeout` が中心で、Bearer等を受け取って workspace 設定（MCP定義）へ反映する処理が見当たらない。
   * 影響: “実行時に注入された認証情報で MCP を呼ぶ”ユースケースが、現状のSV経路では成立しにくい。


### 自律型エージェントの実装方針
* Claude Code、Cline CLI、OpenCodeのようなコーディングエージェントをDockerコンテナ上で実行する。
  * コーディングエージェントには、ソースコードやログファイル、実行の前提となるデータファイルを格納したワークスペースを
ホスト側から渡す。
  * ワークスペースにはAGENT.mdや利用可能なMCPの定義を記述した設定ファイルも格納する。
* Egress 制御（Dockerネットワーク内のみ許可・暫定）
   * 方針/期待: 「LiteLLM Proxy を経由しない不正な LLM 通信のネットワーク遮断（Egress制御）」を実行時ゲートとして担保。
   * 現状: `all-in-on-image` の `init-firewall.sh` で `iptables -P OUTPUT DROP` を既定にし、`127.0.0.0/8` とコンテナ所属のDockerサブネット宛のみ許可する（サブネットはデフォルトルートのIFから自動検出）。
   * 影響/評価: サンドボックスから外部インターネット等への直接通信は遮断される。Dockerネットワーク内（例: LiteLLM Proxy等）へのアクセスは可能。
* 自律型エージェントの `task_id` は外部から指定可能で、未指定の場合はUUID等で自動採番する。

* サンプル実装の方針
   * Dockerコンテナのサンプル実装を[all-in-on-image](../../app/docker/autonomous-agent-executor/images/all-in-on-image)に作成する。
   * Dockerコンテナの操作をPythonから行うサンプル実装を[ai_platform_samplelib/application/autonomous](../../app/ai-platform-samplelib/src/ai_platform_samplelib/application/autonomous)に作成する。
   * Dockerコンテナの操作をPythonから行うサンプル実装のテストクライアント(シェルスクリプト)を[test/application/autonomous](../../test/application/autonomous)に配置する。


#### 乖離点の列挙（暫定・優先判断は別途）
3. 機密情報の「注入」よりも「ハードコード/配布ファイルへの固定値」が中心
   * 方針/期待: ウォームプール等を見据えた「実行直前の機密注入」（永続化しない）を志向。
   * 現状: `.env_template` や `opencode.jsonc` などに API key が固定値として記載されている箇所がある（PoC用と推測されるが、方針とは方向性が異なる）。
   * 影響: 誤って別環境へ持ち出す/ログ等へ露出するリスクが上がる。将来の「注入方式」への移行時に差し替えコストが発生し得る。

4. workspace に置く想定の `AGENT.md` が見当たらない
   * 方針/期待: workspace に `AGENT.md`（エージェント運用ルール等）を格納して渡す。
   * 現状: リポジトリ内に `AGENT.md` が見当たらず、現行フロー上どこで生成/配置するかも不明。
   * 影響: “何をしてよいか/だめか”の制約を workspace 側で与えづらく、運用ポリシーの具体化が進みにくい。

5. MCP 認証情報の「受け取り→workspace内設定反映」の経路が薄い
   * 方針/期待: Bearer トークン等を引数/環境変数で受け取り、workspace 内の MCP 定義へ反映。
   * 現状: `create_opencode_json.py` は LLM 接続設定（provider/model/baseURL）中心で、`config/common/opencode.jsonc` の MCP 定義は固定値になっている。
   * 影響: “実行時に注入された認証情報で MCP を呼ぶ”ユースケースが、今の default 設定では成立しにくい。

6. 生成物（`src-updated`）内に環境ファイルが混在し、設定キーも揺れている
   * 方針/期待: 実行時に参照される env キー（例: `COMPOSE_DIRECTORY`）が一貫していること。
   * 現状: `test/application/autonomous/src-updated/` に過去の `.env_*` が残っており、`COMPOSE_PROJECT_DIRECTORY` のように実装が参照しないキーも含まれる。
   * 影響: 人手運用時に誤って参照/コピーされやすく、トラブルシュートが難しくなる。

7. ウォームプール/Speculative Boot 等の性能方針は未実装（PoC段階）
   * 方針/期待: コールドスタート遅延を隠蔽するための投機起動・ウォームプール。
   * 現状: タスクごとに workspace を切り、コンテナ起動・監視・終了後 remove までの基本線はあるが、ウォームプール等は未実装。
   * 影響: コールドスタート時間がそのままユーザー体験に跳ねる。将来拡張の設計余地を残す必要がある。

