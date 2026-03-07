import typer
import asyncio
from pathlib import Path
from typing import Optional

# 内部パッケージのインポート
from ..core.task_manager import TaskManager
from ..core.task_service import TaskService
from .typer_actions import TyperActions

# --- CLI Layer: コマンドの定義 ---
actions = TyperActions()

app = typer.Typer(help="Autonomous Agent Executor CLI Tool")

@app.command()
def run(
    prompt: str = typer.Argument(..., help="指示内容"),
    src: Optional[Path] = typer.Option(None, "--src", "-s"),
    task_id: Optional[str] = typer.Option(None, "--id"),
    timeout: int = 300,
    wait: bool = True,
    dest: Path = typer.Option("./src-updated", help="成果物の同期先ディレクトリ"),
):
    """新しいタスクを実行します。"""
    async def main():
        await TaskService.run(
        actions,
        prompt,
        src,
        task_id,
        timeout,
        wait,
        dest
    )
        
    asyncio.run(main())

@app.command(name="list")
def list_tasks():
    """一覧表示"""
    actions.after_list_action(TaskManager.list_tasks())

@app.command()
def status(task_id: str, tail: int = 20):
    """状態確認"""
    async def main():
        status_data = await TaskManager.show_status(task_id, tail)
        actions.after_get_status_action(task_id, status_data)

    asyncio.run(main())

@app.command()
def cancel(task_id: str):
    """強制終了"""
    async def main():
        await TaskManager.cancel_task(task_id)
        actions.after_cancel_action(task_id)

    asyncio.run(main())

@app.command()
def pull(task_id: str, dest: Path = typer.Option("./src-updated")):
    """同期実行"""
    def pull_func():
        TaskService.pull_artifacts(task_id, dest)
    actions.pull_progress_action(pull_func, dest)

@app.command()
def prune(compose_service_name: str):
    """掃除実行"""
    actions.prune_progress_action(TaskManager.prune_containers(compose_service_name))

if __name__ == "__main__":
    app()