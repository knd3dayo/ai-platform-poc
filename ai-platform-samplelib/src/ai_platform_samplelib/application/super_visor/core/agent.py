from langchain_core.tools import tool
from langchain_core.messages import AIMessage, SystemMessage

from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.graph import MessagesState

from ..core.utils import LLMUtils
from .tools import Tools
class LangGraphNodes:

    @staticmethod
    async def planner_node(state: MessagesState):
        llm = LLMUtils.create_llm()
        planner_prompt = SystemMessage(content=(
            "あなたはシニアエンジニアです。ユーザーの依頼を分析し、タスクリストを作成してください。\n"
            "タスクは具体的かつ実行可能なステップに分解してください。必要に応じて、タスクの順序や優先順位も考慮してください。\n"
            "タスクリストを作成後、そのタスクの実行を適切な配下のエージェントに割り振ってください。タスクの割り振りは、タスクの内容や必要なスキルセットに基づいて行ってください。\n"
            # "最後は必ず『この計画で実行を開始してよろしいですか？』で終わってください。"
        ))
        # プランナーにはツールをバインドしない（思考に専念させる）
        response = await llm.ainvoke([planner_prompt] + state["messages"])
        return {"messages": [response]}

    @staticmethod
    async def supervisor_agent(state: MessagesState):
        
        llm = LLMUtils.create_llm().bind_tools(tools=Tools.tools) 
        
        sys_prompt = SystemMessage(content=(
            "あなたは実行責任者です。承認された計画に基づき、直ちにツールを呼び出して実行してください。\n"
            "「了解しました」などの挨拶は不要です。まず最初のステップに必要なツールを呼び出してください。"
        ))
        
        response = await llm.ainvoke([sys_prompt] + state["messages"])
        return {"messages": [response]}

