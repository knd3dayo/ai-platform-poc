from typing import Dict, Any, Optional, List
from langchain_core.messages import SystemMessage
from langchain_core.messages import HumanMessage

from langgraph.graph import MessagesState
from ..core.utils import LLMUtils

class LangGraphNodes:

    @staticmethod
    async def planner_node(state: MessagesState):
        llm = LLMUtils.create_llm()
        planner_prompt = SystemMessage(content=(
            "あなたは実行計画作成者です。ユーザーの依頼を分析し、実行可能なサブタスクに分解してください。\n"
            "\n"
            "【重要】出力はJSONのみ。余計な説明/見出し/担当者割り当ては書かないでください。\n"
            "次の形式に厳密に従ってください: {\"tasks\": [\"...\", ...]}\n"
            "- tasks は最大6件\n"
            "- 各taskは1〜2文で具体的に（ツールで実行できる粒度）\n"
            "- タスク内でユーザーに質問したり、選択肢(1/2/3)や出力形式(CSV/表/JSON)の指定を求めない（必要なら自分で決めて進める）\n"
            "- なるべく『最終アウトプット』が返るタスクにする（例: 5件を表形式で列挙して一言評価まで完了）\n"
            "- 重要: このワークフローはタスクを並列実行する。タスク間で前段の出力が必要になる依存関係を作らない。依存が避けられない場合は分割せず1つのtaskに統合する\n"
            "- 各taskは単独で完結し、必要な入力（対象ファイル/ディレクトリ）と期待する出力形式まで含める\n"
            "- 実行環境メモ: executor コンテナの作業ディレクトリは /workspace。ファイル参照はホスト絶対パスではなく /workspace からの相対パス（例: /workspace/14-front/package.json）を使う\n"
            "- 『担当エージェント』や『タスクの割り振り』などは出力しない\n"
        ))
        # プランナーにはツールをバインドしない（思考に専念させる）
        response = await llm.ainvoke([planner_prompt] + state["messages"])
        return {"messages": [response]}

    @staticmethod
    async def supervisor_agent(state: MessagesState, tools: list):
        
        llm = LLMUtils.create_llm().bind_tools(tools=tools) 
        
        sys_prompt = SystemMessage(content=(
            "あなたは実行責任者です。承認された計画に基づき、直ちにツールを呼び出して実行してください。\n"
            "「了解しました」などの挨拶は不要です。まず最初のステップに必要なツールを呼び出してください。"
        ))
        
        response = await llm.ainvoke([sys_prompt] + state["messages"])
        return {"messages": [response]}


    @staticmethod
    async def planner_summarize_results(
        *,
        original_request: str,
        results: List[Dict[str, Any]],
        raw_summary: str,
    ):
        """並列実行の結果をPlanner視点で要約する（ツール呼び出し無し）。"""
        llm = LLMUtils.create_llm()
        sys_prompt = SystemMessage(content=(
            "あなたはPlanner（統合責任者）です。以下の実行結果を、ユーザー向けに日本語で簡潔にまとめてください。\n"
            "- 成果物（得られた情報）\n"
            "- 失敗したタスクと原因（分かる範囲）\n"
            "- 次にやるべきこと（最大3点）\n"
            "\n"
            "注意: 事実は結果からのみ述べ、推測は『推測』と明記してください。\n"
        ))

        # LLMへの入力は大きくなりやすいので、ここでは既に圧縮されたサマリ文字列を主に渡す。
        user_prompt = HumanMessage(content=(
            "[元の依頼]\n"
            f"{original_request}\n\n"
            "[実行結果サマリ]\n"
            f"{raw_summary}\n"
        ))
        return await llm.ainvoke([sys_prompt, user_prompt])

