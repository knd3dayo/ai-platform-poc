# AIエージェントの業務適用を見据えた非同期連携基盤（Event Bus）の検討

---

## 1. 目的

生成AIワークロード（WF/SV/自律）は、

* 実行時間が読めない（探索・合議・リトライで長時間化）
* 人間がリアルタイムに応答できない（非同期HITL）
* 外部イベント（PR、コメント、メール承認）で再開される

という性質を持つため、同期HTTP連携だけでは **タイムアウト・再試行地獄**になりがちです。

本書では、Dify/LangGraph/自律型エージェント/周辺システムを疎結合でつなぐために、
中央に **Event Bus（メッセージブローカー）** を置く設計原則を整理します。

---

## 2. Event Busの位置づけ

* Event Busは **Application層の内部実装ではなく**、BFF/Application/（必要によりTool）から利用される **共有ミドルウェア**。
* “どのコンポーネントがPublisher/Subscriberか” を明確にし、責務境界（同期/非同期）を固定する。

関連：`ドキュメント/02_PoC検討/システム構成.md` の「非同期連携基盤（Event Bus）」

---

## 3. 代表ユースケース

### 3.1 長時間実行のジョブ化（LangGraphワーカー）

* BFFが `JOB_REQUESTED` をpublish
* Applicationのワーカーがsubscribeして実行
* 完了時に `JOB_COMPLETED` / `JOB_FAILED` をpublish

### 3.2 HITL（Pause/Resume）

* `HITL_REQUIRED`（interrupt発生）をpublish
* BFFがsubscribeしてフロントへ通知（SSE/WebSocket）
* 人間入力を受けたBFFが `HITL_RESUMED` をpublish

### 3.3 自律型エージェント（PRレビュー駆動）

* GitHub/GitLab WebhookをBFFが受け `PR_CREATED` / `PR_COMMENTED` をpublish
* Applicationがsubscribeしてエージェントジョブ（コンテナ）を起動

---

## 4. イベント設計（最低限の標準）

### 4.1 メッセージ共通属性

* `trace_id`（W3C traceparent準拠）
* `event_type`
* `occurred_at`（UTC推奨）
* `producer`（どのコンポーネントが出したか）
* `idempotency_key`（重複排除キー）

### 4.2 ペイロード（例）

```json
{
  "trace_id": "00-...-...-01",
  "event_type": "HITL_REQUIRED",
  "occurred_at": "2026-02-24T12:00:00Z",
  "producer": "application.langgraph",
  "idempotency_key": "...",
  "data": {
    "status": "PAUSED_FOR_HITL",
    "thread_id": "...",
    "human_task": {
      "type": "APPROVAL",
      "summary": "顧客への送信文面の承認",
      "inputs_schema": {"approve": "boolean", "comment": "string"}
    }
  }
}
```

---

## 5. 冪等性・重複配送・順序

Event Busは一般に **at-least-once** 配送（重複あり）を前提とします。

* **冪等性**：Subscriberは `idempotency_key` / `trace_id + event_type + version` 等で重複排除
* **順序保証の要否**：
  * `trace_id` 単位で順序が必要なイベントは、同一パーティション/同一キューへ
  * 必要ないものは並列化してスループット優先

---

## 6. リトライ・DLQ（必須）

* **リトライ戦略**：指数バックオフ + ジッタ + 最大試行回数
* **DLQ**：一定回数失敗したメッセージはDLQへ隔離し、消失させない
* **DLQ運用**：
  * `trace_id` で原因を追えること
  * DLQを起点に再実行（replay）できること

---

## 7. セキュリティ（最低限）

* **メッセージの改ざん防止**：署名 or mTLS（環境に応じて）
* **PIIを載せない**：イベントには参照キー（artifact_id等）を載せ、本文は別ストアへ
* **テナント境界**：マルチテナントの場合はトピック/namespace分離

---

## 8. PoC→初期本番の意思決定ポイント

* **採用技術**：Redis Streams / RabbitMQ / NATS / Kafka / Azure Service Bus など
  * PoC：運用が軽いもの（例：Redis Streams）
  * 初期本番：DLQ・監視・権限分離を含めて選定
* **イベントの粒度**：
  * 大粒度（Job/HITL/完了）から開始し、必要に応じて細分化

---

## 9. アンチパターン

* 同期API連携のみで長時間処理を待つ（タイムアウト）
* `trace_id` を載せない（観測不能）
* DLQがない（メッセージ消失で原因不明）
* PIIや巨大な本文をイベントに載せる（漏洩・肥大化）

---

## 10. 関連ドキュメント

* 集大成：[`AIエージェントの業務適用を見据えた生成AIアーキテクチャ検討.md`](./AIエージェントの業務適用を見据えた生成AIアーキテクチャ検討.md)
* BFF層：[`AIエージェントの業務適用を見据えたAPIゲートウェイBFF層の検討.md`](./AIエージェントの業務適用を見据えたAPIゲートウェイBFF層の検討.md)
* 技術メモ（非同期HITL）：[`修正版_技術メモ_ワークフローの状態管理と非同期HITLについて.md`](../02_PoC検討/修正版_技術メモ_ワークフローの状態管理と非同期HITLについて.md)
