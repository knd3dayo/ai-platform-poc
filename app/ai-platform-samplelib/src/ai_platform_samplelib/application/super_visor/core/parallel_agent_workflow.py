import time
from typing import Any, Dict, Optional, List, Tuple, Deque, TypedDict, Annotated
import operator
import json
import threading
import traceback
import pathlib
import re
import os
from collections import deque
import zipfile

from langchain_core.messages import AIMessage
from langchain_core.messages import HumanMessage

from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.graph import MessagesState
from langgraph.graph.message import add_messages
from langgraph.types import Send

from ..model.models import ServerConfig, Job, jobs_lock, jobs
from ..core.utils import JobUtils, LLMUtils
from .agent import LangGraphNodes
from .tools import Tools, ToolNode
from .agent import run_executor_local


class ParallelExecutionState(TypedDict, total=False):
    # Keep LangGraph message semantics
    messages: Annotated[list, add_messages]

    # Optional execution context
    source_dir: Optional[pathlib.Path]
    source_dirs: Optional[list[pathlib.Path]]
    zip_path: Optional[str]

    # Parallel task execution
    tasks: list[str]
    task_queue: list[str]
    current_batch: list[str]
    task: str
    results: Annotated[list[Dict[str, Any]], operator.add]
    raw_summary: str


