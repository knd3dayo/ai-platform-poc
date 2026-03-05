from fastapi import FastAPI
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from ..core.test_langgraph_hitl import LangGraphWorkflowTest1
# Pylance対策として MessagesState もインポートしておきます
from langgraph.graph import MessagesState 
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from contextlib import asynccontextmanager

# ==========================================
# FastAPI アプリケーションの実装
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- [Startup] アプリ起動時の処理 ---
    # 非同期チェックポインターを初期化
    # ※ aiosqlite を使うため、AsyncSqliteSaver を使用
    checkpointer = AsyncSqliteSaver.from_conn_string("langgraph_state.db")
    
    # 接続を開始 (context managerとして入る)
    async with checkpointer as saver:
        # グラフをコンパイル
        app_graph = chat_poc.create_graph().compile(
            checkpointer=saver,
            interrupt_before=["tools"]
        )
        # コンパイルしたグラフを app.state に保存（リクエスト間で共有可能）
        app.state.app_graph = app_graph
        
        print("🚀 LangGraph App with Async Checkpointer is ready")
        yield  # ここでアプリが稼働する
        
    # --- [Shutdown] アプリ終了時の処理 ---
    print("🛑 Shutting down...")

app = FastAPI(title="AI-Agent Async API", lifespan=lifespan)

# 【重要】リクエストごとに状態が初期化されないよう、
# クラスのインスタンス化とグラフのコンパイルは関数の外側（グローバル）で1度だけ行います。
chat_poc = LangGraphWorkflowTest1()

class ChatRequest(BaseModel):
    thread_id: str
    message: str

class ResumeRequest(BaseModel):
    thread_id: str
    action: str  # "approve" など

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    """最初のユーザー入力を受け取るエンドポイント"""
    # Pylance対策の型ヒントを復活させています
    config: RunnableConfig = {"configurable": {"thread_id": req.thread_id}}
    initial_input: MessagesState = {"messages": [HumanMessage(content=req.message)]}
    
    # グラフの実行（interrupt_beforeに引っかかると自動停止）
    async for event in app.state.app_graph.astream(initial_input, config=config, stream_mode="values"):
        pass 

    # 停止した時点の状態を確認
    snapshot = await app.state.app_graph.aget_state(config)
    
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
    """
    Dify/BFFから承認・却下を受けて、中断されたLangGraphを再開する
    """
    config: RunnableConfig = {"configurable": {"thread_id": req.thread_id}}
    
    # 状態の確認（念のため）
    state = await app.state.app_graph.aget_state(config)
    if not state.next:
        return {"status": "error", "message": "再開可能な待機状態ではありません。"}

    final_message = ""

    if req.action == "approve":
        # --- 承認時の処理 ---
        # None を渡すことで、中断ポイント（ツール実行直前）から再開
        # stream_mode="values" で最新のメッセージリストを追跡
        async for event in app.state.app_graph.astream(None, config=config, stream_mode="values"):
            if "messages" in event and len(event["messages"]) > 0:
                # 常に最新（最後）のメッセージを取得
                last_msg = event["messages"][-1]
                # AIによる最終回答テキストを取得
                final_message = last_msg.content

        return {
            "status": "success",
            "message": final_message or "処理が完了しました。"
        }

    else:
        # --- 却下時の処理 ---
        # 却下された場合は、グラフを強制的に終了状態へ持っていくか、
        # 却下された旨を履歴に追加するロジックをここに書く
        return {
            "status": "cancelled",
            "message": "ユーザーによって承認が却下されたため、処理を中断しました。"
        }
            
if __name__ == "__main__":
    import uvicorn
    import argparse
    # -p --port オプションを追加して、起動時にポート番号を指定できるようにします
    parser = argparse.ArgumentParser(description="Run the LangGraph HITL API server.")
    parser.add_argument("-p", "--port", type=int, default=5201, help="Port to run the API server on (default: 5201)")
    args = parser.parse_args()

    uvicorn.run(app, host="0.0.0.0", port=args.port)