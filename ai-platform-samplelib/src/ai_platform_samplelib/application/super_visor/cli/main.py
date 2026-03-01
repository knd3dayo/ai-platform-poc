import asyncio
import pathlib
import uuid
import typer
from typing import Optional, Dict, Any, List
from typing_extensions import Annotated # Python 3.9未満の場合は必要

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langgraph.graph import MessagesState 

# 以前リファクタリングしたクラス群
from ai_platform_samplelib.application.autonomous.core.runner import ComposeRunner
from ai_platform_samplelib.application.autonomous.model.models import ComposeConfig
from ..core.parallel_agent_workflow import ParallelAgentWorkflow

# Typerのインスタンス作成
app = typer.Typer(help="統合エージェント実行 CLI", add_completion=False)

# ==========================================
# 1. ローカル直接実行ツールの定義 (変更なし)
# ==========================================

@tool
async def run_executor_local(
    prompt: str,
    source_dir: Optional[pathlib.Path] = None,
    timeout: int = 300,
) -> Dict[str, Any]:
    """
    【ローカル実行版】コーディングエージェントを直接起動します。
    """
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
            # Typer形式のログ出力
            print(f"  [{task_id[:8]}] {last_line}", end="\r")
            
        await asyncio.sleep(2)

local_tools = [run_executor_local]
local_tool_node = ToolNode(local_tools)

# ==========================================
# 2. ロジック本体 (async)
# ==========================================

async def run_integrated_agent_core(message: str, source_path: Optional[pathlib.Path]):
    typer.secho("🤖 統合エージェントを起動しています...", fg=typer.colors.MAGENTA, bold=True)
    
    wf = ParallelAgentWorkflow()
    builder = wf.create_graph()
    builder.add_node("local_tools", local_tool_node)
    builder.add_edge("agent", "local_tools")
    builder.add_edge("local_tools", "agent")
    
    graph = builder.compile()

    user_input = message
    if source_path:
        # 絶対パスに変換してコンテキストに追加
        abs_path = source_path.resolve()
        user_input += f"\n\n[Context] 以下のソースディレクトリが提供されています: {abs_path}"

    initial_input: MessagesState = {"messages": [HumanMessage(content=user_input)]}

    async for event in graph.astream(initial_input, stream_mode="values"):
        if "messages" in event:
            latest_msg = event["messages"][-1]
            
            if isinstance(latest_msg, AIMessage):
                if latest_msg.tool_calls:
                    for tc in latest_msg.tool_calls:
                        typer.secho(f"\n🛠️  ツール呼び出し: {tc['name']}", fg=typer.colors.YELLOW)
                        typer.echo(f"   引数: {tc['args']}")
                elif latest_msg.content:
                    typer.secho(f"\n🤖 Supervisor:", fg=typer.colors.GREEN, bold=True)
                    typer.echo(latest_msg.content)
            elif isinstance(latest_msg, HumanMessage):
                typer.secho(f"\n👤 User:", fg=typer.colors.BLUE, bold=True)
                typer.echo(latest_msg.content)

# ==========================================
# 3. Typer コマンド定義
# ==========================================

@app.command()
def run(
    message: Annotated[str, typer.Argument(help="エージェントへの指示内容")],
    source_dir: Annotated[
        Optional[pathlib.Path], 
        typer.Option("--source-dir", "-s", help="入力ソースディレクトリのパス", exists=True, file_okay=False, dir_okay=True, resolve_path=True)
    ] = None,
):
    """
    Supervisor Agentを起動し、必要に応じてローカルのExecutorを呼び出します。
    """
    try:
        asyncio.run(run_integrated_agent_core(message, source_dir))
    except KeyboardInterrupt:
        typer.echo("\n👋 終了します")
        raise typer.Exit()

if __name__ == "__main__":
    app()