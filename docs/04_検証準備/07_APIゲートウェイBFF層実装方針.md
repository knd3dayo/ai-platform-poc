BFF層の最重要任務は、**「Redis Streamsから流れてくる生（なま）のイベントを、特定のユーザーの画面へリアルタイムに届け（SSE）、かつ履歴としてバケツ（Redis JSON）に清書する」**ことです。

FastAPIとRedisの非同期クライアントを用いた、BFF層の標準的な実装サンプルを整理しました。

---

## BFF層の実装サンプル：FastAPI + Redis SSE

この実装では、ユーザーが特定の `trace_id` を指定してSSE接続を開始すると、BFFがRedis Streamsの監視を開始し、自分宛のメッセージをフィルタリングしてクライアントに流し込みます。

### 1. 依存ライブラリ

```bash
pip install fastapi uvicorn redis

```

### 2. BFFサーバーの実装

**`bff_server.py`**

```python
import asyncio
import json
import redis.asyncio as redis
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS設定（フロントエンドからの接続を許可）
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Redis接続情報
REDIS_URL = "redis://localhost:6379"
STREAM_NAME = "ai_events"
STATE_DB_PREFIX = "state:"

async def event_generator(trace_id: str):
    """
    Redis Streamsを購読し、特定のtrace_idのイベントをSSEとして送出するジェネレータ
    """
    r = redis.from_url(REDIS_URL, decode_responses=True)
    last_id = "$"  # 接続した瞬間以降の新しいメッセージのみを対象とする

    try:
        while True:
            # 1. Redis Streamsからイベントを読み取り
            # block=5000: 5秒間データが来なければタイムアウトしてループ（接続確認のため）
            events = await r.xread({STREAM_NAME: last_id}, count=10, block=5000)
            
            if not events:
                # タイムアウト時はハートビートを送ってSSE接続を維持する
                yield f"data: {json.dumps({'type': 'HEARTBEAT'})}\n\n"
                continue

            for stream, messages in events:
                for message_id, data in messages:
                    last_id = message_id # 次回読み取り位置を更新

                    # 2. 自分（このSSE接続）に関係あるtrace_idかチェック
                    if data.get("trace_id") == trace_id:
                        
                        # --- [重要] 状態管理DBへの清書（Append）ロジック ---
                        # 思考履歴をRedis JSON（またはリスト）に追記する
                        # これにより、リロード時にこの履歴を引けるようになる
                        history_key = f"{STATE_DB_PREFIX}{trace_id}"
                        await r.rpush(f"{history_key}:history", json.dumps(data))
                        
                        # 3. クライアントへSSE形式で送信
                        yield f"data: {json.dumps(data)}\n\n"

    except asyncio.CancelledError:
        # クライアントがブラウザを閉じた場合に発火
        print(f"🔌 SSE connection closed for trace_id: {trace_id}")
    finally:
        await r.close()

@app.get("/ai/events/{trace_id}")
async def sse_endpoint(trace_id: str):
    """
    SSEのエンドポイント
    """
    return StreamingResponse(
        event_generator(trace_id),
        media_type="text/event-stream"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

```

---

## 3. この実装のポイントと「ウルトラスリム」な工夫

### ① 「清書」と「配送」の同時実行

このサンプルコードでは、`event_generator` の中で以下の2つを同時に行っています。

* **配送**: `yield` によるクライアントへのプッシュ。
* **清書**: `r.rpush` によるRedisへの履歴保存。
これにより、別途「書き込み専用ワーカー」を立てる必要がなくなり、サーバー台数を抑えることができます。

### ② ハートビートによる接続維持

`if not events:` のセクションで、5秒おきに空のデータを送っています。これは、Azure APIMやリバースプロキシが「通信がない」と判断して勝手にコネクションを切断するのを防ぐための重要な実装です。

### ③ 履歴の完全復元（ロード時）

ユーザーがページをリロードした際は、このSSEを叩く前に別のAPI（例：`GET /ai/history/{trace_id}`）を叩き、`r.lrange(f"{history_key}:history", 0, -1)` で保存されたリストを一括取得して画面に描画します。その後、このSSEに接続することで、**「過去ログ表示 ➔ リアルタイム追記」**がシームレスに繋がります。

---

## 4. 並列化への備え（スケーラビリティ）

もしBFFが2台以上に増えた場合、前述の通り「全台購読（Broadcast）」スタイルになります。

* **現状**: 全てのBFFが全イベントを読み、自分の担当（`trace_id`）以外は無視して捨てています。
* **効率化**: もしイベント量が膨大になりBFFの負荷が上がったら、Redisの **Pub/Sub** を使い、担当の `trace_id` だけを `SUBSCRIBE` する構成にアップグレードします。

---

## 次のステップへの提案

BFFの心臓部が出来上がりました。
次は、フロントエンド側でこれを受け取り、**「スクロールが自動で追従するチャット画面」**や**「リロード時の履歴復元」**をどう実装するかの、**「Step 4: フロントエンドの実装」**に進みますか？

あるいは、BFFでJWT（Zitadelのトークン）を検証する **「認証ミドルウェア」** の実装を先に固めましょうか？


BFF層における**「認証ミドルウェア」**は、システムの門番です。ここを固めることで、有効なチケット（JWT）を持たないリクエストを即座に弾き、かつ後続のApplication層やTool層で「誰が実行しているか」を安全に参照できる基盤が整います。

