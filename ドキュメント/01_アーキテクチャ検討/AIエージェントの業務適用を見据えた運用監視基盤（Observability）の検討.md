# AIエージェントの業務適用を見据えた運用/監視基盤（Observability）の検討

---

## 1. 目的

生成AIエージェント（WF/SV/自律）は、従来アプリに比べて以下が起きやすいです。

* 実行時間が長い・不確実（タイムアウト、途中停止、再開）
* 結果の正当性が確率的（評価が必要）
* 事故の原因が多層（入力/モデル/ツール/権限/データ鮮度）
* コストが可変（トークン・外部API呼び出し）

そのため「動いているか」だけではなく、**止められる・追える・説明できる**運用監視が必須です。

本書では、分散トレーシング（`trace_id`）を軸に、BFF/Application/AI Assurance/Tool/Event Busを串刺しにするための設計を整理します。

---

## 2. 観測対象（何を測るか）

### 2.1 可用性（Availability）

* API成功率、p95/p99レイテンシ
* キュー滞留（バックログ）
* ワーカー稼働数、失敗率

### 2.2 正しさ（Quality / Safety）

* ガードレール遮断率（PII/禁則/インジェクション）
* LLM-as-a-Judge / Ragas 等の評価スコア（faithfulness等）
* HITL発生率、差戻し率

### 2.3 コスト（Cost）

* トークン消費、モデル別コスト
* 1ジョブあたりの平均/最大コスト

---

## 3. 相関ID（trace_id）中心設計

### 3.1 原則

* `trace_id` を全コンポーネントで必須にし、
  * HTTPヘッダ（`traceparent`）
  * Event Busメッセージ属性
  * 永続ストア（状態管理、監査ログ）
  に伝播させる。

### 3.2 なぜ必須か

* 事故時に「誰の依頼が、どの経路で、どこで失敗したか」を即時に辿れる
* HITLで数日止まっても、同一キーで追跡できる
* DLQのメッセージを運用UIから逆引きできる

---

## 4. ログ・メトリクス・トレースの設計

### 4.1 トレース（OpenTelemetry推奨）

* Span例：
  * BFF request
  * Application job
  * LiteLLM proxy
  * MCP tool call
  * Event Bus publish/consume

### 4.2 ログ（監査/フォレンジック向け）

* 必須項目：`trace_id`, `user_id`, `tenant`, `component`, `action`, `status`, `policy_decision`
* PIIをログに出さない（マスク/トークン化）

### 4.3 メトリクス（SLO/アラート向け）

* Job完了率、失敗率
* HITL待機時間（平均/最大）
* キュー滞留数、DLQ投入数

---

## 5. 評価（Evaluation）を運用に組み込む

生成AIは「測らないと劣化に気づけない」ため、評価を運用基盤に取り込みます。

* **Shadow Eval**：本番レスポンスに影響しない影評価
* **Async Monitor**：応答後に採点し、スコア低下でアラート
* **Synchronous Gate**：対外送信などは応答前に遮断/HITL

評価結果も `trace_id` に紐付けて保存し、改善サイクル（プロンプト/モデル/データ）に接続する。

---

## 6. 運用UI（最低限ほしい画面/検索）

* `trace_id` 検索
* ステータス（RUNNING/PAUSED_FOR_HITL/COMPLETED/FAILED）一覧
* HITL待ち一覧（担当/期限/承認内容）
* DLQ一覧（再実行ボタン）

---

## 7. PoC→初期本番での最小セット

* **Langfuse**（Tracing + Eval 連携）
* **OpenTelemetry**（traceparent伝播）
* **Event BusのDLQ監視**
* `trace_id` をキーにした状態管理テーブル（簡易で良い）

---

## 8. アンチパターン

* trace_id が各所で変わる/欠落する（追跡できない）
* HITL待ちをログだけで追う（運用者が疲弊）
* コスト上限（Budget）と停止装置（Kill Switch）がない
* 評価をPoCで終わらせて運用に繋げない（Driftに気づけない）

---

## 9. 関連ドキュメント

* 集大成：[`AIエージェントの業務適用を見据えた生成AIアーキテクチャ検討.md`](./AIエージェントの業務適用を見据えた生成AIアーキテクチャ検討.md)
* BFF層：[`AIエージェントの業務適用を見据えたAPIゲートウェイBFF層の検討.md`](./AIエージェントの業務適用を見据えたAPIゲートウェイBFF層の検討.md)
* 非同期連携基盤：[`AIエージェントの業務適用を見据えた非同期連携基盤（Event Bus）の検討.md`](./AIエージェントの業務適用を見据えた非同期連携基盤（Event Bus）の検討.md)
* AI Assurance：[`AIエージェントの業務適用を見据えた生成AI信頼性保障層の検討.md`](./AIエージェントの業務適用を見据えた生成AI信頼性保障層の検討.md)
