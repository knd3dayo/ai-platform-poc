「4.3 Application層」の実装において、**Redis Streams**はAIエージェントの「実況中継（Thought）」と「外部からの制御（Cancel）」を司る、文字通りの神経系となります。

まずは基盤チームが行うべき**Redisの導入手順**と、アプリチームが実装する**LangGraphでのストリーム連携サンプル**を整理しました。

---

## 1. 【基盤チーム】Redisの導入手順 (Server 1)

ウルトラスリム構成の「サーバー1」に、Event Bus（Streams）と状態管理DB（JSON）を兼ねたRedisを構築します。

### 1-1. Docker Composeでの起動

Redis Stackを使用することで、Streamsに加えてJSON操作や可視化ツール（Redis Insight）を一度に導入できます。

**`1_infrastructure/docker-compose.yml`**

```yaml
services:
  redis:
    image: redis/redis-stack-server:latest
    ports:
      - "6379:6379"
    environment:
      - REDIS_ARGS=--requirepass yourpassword --maxmemory 2gb --maxmemory-policy allkeys-lru
    networks:
      - ai_platform_net
    volumes:
      - redis_data:/data

volumes:
  redis_data:

```

---

## 2. 【アプリチーム】Application層の実装 (Server 2)


## 1. 準備：ライブラリのインストール

非同期処理（asyncio）に対応した `redis-py` を使用します。

```bash
pip install redis

```

---

## 2. 【Producer】メッセージを投げる（Agent/App層相当）

`xadd` というコマンドを使います。これはストリームという「追記型の土管」にデータを放り込む操作です。

**`producer.py`**

```python
import asyncio
import json
import redis.asyncio as redis

async def run_producer():
    # Redisに接続
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    stream_name = "ai_events"

    print("🚀 Producer started. Sending events...")

    for i in range(5):
        # 送信するデータ（辞書形式）
        # headerとpayloadを分けておくと、後のBFFでの処理が楽になります
        event_data = {
            "trace_id": f"trace-id-{i}",
            "type": "AGENT_THOUGHT",
            "message": f"思考プロセス #{i}: 調査を実行中です..."
        }

        # XADD: ストリームにデータを追加
        # '*' は、RedisにメッセージID（タイムスタンプベース）を自動生成させる指定です
        event_id = await r.xadd(stream_name, event_data)
        
        print(f" [Sent] ID: {event_id} | Message: {event_data['message']}")
        await asyncio.sleep(1) # 1秒おきに送信

if __name__ == "__main__":
    asyncio.run(run_producer())

```

---

## 3. 【Consumer】メッセージを受け取る（BFF層相当）

`xread` というコマンドを使います。新しいデータが来るまで待機（ブロック）する設定が可能です。

**`consumer.py`**

```python
import asyncio
import redis.asyncio as redis

async def   ():
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    stream_name = "ai_events"
    
    # 最初は「最新のデータから読み取る」設定（"$"）
    last_id = "$" 

    print("👂 Consumer started. Waiting for events...")

    while True:
        # XREAD: ストリームからデータを読み取る
        # count=1: 1件ずつ処理
        # block=0: データが来るまで無限に待つ
        response = await r.xread({stream_name: last_id}, count=1, block=0)
        
        # responseは [[stream_name, [[message_id, data]]]] という複雑な構造
        for stream, messages in response:
            for message_id, data in messages:
                print(f" 📥 [Received] ID: {message_id}")
                print(f"    - Trace ID: {data['trace_id']}")
                print(f"    - Message: {data['message']}")
                
                # 次の読み取りのためにIDを更新
                last_id = message_id

if __name__ == "__main__":
    asyncio.run(run_consumer())

```

---

## 4. 動作確認の手順

1. **Redisを起動**: `docker run -d -p 6379:6379 redis` 等。
2. **Consumerを起動**: ターミナル1で `python consumer.py` を実行。待ち状態になります。
3. **Producerを実行**: ターミナル2で `python producer.py` を実行。
4. **結果**: Producerが送ったデータが、Consumer側の画面に即座に表示されます。

---

## 💡 ここが「Pub/Sub」と違うポイント

* **履歴が残る**: Consumerを止めた状態でProducerを実行し、後からConsumerを起動しても、`last_id = "0-0"` から読み始めれば、過去のメッセージをすべて取得できます。これが**「ブラウザ再読み込み時の履歴復元」**に役立ちます。
* **構造化データ**: 単なる「文字列」ではなく、フィールド（キー）を持った「レコード」としてデータを扱えます。
* **複数の購読者**: 1つのストリームを「SSEで画面に流すBFF」と「ログを分析する監視ツール」が同時にそれぞれのペースで読み取ることができます。

まずはこの仕組みで「データが非同期で流れる」感覚を掴んでおくと、後のBFF（SSE）の実装がスムーズになります。

次は、このConsumerの部分を拡張して、**「受け取ったデータをRedis JSON（状態管理DB）に書き込む」**ロジックを追加してみましょうか？

