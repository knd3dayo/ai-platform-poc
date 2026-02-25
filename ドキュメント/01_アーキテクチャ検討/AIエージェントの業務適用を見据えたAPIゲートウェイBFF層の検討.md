# AIエージェントの業務適用を見据えたAPIゲートウェイ/BFF層の検討

## 1. 目的

生成AIアプリケーションをエンタープライズ業務に適用する際、入口（north）を単なるHTTP中継として扱うと、

* 認証・認可のばらつき
* ID（trace/workflow/thread等）の不整合
* 非同期ジョブ（HITL/長時間実行）の起点/通知経路の混乱
* フロントエンドが各バックエンド仕様に引きずられる

といった運用不能（カオス）に繋がります。
本書では **APIゲートウェイ/BFF層を「入口の標準化ポイント」かつ「同期・非同期の境界線」**として定義し、Application層（AIの脳）や非同期連携基盤（Event Bus）へ安全かつ効率的に接続するための設計原則を整理します。

> 注：生成AIの回答チェックやガードレール等の **意味論的な統制** は、BFFに閉じず、専用のAI Assuranceコンポーネント（例：LiteLLM Proxy / MCPゲートウェイ）へ寄せるのが推奨です。

---

## 2. BFF層と非同期連携基盤（Event Bus / 状態管理DB）との関係【最重要】

BFF層は、単なるプロキシではなく、背後にある「非同期連携基盤」を統制するオーケストレーターとして機能します。

### 2.1 状態管理DBの読み書き（I/O）の独占

* **原則**: システム全体の「現在のジョブ状態」や「IDマッピング」を永続化する **状態管理DB（NoSQL等）へのアクセス権限は、BFF層が完全に独占**します。
* **理由**: Application層のエージェント（LangGraphやコンテナ）に直接DBを更新させると、クレデンシャルの分散やスキーマの密結合が発生するためです。

### 2.2 トラフィックのルーティング（Fast Track / Slow Track）

BFFはリクエストの性質に応じ、後続の処理経路（同期か非同期か）を動的にルーティングします。

* **Fast Track（Event Bus バイパス）**: 単純なチャット応答や情報検索など、即時応答が可能な軽量処理。BFFが直接APIを叩き、SSEでフロントエンドへ同期的にストリーミングを返します。
* **Slow Track（Event Bus 経由）**: エージェントの自律実行やHITL（承認）を伴う重量処理。BFFはDBに初期状態を書き込み、フロントへ即座に `202 Accepted` を返却後、メッセージを **Event Bus** へパブリッシュして非同期ワーカーへ委譲します。

### 2.3 フロントエンドへの状態同期とセッション復帰

ブラウザ再起動時など、フロントエンドが状態を復元する際、BFFは以下の順序で振る舞います。

1. **初期状態の取得**: フロントエンドからの `GET /jobs` に対し、BFFはEvent Busを見ず、**状態管理DB** から最新のスナップショットを引いて即答します。
2. **リアルタイム通知**: その後確立されたSSEコネクションに対し、BFFは **Event Bus** から流れてくる業務イベント（完了、HITL発生など）を購読（Subscribe）し、該当ユーザーへプッシュ配信します。

---

## 3. BFFが担う責務（やること/やらないこと）

### 3.1 やること（入口としての最小責務）

* **境界防御**: JWT検証、WAF、レート制限、入力サイズ制限、CORS等（※APIMと分担）
* **相関IDの発行と伝播**: W3C `traceparent` 準拠の `trace_id` 発行・伝播
* **状態とIDの永続化**: 状態管理DBを用いた `trace_id` と各ツールID（`workflow_run_id`, `thread_id` 等）のマッピングとステータス管理
* **API形状の正規化**: フロントが「AI基盤の内部差異」を意識しない統一APIの提供
* **通知経路の提供**: SSE/WebSocket等によるEvent Busからの非同期イベントのpush配信
* **外部Webhook入口**: GitHub/GitLab等のWebhookを受けて正規化し、Event Busにpublish

### 3.2 やらないこと（アンチパターン）

* **BFF自身のステート保持**: BFFプロセス（メモリ内）にジョブ状態やWebSocketセッションを抱え込むこと（スケールアウト不可になるため、必ず外部のDBやRedis Pub/Subへ逃がす）。
* **AIの推論ロジックの実装**: プロンプトの組み立てやHITLの分岐ロジックをBFFに持たせること。
* **Event Busのフロントエンドへの直接露出**: セキュリティとノイズ軽減のため、フロントエンドは必ずBFFを介して通信する。

---

## 4. 推奨アーキテクチャ：入口統合（APIM）＋BFF（アプリ境界）

