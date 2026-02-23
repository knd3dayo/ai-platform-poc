import os

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode
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

class LangGraphWorkflowTest1:
    thread_id: str
    message: str

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
        llm = LangGraphWorkflowTest1.create_llm()
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

