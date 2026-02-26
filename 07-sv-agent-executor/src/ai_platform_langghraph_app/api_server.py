from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import requests
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import MessagesState

# 先ほど完成したクラスをインポート（パスは環境に合わせて適宜修正してください）
from ai_platform_langgraph_app.test_langgraph_hitl import LangGraphWorkflowTest1

app = FastAPI(title="Async Agent Webhook API")

# グローバルなエージェントインスタンスの作成
chat_poc = LangGraphWorkflowTest1()
app_graph = chat_poc.create_app()

# ==========================================
# データモデル
# ==========================================
class AsyncChatRequest(BaseModel):
    thread_id: str
    message: str
    webhook_url: str
    event_type: str = "agent_task_completed"
    metadata: Dict[str, Any] = {}

class AsyncResumeRequest(BaseModel):
    thread_id: str
    action: str  # "approve" など
    webhook_url: str
    event_type: str = "agent_resume_completed"
    metadata: Dict[str, Any] = {}

# ==========================================
# バックグラウンド処理ワーカー
# ==========================================
def background_agent_task(
    thread_id: str, 
    initial_input: Optional[MessagesState], 
    webhook_url: str, 
    event_type: str, 
    metadata: Dict[str, Any]
):
    """レスポンス返却後に裏側で実行される重い処理（チャット・再開共通）"""
    print(f"\n[Background Worker] スレッド {thread_id} の処理を開始します... (Event: {event_type})")
    
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

    try:
        # LangGraphの処理を実行（initial_inputがNoneの場合は中断箇所から再開）
        for event in app_graph.stream(initial_input, config=config, stream_mode="values"):
            pass 

        # 最終状態の取得
        snapshot = app_graph.get_state(config)
        
        # HITL（承認待ち）で止まった場合のハンドリング
        if snapshot.next and snapshot.next[0] == "tools":
            pending_action = snapshot.values["messages"][-1].tool_calls[0]
            status = "requires_approval"
            result_data = {
                "message": "処理を実行する前に人間の承認が必要です。",
                "tool_name": pending_action["name"],
                "tool_args": pending_action["args"]
            }
        else:
            status = "completed"
            result_data = {
                "message": snapshot.values["messages"][-1].content
            }

        # 統合Webhook向けの拡張Payload
        payload = {
            "event_type": event_type,
            "thread_id": thread_id,
            "status": status,
            "result": result_data,
            "metadata": metadata
        }
        
        print(f"[Background Worker] 処理完了。Webhookを送信します -> {webhook_url}")
        requests.post(webhook_url, json=payload, timeout=10)
        
    except Exception as e:
        print(f"[Background Worker] ❌ エラー発生: {e}")
        error_payload = {
            "event_type": f"{event_type}_failed",
            "thread_id": thread_id,
            "status": "failed",
            "error": str(e),
            "metadata": metadata
        }
        requests.post(webhook_url, json=error_payload, timeout=10)


# ==========================================
# エンドポイント
# ==========================================
@app.post("/api/chat_async")
async def chat_async_endpoint(req: AsyncChatRequest, background_tasks: BackgroundTasks):
    """ユーザーに即時応答し、裏で処理を開始する"""
    initial_input: MessagesState = {"messages": [HumanMessage(content=req.message)]}
    
    background_tasks.add_task(
        background_agent_task,
        req.thread_id,
        initial_input,
        req.webhook_url,
        req.event_type,
        req.metadata
    )

    return {
        "status": "processing",
        "thread_id": req.thread_id,
        "message": "バックグラウンドで処理を開始しました。"
    }

@app.post("/api/resume_async")
async def resume_async_endpoint(req: AsyncResumeRequest, background_tasks: BackgroundTasks):
    """ユーザーが承認した後、裏で処理を再開する"""
    config: RunnableConfig = {"configurable": {"thread_id": req.thread_id}}
    snapshot = app_graph.get_state(config)
    
    if not snapshot.next or snapshot.next[0] != "tools":
        raise HTTPException(status_code=400, detail="承認待ちのタスクがありません。")

    if req.action == "approve":
        background_tasks.add_task(
            background_agent_task,
            req.thread_id,
            None, # Noneを渡すことで中断箇所から再開
            req.webhook_url,
            req.event_type,
            req.metadata
        )

    return {
        "status": "processing",
        "thread_id": req.thread_id,
        "message": "バックグラウンドで処理を再開しました。"
    }

@app.get("/api/status/{thread_id}")
async def get_status_endpoint(thread_id: str):
    """現在の状態を確認する（ポーリング用）"""
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    snapshot = app_graph.get_state(config)
    
    if not snapshot.values:
        raise HTTPException(status_code=404, detail="指定されたスレッドが見つかりません。")
        
    return {
        "thread_id": thread_id,
        "latest_message": snapshot.values["messages"][-1].content
    }

if __name__ == "__main__":
    import uvicorn
    import argparse
    # -p --port オプションを追加して、起動時にポート番号を指定できるようにします
    parser = argparse.ArgumentParser(description="Async Agent Webhook API Server")
    parser.add_argument("-p", "--port", type=int, default=5202, help="Port to run the API server on (default: 5202)")
    args = parser.parse_args()
    uvicorn.run(app, host="0.0.0.0", port=args.port)
    