import time
from typing import Any, Dict, Optional, List, Tuple, Deque
import json
import threading
import traceback
from collections import deque

from langchain_core.messages import AIMessage

from langgraph.graph import StateGraph, START, END, MessagesState
from langchain_core.messages import HumanMessage
from langgraph.graph import MessagesState

from ..model.models import ServerConfig, Job, jobs_lock, jobs
from ..core.utils import JobUtils, LLMUtils
from .agent import LangGraphNodes
from .tools import Tools, ToolNode

def _extract_tool_payloads_from_messages(messages: List[Any]) -> List[Dict[str, Any]]:
    """LangGraph の state.messages から tool 実行結果っぽいものを抽出する（PoC）。

    ToolNode の結果は ToolMessage として入ることが多い。
    - msg.type == "tool" かつ msg.content が JSON 文字列の場合は dict にデコードする。
    """
    payloads: List[Dict[str, Any]] = []
    for msg in messages:
        msg_type = getattr(msg, "type", None)
        if msg_type != "tool":
            continue
        content = getattr(msg, "content", None)
        if not isinstance(content, str):
            continue
        try:
            val = json.loads(content)
            if isinstance(val, dict):
                payloads.append(val)
        except Exception:
            continue
    return payloads


def _run_workflow_in_background(thread_id: str, message: str, input_zip_path: Optional[str]) -> None:
    """parallel_agent_workflow をバックグラウンドで実行し、jobs に途中経過/結果を格納する。"""

    with jobs_lock:
        jobs[thread_id] = Job(
            thread_id=thread_id,
            status="running",
            progress={
                "started_at": time.time(),
                "latest_message": None,
                "last_tool": None,
                "stdout": None,
                "stderr": None,
                "server_logs": deque(maxlen=200),
            },
        )

    try:

        wf = ParallelAgentWorkflow()
        graph = wf.create_graph().compile()
        server_config = ServerConfig.load_from_env()

        # parallel_agent_workflow 側のデフォルト分岐と合わせる
        llm_base_url = server_config.llm_base_url 
        executor_base_url = server_config.executor_base_url

        # ユーザーがZIPを渡してきた場合は、Supervisor がツール呼び出しで使えるようパスを明示する。
        # run_autonomous_agent_executor_zip は zip_path を受け取れるので、実ファイルパスを案内すれば良い。
        user_message = message
        if input_zip_path:
            user_message += (
                "\n\n[入力ZIP]\n"
                "ユーザーがZIPファイルをアップロードしました。必要なら `run_autonomous_agent_executor_zip` を使い、"
                "次の zip_path を指定して処理してください。\n"
                f"zip_path: {input_zip_path}\n"
            )

        state: MessagesState = {"messages": [HumanMessage(content=user_message)]}

        with jobs_lock:
            job = jobs.get(thread_id)
            if job:
                JobUtils.append_server_log(job, "LangGraph stream started")
                JobUtils.append_server_log(job, f"llm_base_url={llm_base_url}")
                JobUtils.append_server_log(job, f"executor_base_url={executor_base_url}")
                job.progress["llm_base_url"] = llm_base_url
                job.progress["executor_base_url"] = executor_base_url

        for event in graph.stream(state, stream_mode="values"):
            # event は state(values) の dict を想定
            messages = event.get("messages") if isinstance(event, dict) else None
            if not isinstance(messages, list) or not messages:
                continue

            latest = messages[-1]
            latest_content = getattr(latest, "content", None)

            # 進捗更新
            with jobs_lock:
                job = jobs.get(thread_id)
                if job:
                    if JobUtils.get_cancel_flag(job):
                        JobUtils.append_server_log(job, "Cancel requested. Stopping stream loop.")
                        job.status = "cancelled"
                        break
                    job.progress["latest_message"] = latest_content

                    tool_payloads = _extract_tool_payloads_from_messages(messages)
                    if tool_payloads:
                        last_tool = tool_payloads[-1]
                        job.progress["last_tool"] = last_tool
                        JobUtils.append_server_log(job, f"tool_result received keys={list(last_tool.keys())}")
                        # stdout/stderr があれば status ポーリングで返せるようにコピー
                        if "stdout" in last_tool:
                            job.progress["stdout"] = last_tool.get("stdout")
                        if "stderr" in last_tool:
                            job.progress["stderr"] = last_tool.get("stderr")

                        # cancel が要求されていたら executor 側にも kill を試みる
                        if JobUtils.get_cancel_flag(job):
                            JobUtils.try_cancel_executor_task(job)

        # 最終 state を取得（stream で最後に来た event を使っても良いが、ここでは progress を採用）
        with jobs_lock:
            job = jobs.get(thread_id)
            if job:
                if JobUtils.get_cancel_flag(job):
                    JobUtils.append_server_log(job, "LangGraph stream finished (cancelled)")
                else:
                    JobUtils.append_server_log(job, "LangGraph stream finished")
            jobs[thread_id] = Job(
                thread_id=thread_id,
                status="cancelled" if (job and JobUtils.get_cancel_flag(job)) else "completed",
                progress=job.progress if job else {"latest_message": None},
                result={
                    "thread_id": thread_id,
                    "latest_message": job.progress.get("latest_message") if job else None,
                    "last_tool": job.progress.get("last_tool") if job else None,
                },
            )

    except Exception as e:
        with jobs_lock:
            job = jobs.get(thread_id)
            if job:
                JobUtils.append_server_log(job, f"ERROR: {repr(e)}")
                JobUtils.append_server_log(job, traceback.format_exc())
            jobs[thread_id] = Job(
                thread_id=thread_id,
                status="failed",
                progress=job.progress if job else {},
                error=repr(e),
            )
    finally:
        # 入力ZIPはPoCのため、そのまま残す（必要なら削除に変更可能）
        pass


def start_background_thread(thread_id: str, message: str, input_zip_path: Optional[str]) -> None:
    t = threading.Thread(target=_run_workflow_in_background, args=(thread_id, message, input_zip_path), daemon=True)
    t.start()

# ==========================================
# 2. Supervisor（LLM）の設定
# ==========================================

# ... 既存のインポート ...

class ParallelAgentWorkflow:
    @staticmethod
    def should_continue(state: MessagesState):
        """次の遷移先を決定するルーティング関数"""
        last_message = state["messages"][-1]
        if isinstance(last_message, AIMessage) and last_message.tool_calls:        
            return "tools" # ツール呼び出しがあればtoolsノードへ
        return END         # なければ会話終了


    def create_graph(self, include_planner: bool = False, tools: Optional[list] = None) -> StateGraph:
        workflow = StateGraph(MessagesState)

        # IMPORTANT: LLM側にバインドするツールと、ToolNode側で実行可能なツールは必ず一致させる。
        # ここがズレると、LLMが存在しないツール名（例: run_executor_local）を呼び出して失敗する。
        effective_tools = Tools.tools if tools is None else tools

        async def create_agent_node(state: MessagesState):
            return await LangGraphNodes.supervisor_agent(state, tools=effective_tools)
        workflow.add_node("agent", create_agent_node)
        workflow.add_node("tools", ToolNode(effective_tools))

        if include_planner:
            workflow.add_node("planner", LangGraphNodes.planner_node)
            workflow.add_edge(START, "planner")
            workflow.add_edge("planner", "agent")
        else:
            workflow.add_edge(START, "agent")

        workflow.add_conditional_edges("agent", self.should_continue)
        workflow.add_edge("tools", "agent")

        return workflow
            
