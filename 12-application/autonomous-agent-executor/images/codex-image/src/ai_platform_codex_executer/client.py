from typing import TypedDict, List, Optional

class GraphState(TypedDict):
    code: str
    result: Optional[str]
    error: Optional[str]
    retry_count: int
    max_retries: int

import time
import requests

def execute_code_node(state: GraphState):
    print(f"--- 実行中 (試行 {state['retry_count'] + 1}) ---")
    code = state["code"]
    
    # 1. 実行リクエスト
    res = requests.post("http://executor-service:8000/execute", json={"code": code})
    task_id = res.json()["task_id"]
    
    # 2. ポリング（完了を待つ）
    while True:
        status_res = requests.get(f"http://executor-service:8000/status/{task_id}").json()
        if status_res["status"] in ["completed", "failed", "timeout", "cancelled"]:
            break
        time.sleep(1) # 1秒待機
    
    # 3. 結果の判定
    if status_res["status"] == "completed":
        return {"result": status_res["stdout"], "error": None}
    else:
        # エラー（stderr）を記録
        return {"error": status_res["stderr"] or "Unknown error", "result": None}


def decide_next_step(state: GraphState):
    # エラーがなければ終了
    if state["error"] is None:
        return "end"
    
    # リトライ回数上限に達したら諦める
    if state["retry_count"] >= state["max_retries"]:
        print("--- リトライ上限到達 ---")
        return "end"
    
    # エラーがあれば「修正ノード」へ
    return "correct"

def correction_node(state: GraphState):
    print("--- エラーを修正中 ---")
    # ここで LLM を呼び出し、state['code'] と state['error'] を渡して
    # 「修正したコード」を生成させます
    # new_code = llm.invoke(...)
    
    return {
        "code": "修正されたコード", 
        "retry_count": state["retry_count"] + 1,
        "error": None
    }

from langgraph.graph import StateGraph, END

workflow = StateGraph(GraphState)

# ノードの追加
workflow.add_node("execute", execute_code_node)
workflow.add_node("correct", correction_node)

# エントリポイント
workflow.set_entry_point("execute")

# 条件付きエッジ（自己修復ループ）
workflow.add_conditional_edges(
    "execute",
    decide_next_step,
    {
        "correct": "correct",
        "end": END
    }
)

# 修正後は再度実行へ
workflow.add_edge("correct", "execute")

app = workflow.compile()