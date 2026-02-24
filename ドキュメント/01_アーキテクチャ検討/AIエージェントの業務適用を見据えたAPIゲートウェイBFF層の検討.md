# AIエージェントの業務適用を見据えたAPIゲートウェイ/BFF層の検討

---

## 1. 目的

生成AIアプリケーションをエンタープライズ業務に適用する際、入口（north）を単なるHTTP中継として扱うと、

* 認証・認可のばらつき
* ID（trace/workflow/thread等）の不整合
* 非同期ジョブ（HITL/長時間実行）の起点/通知経路の混乱
* フロントエンドが各バックエンド仕様に引きずられる

といった運用不能に繋がります。

本書では **APIゲートウェイ/BFF層を「入口の標準化ポイント」**として定義し、
Application層（AIの脳）/Tool層（手足）/AI Assurance（関所）へ安全に接続するための設計原則を整理します。

> 注：生成AIの回答チェックやガードレール等の **意味論的な統制** は、BFFに閉じず、
> 専用のAI Assuranceコンポーネント（例：LiteLLM Proxy / MCPゲートウェイ）へ寄せるのが推奨です。

---

## 2. BFFが担う責務（やること/やらないこと）

### 2.1 やること（入口としての最小責務）

* **境界防御**：JWT検証、WAF、レート制限、入力サイズ制限、CORS等
* **認証の強制**：Bearerトークン必須化（必要に応じてセッション/リフレッシュ）
* **相関IDの発行と伝播**：W3C `traceparent` 準拠の `trace_id` 発行・伝播
* **IDのマッピング**：
  * `trace_id` ⇔ `workflow_run_id`（Dify）
  * `trace_id` ⇔ `thread_id`（LangGraph）
  * （必要なら）`case_id`/`ticket_id` 等の業務ID
* **API形状の正規化**：フロントが「AI基盤の内部差異」を意識しない統一API
* **通知経路の提供**：SSE/WebSocket等で「完了」「HITL発生」などのイベントをフロントへpush
* **外部Webhook入口**：Dify/GitHub/GitLab等のWebhookを受けて正規化し、Event Busにpublish

### 2.2 やらないこと（アンチパターン）

* **AIの推論ロジックをBFFに持たせる**（プロンプト、合議、HITLの状態主権など）
* **生成AI出力の意味論評価をBFFだけで完結させる**
  * 理由：機能が肥大化し、Assuranceの一貫性/再利用性が壊れやすい
* **Tool層の個別API仕様をフロントへ露出させる**（フロントがSaaSごとに分岐する）

---

## 3. 推奨アーキテクチャ：入口統合（APIM）＋BFF（アプリ境界）

### 3.1 役割分担

* **API Gateway（例：Azure APIM）**
  * 決定論的な防御（JWT検証、WAF、レート制限、IP制限、TLS終端など）
  * ルーティングと段階的移行（blue/green、v1/v2）

* **BFF（例：FastAPI）**
  * `trace_id` の発行/伝播、IDマッピング
  * ペイロード変換（フロント↔バックエンド差分の吸収）
  * 非同期イベントの配信（SSE/WebSocket）
  * Webhook入口（Dify/GitHub等）

---

## 4. 非同期（長時間処理・HITL）前提のBFF設計

### 4.1 「同期応答」から「受付票＋通知」へ

生成AI処理は実行時間が予測不能です。BFFは以下を原則化します。

* **受付は即答**：BFFは `202 Accepted` を返し、`trace_id` と受付状態を返す
* **完了通知はpush**：SSE/WebSocketで `trace_id` をキーにフロントへ通知
* **状態照会API**：pushを取り逃した場合に `GET /jobs/{trace_id}` で状態取得

### 4.2 HITL（Pause/Resume）の入口

* Pause：Applicationが `INTERRUPTED` をEvent Busへpublish
* Notify：BFFがsubscribeしてフロントへpush（＋メール/Teams等への通知連携も可能）
* Resume：フロントの承認入力をBFFが受け、`trace_id + user_input` をApplicationへ渡す

---

## 5. `trace_id` とIDマッピング（最重要）

### 5.1 目的

* **分散トレーシング**：入口→BFF→Application→Assurance→Tool→（Event Bus）を串刺し
* **製品ID差異の吸収**：Dify/LangGraph/自律型コンテナなどはID体系が異なる

### 5.2 推奨ルール

* `traceparent` 形式で `trace_id` を発行し、
  * HTTPヘッダ
  * Event Busメッセージ属性
  * ジョブペイロード
  に必ず伝播する。

* `trace_id` を「人間の問い合わせ・運用の主キー」とし、
  * 画面上の検索
  * アラート
  * 監査
  * DLQ調査
  を統一する。

---

## 6. 代表的なAPI形状（例）

### 6.1 受付（非同期）

* `POST /ai/jobs`

レスポンス例：

```json
{
  "trace_id": "00-...-...-01",
  "status": "ACCEPTED"
}
```

### 6.2 状態照会

* `GET /ai/jobs/{trace_id}`

```json
{
  "trace_id": "00-...-...-01",
  "status": "PAUSED_FOR_HITL",
  "hitl": {
    "type": "APPROVAL",
    "inputs_schema": {"approve": "boolean", "comment": "string"}
  }
}
```

### 6.3 Resume（承認）

* `POST /ai/jobs/{trace_id}/resume`

---

## 7. 意思決定ポイント（PoC→初期本番）

* **SSE vs WebSocket**：
  * PoCはSSEが実装/運用が軽い（HTTPだけで良い）
  * 双方向が必要ならWebSocket
* **BFFのステート**：
  * 原則ステートレス
  * 例外としてIDマッピングはRedis等に置く（期限付き）
* **Webhook入口の増加**（GitHub/GitLab/Dify等）：
  * 入口はBFFに集約し、Event Busへ正規化イベントとしてpublish

---

## 8. アンチパターン集

* **BFFに「業務ルール」や「評価ロジック」を実装して肥大化**（属人化・再利用不能）
* **同期APIで長時間待機**（タイムアウト・再試行地獄）
* **相関IDがない/ばらばら**（障害時に追えない）
* **フロントがDify/LangGraphのAPI仕様を直に理解している**（置換不能）

---

## 9. 関連ドキュメント

* 集大成：[`AIエージェントの業務適用を見据えた生成AIアーキテクチャ検討.md`](./AIエージェントの業務適用を見据えた生成AIアーキテクチャ検討.md)
* Application層：[`修正版_AIエージェントの業務適用を見据えた生成AIアプリケーション層の検討.md`](./修正版_AIエージェントの業務適用を見据えた生成AIアプリケーション層の検討.md)
* 非同期連携基盤：[`AIエージェントの業務適用を見据えた非同期連携基盤（Event Bus）の検討.md`](./AIエージェントの業務適用を見据えた非同期連携基盤（Event Bus）の検討.md)
* 運用監視基盤：[`AIエージェントの業務適用を見据えた運用監視基盤（Observability）の検討.md`](./AIエージェントの業務適用を見据えた運用監視基盤（Observability）の検討.md)
