import secrets
import httpx
import yaml
from fastapi import FastAPI, Request, Header, HTTPException, Depends
from typing import Optional

app = FastAPI(title="AI-Agent Configurable BFF")

# --- 設定読み込み ---
with open("config.yml", "r") as f:
    CONFIG = yaml.safe_load(f)
    BACKENDS = CONFIG.get("backends", {})

# --- 共通ガードレール（依存関数） ---
async def agent_gatekeeper(
    authorization: Optional[str] = Header(None),
    traceparent: Optional[str] = Header(None)
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Valid Bearer token required")
    
    access_token = authorization.replace("Bearer ", "")
    
    # トレースID生成/継承
    if traceparent and len(traceparent.split("-")) == 4:
        tid = traceparent.split("-")[1]
        full_tp = traceparent
    else:
        tid = secrets.token_hex(16)
        full_tp = f"00-{tid}-{secrets.token_hex(8)}-01"

    return {
        "access_token": access_token,
        "trace_id": tid,
        "traceparent": full_tp
    }

# --- 動的ルーティングエンドポイント ---

@app.post("/api/v1/execute/{backend_key}")
async def execute_agent(
    backend_key: str,
    query: str,
    gate: dict = Depends(agent_gatekeeper)
):
    # 1. config.yml からバックエンド設定を取得
    cfg = BACKENDS.get(backend_key)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Backend '{backend_key}' not found in config")

    backend_type = cfg.get("type")
    url = cfg.get("url")

    async with httpx.AsyncClient() as client:
        # 2. バックエンドの型に応じてペイロードを構築
        if backend_type == "dify":
            payload = {
                "inputs": {
                    "access_token": gate["access_token"],
                    "trace_id": gate["trace_id"]
                },
                "query": query,
                "user": "unique_user_id",
                "response_mode": "blocking"
            }
            headers = {
                "Authorization": f"Bearer {cfg.get('api_key')}",
                "traceparent": gate["traceparent"]
            }

        elif backend_type == "langgraph":
            payload = {
                "message": query,
                "thread_id": gate["trace_id"],
                "metadata": {
                    "user_access_token": gate["access_token"]
                }
            }
            headers = {
                "Authorization": f"Bearer {cfg.get('internal_key')}",
                "traceparent": gate["traceparent"]
            }
        
        else:
            raise HTTPException(status_code=500, detail="Unknown backend type")

        # 3. 実行
        try:
            response = await client.post(url, json=payload, headers=headers, timeout=60.0)
            response.raise_for_status()
            return {
                "backend": backend_key,
                "trace_id": gate["trace_id"],
                "data": response.json()
            }
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

# bff_server.py へ追記
@app.post("/api/v1/resume/{backend_key}")
async def resume_agent(
    backend_key: str,
    action: str, # "approve" or "cancel"
    trace_id: str, # 初回にBFFから返されたtrace_idを指定
    gate: dict = Depends(agent_gatekeeper)
):
    cfg = BACKENDS.get(backend_key)
    if not cfg or cfg.get("type") != "langgraph":
        raise HTTPException(status_code=400, detail="Invalid backend for resume")

    # LangGraph側の /api/resume を叩く
    # config.yml の url が .../api/chat なら、.../api/resume に変換
    resume_url = cfg.get("url").replace("/chat", "/resume")

    async with httpx.AsyncClient() as client:
        payload = {
            "thread_id": trace_id, # BFFのtrace_id = LangGraphのthread_id
            "action": action
        }
        headers = {
            "Authorization": f"Bearer {cfg.get('internal_key')}",
            "traceparent": gate["traceparent"]
        }
        
        response = await client.post(resume_url, json=payload, headers=headers)
        return response.json()

if __name__ == "__main__":
    import uvicorn
    import argparse
    # -p, --port オプションを追加
    parser = argparse.ArgumentParser(description="Run the AI-Agent Configurable BFF")
    parser.add_argument("-p", "--port", type=int, default=5401, help="Port to run the API server on")
    args = parser.parse_args()
    uvicorn.run(app, host="0.0.0.0", port=args.port)