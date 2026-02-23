from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from ai_platform_app.test_langgraph_hitl import TestLangGraphHITL
# Pylance対策として MessagesState もインポートしておきます
from langgraph.graph import MessagesState 

# ==========================================
# FastAPI アプリケーションの実装
# ==========================================
app = FastAPI(title="LangGraph HITL API for Dify")

# 【重要】リクエストごとに状態が初期化されないよう、
# クラスのインスタンス化とグラフのコンパイルは関数の外側（グローバル）で1度だけ行います。
chat_poc = TestLangGraphHITL()
app_graph = chat_poc.create_app()

class ChatRequest(BaseModel):
    thread_id: str
    message: str

class ResumeRequest(BaseModel):
    thread_id: str
    action: str  # "approve" など

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    """Difyから最初のユーザー入力を受け取るエンドポイント"""
    # Pylance対策の型ヒントを復活させています
    config: RunnableConfig = {"configurable": {"thread_id": req.thread_id}}
    initial_input: MessagesState = {"messages": [HumanMessage(content=req.message)]}
    
    # グラフの実行（interrupt_beforeに引っかかると自動停止）
    for event in app_graph.stream(initial_input, config=config, stream_mode="values"):
        pass 

    # 停止した時点の状態を確認
    snapshot = app_graph.get_state(config)
    
    # 次のノードが 'tools'（承認待ち）かどうかでレスポンスを変える
    if snapshot.next and snapshot.next[0] == "tools":
        pending_action = snapshot.values["messages"][-1].tool_calls[0]
        return {
            "status": "requires_approval",
            "tool_name": pending_action["name"],
            "tool_args": pending_action["args"],
            "message": "処理を実行する前に承認が必要です。"
        }
    else:
        # 普通の会話（ツール不要）で終わった場合
        return {
            "status": "completed",
            "message": snapshot.values["messages"][-1].content
        }

@app.post("/api/resume")
async def resume_endpoint(req: ResumeRequest):
    """Difyでユーザーが承認した後に呼び出されるエンドポイント"""
    config: RunnableConfig = {"configurable": {"thread_id": req.thread_id}}
    
    # グローバルな app_graph から状態を取得
    snapshot = app_graph.get_state(config)
    
    if not snapshot.next or snapshot.next[0] != "tools":
        raise HTTPException(status_code=400, detail="承認待ちのタスクがありません。")

    if req.action == "approve":
        # 入力を None にして処理（ツール実行）を再開
        for event in app_graph.stream(None, config=config, stream_mode="values"):
            pass
            
    # 再開〜完了後の最終状態を取得
    snapshot = app_graph.get_state(config)
    return {
        "status": "completed",
        "message": snapshot.values["messages"][-1].content
    }

if __name__ == "__main__":
    import uvicorn
    import argparse
    # -p --port オプションを追加して、起動時にポート番号を指定できるようにします
    parser = argparse.ArgumentParser(description="Run the LangGraph HITL API server.")
    parser.add_argument("-p", "--port", type=int, default=5201, help="Port to run the API server on (default: 5201)")
    args = parser.parse_args()

    uvicorn.run(app, host="0.0.0.0", port=args.port)