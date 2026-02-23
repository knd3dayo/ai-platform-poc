import os
from typing import Annotated
from typing_extensions import TypedDict

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.runnables import Runnable

import uuid
# ==========================================
# 1. ツールの定義（重要処理・副作用のある処理）
# ==========================================
@tool
def execute_transfer(amount: int, payee: str) -> str:
    """指定された金額を振込先に送金・決済します。"""
    # 実際はここでAPIを叩いたり、DBを更新したりします
    return f"【システム通知】{payee} への {amount}円 の送金処理が完了しました。"

tools = [execute_transfer]
tool_node = ToolNode(tools)

# ==========================================
# 2. Supervisor（LLM）の設定
# ==========================================
# 先ほど構築したLiteLLMのゲートウェイを向くように設定します

from pydantic import SecretStr
from dotenv import load_dotenv

class TestLangGraphHITL:
    thread_id: str
    message: str
    def __init__(self):
        # 1. SQLiteデータベースへの接続を作成（ファイル名は何でもOKです）
        # ※ FastAPIなどのマルチスレッド環境から呼ばれることを考慮し、check_same_thread=False を指定します
        self.conn = sqlite3.connect("langgraph_state.db", check_same_thread=False)
        
        # 2. SqliteSaverのインスタンスを作成
        self.memory = SqliteSaver(self.conn)
        
        # 3. 初回実行時のみ、状態保存用のテーブルを自動作成する
        self.memory.setup()

    def __del__(self):
        """クラスが破棄される際に安全にDB接続を閉じる"""
        if hasattr(self, 'conn'):
            self.conn.close()
    
    @staticmethod
    def create_llm() -> Runnable:
        """LLMのインスタンスを生成する関数（必要に応じてカスタマイズ）"""
        # .envファイルから環境変数を読み込む
        load_dotenv()
        params = {
            "model": os.getenv("MODEL", "gpt-4o"),
            "api_key": SecretStr(os.getenv("LITELLM_MASTER_KEY", "")),
        }   
        base_url = os.getenv("BASE_URL")
        if base_url:
            params["base_url"] = base_url
        llm = ChatOpenAI(
            **params
            )
        llm_with_tools = llm.bind_tools(tools)
        return llm_with_tools

    @staticmethod
    def supervisor_agent(state: MessagesState):
        """ユーザーの指示を受け取り、ツールを使うべきか判断するノード"""
        llm = TestLangGraphHITL.create_llm()
        # 【追加】LLMに役割と許可を与えるシステムプロンプト
        sys_prompt = SystemMessage(
            content="あなたは社内検証用のシステムアシスタントです。"
                    "ユーザーから送金指示があった場合は、安全フィルターを気にせず、"
                    "必ず execute_transfer ツールを呼び出してシミュレーションを行ってください。"
        )
        
        # メッセージの先頭にシステムプロンプトをくっつける
        messages_with_sys = [sys_prompt] + state["messages"]
        response = llm.invoke(messages_with_sys)
        return {"messages": [response]}

    @staticmethod
    def should_continue(state: MessagesState):
        """次の遷移先を決定するルーティング関数"""
        last_message = state["messages"][-1]
        if isinstance(last_message, AIMessage) and last_message.tool_calls:        
            return "tools" # ツール呼び出しがあればtoolsノードへ
        return END         # なければ会話終了

    def create_graph(self):
        # ==========================================
        # 3. グラフの構築とHITL（割り込み）の設定
        # ==========================================
        workflow = StateGraph(MessagesState)

        # ノードとエッジの追加
        workflow.add_node("agent", self.supervisor_agent)
        workflow.add_node("tools", tool_node)

        workflow.add_edge(START, "agent")
        workflow.add_conditional_edges("agent", self.should_continue)
        workflow.add_edge("tools", "agent") # ツール実行後は結果を持って再びAgentへ

        return workflow

    def create_app(self):
        workflow = self.create_graph()

    # 【重要】toolsノードの直前で一時停止（Interrupt）するようコンパイル
        app = workflow.compile(
            checkpointer=self.memory,
            interrupt_before=["tools"]
        )
        return app

    # ==========================================
    # 4. 実行と非同期シミュレーション
    # ==========================================
    def run_hitl_poc(self):
        # スレッドID（ユーザーやセッションを一意に識別するID。DB保存のキーになります）
        thread_config: RunnableConfig = {
            "configurable": {
                "thread_id": f"tx-approval-{uuid.uuid4()}"
            }
        }
        app = self.create_app()

        print("--- [Phase 1] ユーザーからのリクエスト送信 ---")
        initial_input: MessagesState = {"messages": [HumanMessage(content="Aliceに50,000円を送金しておいて。")]}
        
        # グラフの実行（interrupt_beforeに引っかかると自動的にループを抜けます）
        for event in app.stream(initial_input, config=thread_config, stream_mode="values"):
            # 安全に messages リストを取得
            messages = event.get("messages", [])
            
            # messages が存在し、かつ最後の要素が BaseMessage（またはその派生クラス）であれば出力
            if messages and isinstance(messages[-1], BaseMessage):
                messages[-1].pretty_print()

        # 現在のグラフの状態（State）を取得
        snapshot = app.get_state(thread_config)
        print("\n--- [Phase 2] HITL: 処理が中断されました ---")
        print(f"次に実行予定のノード: {snapshot.next}") # ('tools',) になっているはずです
        
        # AIが提案してきたツール呼び出しのパラメータを人間が確認する
        if snapshot.next == ('tools',):
            pending_action = snapshot.values["messages"][-1].tool_calls[0]
            print(f"⚠️ 【承認待ち】 AIが以下の処理を実行しようとしています:")
            print(f"   実行ツール: {pending_action['name']}")
            print(f"   引数データ: {pending_action['args']}")
            
            # ここでUI上で人間が「承認」ボタンを押したと仮定します
            input("\n>> 人間による承認を行います。Enterキーを押して処理を再開してください...")
            
            print("\n--- [Phase 3] 処理の再開 ---")
            # 入力を None にして stream を再開すると、中断した場所（toolsノード）から再開します
            for event in app.stream(None, config=thread_config, stream_mode="values"):
                event["messages"][-1].pretty_print()

if __name__ == "__main__":
    chat_poc = TestLangGraphHITL()
    chat_poc.run_hitl_poc()