def _extract_tasks_from_plan_text(plan_text: str, *, max_tasks: int = 50) -> list[str]:
    """Planner出力(Markdown/JSON/自然文)からサブタスク文字列を抽出する（PoC）。

    目的:
    - 章見出し/担当割り振り/補足説明などを「サブタスク」と誤認して大量実行しない
    - JSON({"tasks": [...]}) が来た場合はそれを最優先で使う
    """
    text = (plan_text or "").strip()
    if not text:
        return []

    def _clean_task(s: str) -> str:
        s = (s or "").strip()
        if not s:
            return ""
        # 全体が **...** / `...` の場合は剥がす
        m_bold = re.fullmatch(r"\*\*(.+)\*\*", s)
        if m_bold:
            s = m_bold.group(1).strip()
        m_code = re.fullmatch(r"`(.+)`", s)
        if m_code:
            s = m_code.group(1).strip()
        # 末尾の句読点/コロンを軽く正規化
        s = s.rstrip("：:")
        return s

    def _is_meta_task(s: str) -> bool:
        if not s:
            return True
        if s.startswith("担当エージェント"):
            return True
        if "タスクの割り振り" in s or "タスク割り振り" in s:
            return True
        return False

    def _dedupe_keep_order(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            key = item.strip()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    # 1) JSON を最優先
    for candidate in (text,):
        try:
            if candidate.lstrip().startswith("{"):
                obj = json.loads(candidate)
                if isinstance(obj, dict) and isinstance(obj.get("tasks"), list):
                    raw_tasks = [t for t in (obj.get("tasks") or []) if isinstance(t, str)]
                    cleaned = [_clean_task(t) for t in raw_tasks]
                    cleaned = [t for t in cleaned if t and not _is_meta_task(t)]
                    cleaned = _dedupe_keep_order(cleaned)
                    return cleaned[:max_tasks]
        except Exception:
            pass

    # JSONが文章中に埋まっているケース（最初の { 〜 最後の } を雑に試す）
    try:
        start = text.find("{")
        end = text.rfind("}")
        if 0 <= start < end:
            obj = json.loads(text[start : end + 1])
            if isinstance(obj, dict) and isinstance(obj.get("tasks"), list):
                raw_tasks = [t for t in (obj.get("tasks") or []) if isinstance(t, str)]
                cleaned = [_clean_task(t) for t in raw_tasks]
                cleaned = [t for t in cleaned if t and not _is_meta_task(t)]
                cleaned = _dedupe_keep_order(cleaned)
                return cleaned[:max_tasks]
    except Exception:
        pass

    # 2) Markdown/自然文: 「タスクリスト」セクションのトップレベル項目だけ拾う
    start_markers = ("タスクリスト", "タスク一覧", "task list", "tasks")
    stop_markers = ("タスクの割り振り", "タスク割り振り", "割り振り", "担当エージェント")

    def _extract_top_level_items(lines: list[str], *, require_tasks_section: bool) -> list[str]:
        in_tasks_section = not require_tasks_section
        collected: list[str] = []

        for raw_line in lines:
            stripped = raw_line.strip()
            if not stripped:
                continue

            normalized = stripped.lstrip("#").strip()
            if not in_tasks_section and any(m in normalized.lower() for m in start_markers):
                in_tasks_section = True
                continue
            if in_tasks_section and any(m in normalized for m in stop_markers):
                break
            if not in_tasks_section:
                continue

            # ネストした箇条書き（インデントあり）は爆発しやすいので捨てる
            leading_spaces = len(raw_line) - len(raw_line.lstrip(" "))
            if leading_spaces >= 2:
                continue

            m_num = re.match(r"^\s*\d+[\.|\)]\s+(.+)$", raw_line)
            if m_num:
                task = _clean_task(m_num.group(1))
                if task and not _is_meta_task(task):
                    collected.append(task)
            else:
                m_bullet = re.match(r"^\s*[-\*]\s+(.+)$", raw_line)
                if m_bullet:
                    task = _clean_task(m_bullet.group(1))
                    if task and not _is_meta_task(task):
                        collected.append(task)

            if len(collected) >= max_tasks:
                break

        return collected

    lines = text.splitlines()
    tasks = _extract_top_level_items(lines, require_tasks_section=True)
    if not tasks:
        # タスクリストの見出しが無い場合に備えて、全体からトップレベル箇条書きだけ拾う
        tasks = _extract_top_level_items(lines, require_tasks_section=False)

    tasks = _dedupe_keep_order(tasks)
    if tasks:
        return tasks[:max_tasks]

    # 3) 最後の手段: 全体を1タスクとして扱う
    return [text]

# ==========================================
# 3. ロジック本体
# ==========================================
import typer
# ... 他のインポート ...
local_tools = [run_executor_local]
local_tool_node = ToolNode(local_tools)


def _safe_extract_zip(zip_path: str, dest_dir: pathlib.Path) -> pathlib.Path:
    """ZIP を dest_dir に安全に展開して、展開先ディレクトリを返す。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    base = dest_dir.resolve()

    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            # ディレクトリはスキップ（ZipFile.extract でも作られるが明示）
            if member.is_dir():
                continue

            # ZipSlip 対策: 展開後パスが base 配下に収まることを保証する
            target = (dest_dir / member.filename).resolve()
            if not str(target).startswith(str(base) + os.sep) and target != base:
                raise ValueError(f"Unsafe zip entry path: {member.filename}")

        zf.extractall(dest_dir)

    return dest_dir

async def run_integrated_agent_core(
    message: str, source_paths: Optional[list[pathlib.Path]], auto_approve: bool, tools: list = local_tools
        ):
    typer.secho("🤖 統合エージェント（Planning Mode）を起動中...", fg=typer.colors.MAGENTA, bold=True)
    
    wf = ParallelAgentWorkflow()
    # プランナーを有効化 + 4並列ワーカーで実行
    graph = wf.create_parallel_graph(include_planner=True, tools=tools, max_parallel=4).compile()

    normalized_sources: list[pathlib.Path] = []
    for p in (source_paths or []):
        if isinstance(p, pathlib.Path):
            normalized_sources.append(p)

    user_input = message
    if len(normalized_sources) == 1:
        source_path = normalized_sources[0]
        user_input += (
            f"\n\n[Context] 作業ディレクトリ(ホスト): {source_path.resolve()}"
            "\n[Context] executor コンテナ内の作業ディレクトリ: /workspace"
            "\n[Context] タスクでは /workspace からのパスで参照してください。"
        )
    elif len(normalized_sources) >= 2:
        listed = "\n".join([f"- {p.resolve()}" for p in normalized_sources])
        user_input += (
            "\n\n[Context] 取り込み対象(ホスト)が複数指定されています:"
            f"\n{listed}"
            "\n[Context] executor コンテナ内では /workspace/inputs/<name>/... に配置されます。"
            "\n[Context] タスクでは /workspace からのパスで参照してください。"
        )

    initial_input: ParallelExecutionState = {
        "messages": [HumanMessage(content=user_input)],
    }
    if len(normalized_sources) == 1:
        initial_input["source_dir"] = normalized_sources[0]
    elif len(normalized_sources) >= 2:
        initial_input["source_dirs"] = normalized_sources

    # stream_mode="updates" でノードごとの出力をハンドリング
    async for event in graph.astream(initial_input, stream_mode="updates"):
        # プランナーによる計画策定フェーズ
        # NOTE: event 全体を print するとメタ情報が大量に出るので、デバッグ時のみ有効化。
        if os.getenv("AI_PLATFORM_DEBUG_EVENTS") == "1":
            print(event)
        if "planner" in event:
            latest_msg = event["planner"]["messages"][-1]
            typer.secho("\n📋 --- 提案された実行計画 ---", fg=typer.colors.YELLOW, bold=True)
            typer.echo(latest_msg.content)
            
            # 承認確認（--yes オプションがない場合）
            if not auto_approve:
                if not typer.confirm("\n上記計画で実行を開始しますか？"):
                    typer.secho("🚫 実行はキャンセルされました。", fg=typer.colors.RED, bold=True)
                    return # 処理を中断

        # 並列ワーカーの進捗
        if "worker" in event:
            # worker は results への追記だけを行う想定
            payload = event.get("worker")
            if isinstance(payload, dict):
                results = payload.get("results")
                if isinstance(results, list) and results:
                    item = results[-1] if isinstance(results[-1], dict) else None
                    if item:
                        task = item.get("task")
                        elapsed = item.get("elapsed_sec")
                        typer.secho(f"\n🧩 worker finished task={task!s} elapsed={elapsed!s}s", fg=typer.colors.CYAN)
                    else:
                        typer.secho("\n🧩 worker finished", fg=typer.colors.CYAN)
                else:
                    typer.secho("\n🧩 worker finished", fg=typer.colors.CYAN)

        # 結果統合
        # NOTE: 並列版は join→planner_summarize の2段。
        # join は raw_summary を作るだけで messages を返さない。
        if "planner_summarize" in event:
            latest_msg = event["planner_summarize"]["messages"][-1]
            if latest_msg.content:
                typer.secho("\n🏁 最終報告:", fg=typer.colors.GREEN, bold=True)
                typer.echo(latest_msg.content)

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
        # API 経路も「Python内完結（ローカルツール優先）」をデフォルトとする
        graph = wf.create_graph(tools=local_tools).compile()
        server_config = ServerConfig.load_from_env()

        # parallel_agent_workflow 側のデフォルト分岐と合わせる
        llm_base_url = server_config.llm_base_url 
        executor_base_url = server_config.executor_base_url

        # ユーザーがZIPを渡してきた場合は、一時ディレクトリへ展開して source_dir として案内する。
        user_message = message
        if input_zip_path:
            tmp_dir = pathlib.Path(input_zip_path).parent
            extracted_dir = _safe_extract_zip(input_zip_path, tmp_dir / "unzipped")
            user_message += (
                "\n\n[入力ソース]\n"
                "ユーザーがZIPファイルをアップロードしました。内容はサーバ側で展開済みです。\n"
                "次の方針で `run_executor_local` を呼び出してください。\n"
                f"- source_dir: {extracted_dir.as_posix()}\n"
                "- executor コンテナ内の作業ディレクトリは /workspace（ファイル参照は /workspace から）\n"
            )

        state: MessagesState = {"messages": [HumanMessage(content=user_message)]}

        with jobs_lock:
            job = jobs.get(thread_id)
            if job:
                JobUtils.append_server_log(job, "LangGraph stream started")
                JobUtils.append_server_log(job, f"llm_base_url={llm_base_url}")
                JobUtils.append_server_log(job, "execution_mode=local")
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
        effective_tools = local_tools if tools is None else tools

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


    def create_parallel_graph(
        self,
        *,
        include_planner: bool = True,
        include_planner_summary: bool = True,
        tools: Optional[list] = None,
        max_parallel: int = 4,
    ) -> StateGraph:
        """計画をサブタスクに分割し、最大 max_parallel 件を並列実行して統合するPoCグラフ。"""
        if max_parallel < 1:
            raise ValueError("max_parallel must be >= 1")

        effective_tools = local_tools if tools is None else tools
        tools_by_name = {getattr(t, "name", str(i)): t for i, t in enumerate(effective_tools)}

        async def plan_to_tasks(state: ParallelExecutionState) -> Dict[str, Any]:
            # planner が有効な場合は最後のメッセージ（planner出力）から抽出
            msgs = state.get("messages") or []
            text = ""
            if include_planner and msgs:
                text = getattr(msgs[-1], "content", "") or ""
            elif msgs:
                text = getattr(msgs[0], "content", "") or ""

            tasks = _extract_tasks_from_plan_text(text)
            return {
                "tasks": tasks,
                "task_queue": tasks,
                "current_batch": [],
                "results": [],
            }

        async def dispatch(state: ParallelExecutionState) -> Dict[str, Any]:
            queue = list(state.get("task_queue") or [])
            batch = queue[:max_parallel]
            rest = queue[max_parallel:]
            return {"current_batch": batch, "task_queue": rest}

        def route_after_dispatch(state: ParallelExecutionState):
            batch = state.get("current_batch") or []
            if not batch:
                return "join"
            # NOTE:
            # Send() の payload は worker 側 state として渡されるため、
            # 共有コンテキスト（source_dir/zip_path）が欠落すると executor が /workspace を準備できない。
            shared: Dict[str, Any] = {}
            if state.get("source_dir") is not None:
                shared["source_dir"] = state.get("source_dir")
            if state.get("source_dirs") is not None:
                shared["source_dirs"] = state.get("source_dirs")
            if state.get("zip_path") is not None:
                shared["zip_path"] = state.get("zip_path")

            return [Send("worker", {**shared, "task": t}) for t in batch]

        async def worker(state: ParallelExecutionState) -> Dict[str, Any]:
            task = (state.get("task") or "").strip()
            msgs = state.get("messages") or []
            original_request = getattr(msgs[0], "content", "") if msgs else ""

            started_at = time.time()
            # NOTE: stream_mode="updates" だと worker の state update は完了時にしか見えないため、
            # 並列性が分かるように開始ログを標準出力へ出す（PoC）。
            print(f"🧩 worker started task={task!s} at={started_at:.3f}")

            prompt = (
                "あなたは実行担当の自律型コーディングエージェントです。\n"
                "次のサブタスクを実行してください。必要ならファイルを読み、結果を日本語で報告してください。\n\n"
                f"[サブタスク]\n{task}\n\n"
                f"[元の依頼]\n{original_request}\n"
            )

            source_dir = state.get("source_dir")
            source_dirs = state.get("source_dirs")
            zip_path = state.get("zip_path")

            # ツール選択（ローカル優先、次にzip、最後に通常）
            tool = None
            tool_args: Dict[str, Any] = {"prompt": prompt}

            if "run_executor_local" in tools_by_name:
                tool = tools_by_name["run_executor_local"]
                if source_dirs is not None:
                    tool_args["source_dirs"] = [str(p) for p in source_dirs]
                elif source_dir is not None:
                    tool_args["source_dir"] = str(source_dir)
                tool_args["timeout"] = 600
            elif "run_autonomous_agent_executor_zip" in tools_by_name and (zip_path or source_dir or source_dirs):
                tool = tools_by_name["run_autonomous_agent_executor_zip"]
                if zip_path:
                    tool_args["zip_path"] = zip_path
                elif source_dir is not None:
                    tool_args["dir_path"] = str(source_dir)
                elif source_dirs is not None and source_dirs:
                    tool_args["dir_path"] = str(source_dirs[0])
                tool_args["timeout"] = 900
            elif "run_autonomous_agent_executor" in tools_by_name:
                tool = tools_by_name["run_autonomous_agent_executor"]
                tool_args["timeout"] = 600
            else:
                raise RuntimeError(f"No suitable executor tool found. tools={list(tools_by_name.keys())}")

            result = await tool.ainvoke(tool_args)

            ended_at = time.time()
            print(f"🧩 worker ended   task={task!s} at={ended_at:.3f} elapsed={ended_at - started_at:.3f}s")
            return {
                "results": [
                    {
                        "task": task,
                        "started_at": started_at,
                        "ended_at": ended_at,
                        "elapsed_sec": round(ended_at - started_at, 3),
                        "tool": getattr(tool, "name", None),
                        "result": result,
                    }
                ]
            }

        async def join(state: ParallelExecutionState) -> Dict[str, Any]:
            results = state.get("results") or []
            lines: list[str] = []
            lines.append(f"並列実行の結果サマリ (max_parallel={max_parallel}):")
            for i, item in enumerate(results, start=1):
                task = item.get("task")
                tool_name = item.get("tool")
                elapsed = item.get("elapsed_sec")
                res = item.get("result")
                status = res.get("status") if isinstance(res, dict) else None
                stdout = res.get("stdout") if isinstance(res, dict) else None
                tail = ""
                if isinstance(stdout, str) and stdout.strip():
                    tail = stdout.strip().splitlines()[-1]
                lines.append(f"{i}. task={task!s} tool={tool_name!s} elapsed={elapsed!s}s status={status!s} last={tail!s}")

            report = "\n".join(lines)
            # 次段の summarizer で使えるよう state に保持しておく
            return {"raw_summary": report}

        async def planner_summarize(state: ParallelExecutionState) -> Dict[str, Any]:
            """join の raw_summary と results をもとに、Plannerがユーザー向けに最終報告を生成する。"""
            msgs = state.get("messages") or []
            original_request = getattr(msgs[0], "content", "") if msgs else ""
            raw_summary = (state.get("raw_summary") or "").strip()
            results = state.get("results") or []

            if not include_planner_summary:
                # 旧挙動互換: raw_summary をそのまま返す
                return {"messages": [AIMessage(content=raw_summary)]}

            # Planner(LLM)で要約
            summary_msg = await LangGraphNodes.planner_summarize_results(
                original_request=original_request,
                results=results,
                raw_summary=raw_summary,
            )

            # 生サマリも併記（デバッグ/検証用）
            final_text = (getattr(summary_msg, "content", "") or "").strip()
            if raw_summary:
                final_text = f"{final_text}\n\n---\n[詳細サマリ]\n{raw_summary}".strip()
            return {"messages": [AIMessage(content=final_text)]}

        workflow = StateGraph(ParallelExecutionState)
        workflow.add_node("plan_to_tasks", plan_to_tasks)
        workflow.add_node("dispatch", dispatch)
        workflow.add_node("worker", worker)
        workflow.add_node("join", join)
        workflow.add_node("planner_summarize", planner_summarize)

        if include_planner:
            workflow.add_node("planner", LangGraphNodes.planner_node)
            workflow.add_edge(START, "planner")
            workflow.add_edge("planner", "plan_to_tasks")
        else:
            workflow.add_edge(START, "plan_to_tasks")

        workflow.add_edge("plan_to_tasks", "dispatch")
        workflow.add_conditional_edges("dispatch", route_after_dispatch)
        workflow.add_edge("worker", "dispatch")
        workflow.add_edge("join", "planner_summarize")
        workflow.add_edge("planner_summarize", END)

        return workflow
            