### 4.1 役割分担

* **API Gateway（例：Azure APIM）**
* 決定論的な防御（JWT検証、WAF、レート制限、IP制限、TLS終端など）
* ルーティングと段階的移行（blue/green、v1/v2）


* **BFF（例：FastAPI）**
* `trace_id` の発行/伝播、IDマッピング（状態管理DBとのI/O）
* Fast Track / Slow Track のルーティング
* 非同期イベントの配信（Event BusからのSSE/WebSocket変換）



---

## 5. `trace_id` とIDマッピング

### 5.1 目的

* **分散トレーシング**: 入口→BFF→Application→Assurance→Tool→（Event Bus）を串刺しにする。
* **製品ID差異の吸収**: Dify/LangGraph/自律型コンテナなどの異なるID体系をBFFの「状態管理DB」で紐付け、フロントエンドには `trace_id` のみを見せる。

### 5.2 推奨ルール

* `traceparent` 形式で `trace_id` を発行し、HTTPヘッダ、Event Busメッセージ属性、ジョブペイロードに必ず伝播する。
* `trace_id` を「人間の問い合わせ・運用の主キー」とし、画面検索、アラート、監査、DLQ調査を統一する。

---

## 6. 代表的なAPI形状（例）

### 6.1 受付（Slow Track / 非同期）

* `POST /ai/jobs`
レスポンス例：

```json
{
  "trace_id": "00-...-...-01",
  "status": "ACCEPTED"
}

```

※裏でBFFが状態管理DBに `RUNNING` でINSERTし、Event BusへPublishする。

### 6.2 状態照会（UI初期描画用）

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

※Event Busではなく、状態管理DBから最新スナップショットを引いて返す。

### 6.3 Resume（承認）

* `POST /ai/jobs/{trace_id}/resume`
※BFFが状態管理DBを `RESUMED` に更新し、Event Busへ再開命令をPublishする。

---

## 7. 意思決定ポイント（PoC→初期本番）

* **SSE vs WebSocket**:
* PoCは一方向プッシュのみで済むSSEが実装/運用が軽い（HTTPだけで良い）。双方向のリアルタイム性が必須になればWebSocketを検討。


* **状態管理DBの選定**:
* PoCであってもBFFをステートレスに保つため、IDマッピングとステータス管理は外部のKVS（Redis）やドキュメントDB（MongoDB/CosmosDB）に持たせる。


* **Webhook入口の集約**:
* GitHub/GitLab等の外部イベントも直接エージェントを叩かせず、一度BFFで受け、`trace_id` を付与した上でEvent BusへPublishさせる。



### 7.1 推奨構成（PoC）

PoCでは「まず動かす」「運用の事故を減らす」ことを優先し、構成要素を絞ります。

* **API Gateway**: Azure APIM（またはNginx/Kong）
* **BFF**: FastAPI（ステートレス実装）
* **状態管理DB**: Redis（KVS）または MongoDB
* **フロントへの通知**: SSE（Server-Sent Events）
* **非同期連携基盤**: Redis Streams（Event Busとして機能）
* **観測**: Langfuse + OpenTelemetry

---

## 8. アンチパターン集

* ❌ **BFFプロセス内（メモリ）での状態・セッション保持**（スケールアウトが不可能になる）
* ❌ **BFFでのAI推論・評価ロジックの実装**（属人化・再利用不能）
* ❌ **同期APIで長時間待機させる**（タイムアウト・再試行地獄）
* ❌ **フロントエンドにEvent Busを直接サブスクライブさせる**（セキュリティ違反と大量のノイズ）
* ❌ **フロントエンドがDify/LangGraphのネイティブAPI仕様を直に呼ぶ**（バックエンドの置換不能、APIキー漏洩リスク）

---

## 9. 関連ドキュメント

* 集大成：[`AIエージェントの業務適用を見据えた生成AIアーキテクチャ検討.md`](./AIエージェントの業務適用を見据えた生成AIアーキテクチャ検討.md)
* Application層：[`修正版_AIエージェントの業務適用を見据えた生成AIアプリケーション層の検討.md`](./修正版_AIエージェントの業務適用を見据えた生成AIアプリケーション層の検討.md)
* 非同期連携基盤：[`AIエージェントの業務適用を見据えた非同期連携基盤（Event Bus）の検討.md`](./AIエージェントの業務適用を見据えた非同期連携基盤（Event Bus）の検討.md)
* 運用監視基盤：[`AIエージェントの業務適用を見据えた運用監視基盤（Observability）の検討.md`](./AIエージェントの業務適用を見据えた運用監視基盤（Observability）の検討.md)