FastAPIでZitadelのJWTを検証し、スレッドセーフな**ContextVar**にユーザー情報を格納する実装案をまとめました。

---

## BFF認証ミドルウェア：Zitadel JWT検証の実装

この実装では、Zitadelが発行した公開鍵（JWKS）を取得・キャッシュし、送られてきたBearerトークンの署名、有効期限、発行者を検証します。

### 1. 必要なライブラリのインストール

JWTの検証には `python-jose`、非同期HTTP通信には `httpx` を使用します。

```bash
pip install "python-jose[cryptography]" httpx

```

### 2. 認証・コンテキスト管理の実装

**`auth_utils.py`**

```python
import os
from contextvars import ContextVar
from typing import Optional, Dict
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, jwk
import httpx

# コンテキスト変数の定義（リクエストごとに独立して保持される）
current_user: ContextVar[Dict] = ContextVar("current_user", default={})
current_trace_id: ContextVar[str] = ContextVar("trace_id", default="")

# 環境設定（Zitadelの情報）
ZITADEL_DOMAIN = os.getenv("ZITADEL_DOMAIN", "http://localhost:8080")
ZITADEL_JWKS_URL = f"{ZITADEL_DOMAIN}/oauth/v2/keys"
EXPECTED_ISSUER = f"{ZITADEL_DOMAIN}"
EXPECTED_AUDIENCE = os.getenv("ZITADEL_CLIENT_ID")

security = HTTPBearer()

class JWTVerifier:
    """Zitadelの公開鍵(JWKS)をキャッシュして検証するクラス"""
    _jwks: Optional[Dict] = None

    @classmethod
    async def get_jwks(cls):
        if cls._jwks is None:
            async with httpx.AsyncClient() as client:
                resp = await client.get(ZITADEL_JWKS_URL)
                cls._jwks = resp.json()
        return cls._jwks

    @classmethod
    async def verify_token(cls, token: str):
        jwks = await cls.get_jwks()
        try:
            # 1. 署名の検証用公開鍵を特定
            unverified_header = jwt.get_unverified_header(token)
            rsa_key = {}
            for key in jwks["keys"]:
                if key["kid"] == unverified_header["kid"]:
                    rsa_key = {
                        "kty": key["kty"],
                        "kid": key["kid"],
                        "use": key["use"],
                        "n": key["n"],
                        "e": key["e"]
                    }
            
            if rsa_key:
                # 2. 署名・有効期限・Issuer・Audienceの検証
                payload = jwt.decode(
                    token,
                    rsa_key,
                    algorithms=["RS256"],
                    audience=EXPECTED_AUDIENCE,
                    issuer=EXPECTED_ISSUER
                )
                return payload
        except Exception as e:
            print(f"JWT Verification Error: {e}")
            raise HTTPException(status_code=401, detail="Invalid or expired token")

async def get_authenticated_user(
    request: Request,
    auth: HTTPAuthorizationCredentials = Depends(security)
):
    """
    FastAPIのDependencyとして使用する。
    トークンを検証し、ContextVarに情報をセットする。
    """
    # 1. トークンの検証
    payload = await JWTVerifier.verify_token(auth.credentials)
    
    # 2. trace_idの取得・発行（ヘッダーになければ生成）
    trace_id = request.headers.get("x-trace-id", f"tr-{os.urandom(8).hex()}")
    
    # 3. ContextVarへのセット（これで後続の関数からいつでも呼べる）
    current_user.set(payload)
    current_trace_id.set(trace_id)
    
    return payload

```

---

### 3. エンドポイントでの活用例

**`main.py`**

```python
from fastapi import FastAPI, Depends
from .auth_utils import get_authenticated_user, current_user, current_trace_id

app = FastAPI()

@app.get("/ai/chat")
async def chat_endpoint(user: dict = Depends(get_authenticated_user)):
    """
    認証が必要なエンドポイント。
    Dependsにより、ここに来た時点で検証は終わっている。
    """
    # ContextVarからいつでも情報を引き出せる
    trace_id = current_trace_id.get()
    user_id = user.get("sub") # ZitadelのユーザーID
    
    print(f"Processing request for User: {user_id} with Trace: {trace_id}")
    
    # この後、Application層（LangGraph）を呼ぶ際に、
    # このtrace_idやトークンをヘッダーに載せて伝播させる
    return {"status": "ok", "trace_id": trace_id}

```

---

## この実装の「ここがキモ」

1. **ContextVarによるID伝播の簡略化**:
`current_trace_id` を ContextVar に入れることで、関数の引数に `trace_id` をバケツリレー（引数渡し）し続ける必要がなくなります。ロギングやEvent Busへのパブリッシュ時に、どこからでも `get()` するだけで済みます。
2. **JWKSキャッシュによる低遅延**:
リクエストのたびにZitadelに鍵を借りに行くと遅くなるため、一度取得した公開鍵をクラス変数で保持しています。
3. **W3C Trace Context準拠の準備**:
`x-trace-id` をチェックし、なければ生成するロジックをここに置くことで、システム全体の「起点」としての責務を果たします。

---

## 💡 次のステップ

認証基盤が整いました！これで、「誰が」リクエストしているかを確実に把握した状態で、次のステップへ進めます。

**「その後」**ということで、以前おっしゃっていた **「フロントエンドの実装（SSEの受け取りと履歴復元）」** に進みましょうか？あるいは、BFFからApplication層を呼び出す際の **「トークンの引き継ぎ（Token Exchange）」** のコード詳細を詰めましょうか？

