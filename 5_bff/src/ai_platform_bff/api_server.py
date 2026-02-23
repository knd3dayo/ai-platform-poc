import secrets
from fastapi import Header, HTTPException, Depends
from typing import Optional
import secrets
import httpx
from fastapi import FastAPI, Request, Header, HTTPException, Depends
from typing import Optional

app = FastAPI(title="AI-Agent BFF Gateway")

# --- 共通ガードレール（依存関数） ---

async def agent_gatekeeper(
    authorization: Optional[str] = Header(None),
    traceparent: Optional[str] = Header(None)
):
    """
    全てのAPIエンドポイントの入り口で実行されるガードレール
    """
    # 1. 認証チェック（AuthN）
    if not authorization or not authorization.startswith("Bearer "):
        # 本来はここでIdPのログインURLへ誘導するレスポンスを検討
        raise HTTPException(status_code=401, detail="Please login via IdP to obtain a Bearer token")
    
    access_token = authorization.replace("Bearer ", "")

    # 2. トレース管理（Observability）
    if traceparent:
        parts = traceparent.split("-")
        if len(parts) == 4:
            tid = parts[1]
            full_tp = traceparent
        else:
            # 不正なフォーマットなら再生成
            tid = secrets.token_hex(16)
            full_tp = f"00-{tid}-{secrets.token_hex(8)}-01"
    else:
        # 新規生成
        tid = secrets.token_hex(16)
        full_tp = f"00-{tid}-{secrets.token_hex(8)}-01"

    # 後続に渡す情報をパッケージ化
    return {
        "access_token": access_token,
        "trace_id": tid,
        "traceparent": full_tp
    }

@app.post("/api/v1/workflow/finance")
async def run_finance_workflow(
    query: str,
    gate: dict = Depends(agent_gatekeeper) # ここで保護！
):
    # Dify用の固定APIキーを特定（BFFが秘匿管理）
    DIFY_KEY = "app-finance-master-key"

    payload = {
        "inputs": {
            "access_token": gate["access_token"], # ユーザー個人の権限
            "trace_id": gate["trace_id"]           # 運び屋変数
        },
        "query": query,
        "user": "unique_user_id",
        "response_mode": "blocking"
    }

    # Dify API実行...
    # return response

@app.post("/api/v1/agent/direct")
async def run_langgraph_agent(
    message: str,
    gate: dict = Depends(agent_gatekeeper) # 同じガードレールを適用！
):
    # LangGraphバックエンド（自作API）へのリクエスト
    # trace_id を thread_id に指定することで、ログと状態を完全に統合する
    langgraph_url = f"http://langgraph-api/chat"
    
    payload = {
        "message": message,
        "thread_id": gate["trace_id"], # ステート保持のキーとして使用
        "metadata": {
            "user_access_token": gate["access_token"] # MCPツール等で使用
        }
    }

    headers = {
        "traceparent": gate["traceparent"], # トレースの伝搬
        "Authorization": "Bearer internal-s2s-key"
    }

    # LangGraph API実行...
    # return response
