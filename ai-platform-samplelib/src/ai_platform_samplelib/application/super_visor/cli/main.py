import asyncio
import pathlib
import uuid
import typer
from typing import Optional, Dict, Any, List
from typing_extensions import Annotated

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langgraph.graph import MessagesState, START, END

# インポートパスは環境に合わせて適宜調整してください
from ai_platform_samplelib.application.autonomous.core.runner import ComposeRunner
from ai_platform_samplelib.application.autonomous.model.models import ComposeConfig
from ..core.parallel_agent_workflow import ParallelAgentWorkflow

app = typer.Typer(help="統合エージェント実行 CLI (Planning対応)", add_completion=False)

# ==========================================
# 1. ローカル実行ツール (変更なし)
# ==========================================
@tool
async def run_executor_local(
    prompt: str,
    source_dir: Optional[pathlib.Path] = None,
    timeout: int = 300,
) -> Dict[str, Any]:
    """コーディングエージェントを直接起動します。"""
    compose_config = ComposeConfig.from_env()
    task_id = str(uuid.uuid4())
    typer.secho(f"\n[Executor] Task started: {task_id}", fg=typer.colors.CYAN)

    await ComposeRunner.create_and_run(
        compose_config=compose_config,
        background_tasks=None, 
        prompt=prompt,
        source_path=source_dir,
        task_id=task_id,
        timeout=timeout
    )

    while True:
        status = await ComposeRunner.get_status(task_id)
        if status.status in ["completed", "failed", "cancelled"]:
            return status.model_dump()
        
        if status.stdout:
            last_line = status.stdout.strip().splitlines()[-1] if status.stdout.strip() else ""
            print(f"  [{task_id[:8]}] {last_line}", end="\r")
            
        await asyncio.sleep(2)

local_tools = [run_executor_local]
local_tool_node = ToolNode(local_tools)

# ==========================================
# 2. 計画策定用ノードの追加
# ==========================================

async def planner_node(state: MessagesState):
    """指示に対して具体的な実行計画（タスクリスト）を作成する"""
    # ここでは ParallelAgentWorkflow 内の LLM 生成ロジックを流用するか、
    # 直接 LLMUtils を使って計画を立てます。
    from ..core.utils import LLMUtils # プロジェクトの構造に合わせてインポート
    llm = LLMUtils.create_llm()
    
    sys_msg = SystemMessage(content=(
        "あなたは優秀なシニアエンジニア兼プロジェクトマネージャーです。"
        "ユーザーの指示に対し、複数のAutonomous Agentをどのように動かすか具体的な実行計画を立ててください。"
        "計画はMarkdownのリスト形式で出力し、最後に「この計画で実行を開始しますか？」と添えてください。"
    ))
    
    response = await llm.ainvoke([sys_msg] + state["messages"])
    # 応答をメッセージに追加
    return {"messages": [response]}

# ==========================================
# 3. ロジック本体
# ==========================================
import asyncio
import typer
# ... 他のインポート ...

async def run_integrated_agent_core(message: str, source_path: Optional[pathlib.Path], auto_approve: bool):
    typer.secho("🤖 統合エージェント（Planning Mode）を起動中...", fg=typer.colors.MAGENTA, bold=True)
    
    wf = ParallelAgentWorkflow()
    # プランナーを有効化
    graph = wf.create_graph(include_planner=True).compile()

    user_input = message
    if source_path:
        user_input += f"\n\n[Context] 作業ディレクトリ: {source_path.resolve()}"

    initial_input: MessagesState = {"messages": [HumanMessage(content=user_input)]}

    # stream_mode="updates" でノードごとの出力をハンドリング
    async for event in graph.astream(initial_input, stream_mode="updates"):
        # プランナーによる計画策定フェーズ
        print(event) # デバッグ用: イベントの全体構造を確認
        if "planner" in event:
            latest_msg = event["planner"]["messages"][-1]
            typer.secho("\n📋 --- 提案された実行計画 ---", fg=typer.colors.YELLOW, bold=True)
            typer.echo(latest_msg.content)
            
            # 承認確認（--yes オプションがない場合）
            if not auto_approve:
                if not typer.confirm("\n上記計画で実行を開始しますか？"):
                    typer.secho("🚫 実行はキャンセルされました。", fg=typer.colors.RED, bold=True)
                    return # 処理を中断

        # エージェントによる実行フェーズ
        if "agent" in event:
            latest_msg = event["agent"]["messages"][-1]
            if isinstance(latest_msg, AIMessage) and latest_msg.tool_calls:
                for tc in latest_msg.tool_calls:
                    typer.secho(f"\n🚀 ツール実行中: {tc['name']}", fg=typer.colors.CYAN)
                    # print(f"   Args: {tc['args']}")
            elif latest_msg.content:
                typer.secho("\n🏁 最終報告:", fg=typer.colors.GREEN, bold=True)
                typer.echo(latest_msg.content)


# ==========================================
# 4. Typer コマンド定義
# ==========================================
# CLIコマンドの定義
@app.command()
def run(
    message: Annotated[str, typer.Argument(help="指示内容")],
    source_dir: Annotated[Optional[pathlib.Path], typer.Option("--source-dir", "-s", exists=True)] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="計画承認をスキップ")] = False,
):
    """
    計画を立て、ユーザーの承認を得てから自律エージェントを実行します。
    """
    asyncio.run(run_integrated_agent_core(message, source_dir, yes))



if __name__ == "__main__":
    app()