from typing import Dict, Any, Optional, List
import pathlib
import uuid
import asyncio
import typer

from langchain_core.messages import SystemMessage
from langchain_core.messages import HumanMessage

from langgraph.graph import MessagesState
from langchain_core.tools import tool

from ..core.utils import LLMUtils
from ai_platform_samplelib.application.autonomous.core.runner import ComposeRunner
from ai_platform_samplelib.application.autonomous.model.models import ComposeConfig

# ==========================================
# 1. ローカル実行ツール (変更なし)
# ==========================================
@tool
async def run_executor_local(
    prompt: str,
    source_dir: Optional[str] = None,
    source_dirs: Optional[List[str]] = None,
    timeout: int = 300,
) -> Dict[str, Any]:
    """コーディングエージェントを直接起動します。"""
    compose_config = ComposeConfig.from_env()
    task_id = str(uuid.uuid4())
    typer.secho(f"\n[Executor] Task started: {task_id}", fg=typer.colors.CYAN)

    normalized_source_dir: Optional[pathlib.Path] = None
    normalized_source_dirs: Optional[list[pathlib.Path]] = None

    if isinstance(source_dirs, list) and source_dirs:
        normalized_source_dirs = [pathlib.Path(p) for p in source_dirs if isinstance(p, str) and p]
    elif isinstance(source_dir, str) and source_dir:
        normalized_source_dir = pathlib.Path(source_dir)

    await ComposeRunner.create_and_run(
        compose_config=compose_config,
        background_tasks=None, 
        prompt=prompt,
        source_path=normalized_source_dir,
        source_paths=normalized_source_dirs,
        task_id=task_id,
        timeout=timeout
    )

    last_stdout: str = ""
    last_printed_lines: list[str] = []

    def _emit_new_lines(stdout: str) -> None:
        nonlocal last_stdout, last_printed_lines

        if not stdout:
            return

        # logs() には \r を含む進捗表示が混ざりやすいので正規化
        normalized = stdout.replace("\r", "")

        # まず全文が取れている場合は増分だけ出す（最も見やすい）
        if normalized.startswith(last_stdout):
            delta = normalized[len(last_stdout):]
            last_stdout = normalized
            lines = [ln for ln in delta.splitlines() if ln.strip()]
        else:
            # tail 取得などで先頭が欠ける場合は「最後の数行」を出す
            last_stdout = normalized
            lines = [ln for ln in normalized.splitlines() if ln.strip()]

            # 直前に出した末尾と同じ行はスキップ
            if last_printed_lines:
                # 共通の末尾を落とす（簡易）
                while lines and last_printed_lines and lines[0] == last_printed_lines[0]:
                    lines.pop(0)

        if not lines:
            return

        # 1回のポーリングで出しすぎない
        if len(lines) > 50:
            lines = lines[-50:]

        for ln in lines:
            print(f"  [{task_id[:8]}] {ln}")

        last_printed_lines = lines[-10:]

    while True:
        # 実行中は full logs を取り、CLI で増分表示する
        status = await ComposeRunner.get_status(task_id, tail=None)
        if status.status in ["completed", "failed", "cancelled"]:
            # 終了時に最後のログを出してから返す
            if status.stdout:
                _emit_new_lines(status.stdout)
            return status.model_dump()

        if status.stdout:
            _emit_new_lines(status.stdout)
            
        await asyncio.sleep(2)




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

