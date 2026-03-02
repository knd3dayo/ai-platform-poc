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
service = TaskService(actions)
app = typer.Typer(help="Autonomous Agent Executor CLI Tool")

@app.command()
def run(
    prompt: str = typer.Argument(..., help="指示内容"),
    src: Optional[Path] = typer.Option(None, "--src", "-s"),
    task_id: Optional[str] = typer.Option(None, "--id"),
    timeout: int = 300,
    detach: bool = False,
    dest: Path = typer.Option("./src-updated", help="成果物の同期先ディレクトリ"),
):
    """新しいタスクを実行します。"""
    TaskManager.load_tasks()
    asyncio.run(service.run_task(prompt, src, task_id, timeout, dest, detach))

@app.command(name="list")
def list_tasks():
    """一覧表示"""
    service.list_tasks()

@app.command()
def status(task_id: str, tail: int = 20):
    """状態確認"""
    asyncio.run(service.show_status(task_id, tail))

@app.command()
def cancel(task_id: str):
    """強制終了"""
    asyncio.run(service.cancel_task(task_id))

@app.command()
def pull(task_id: str, dest: Path = typer.Option("./src-updated")):
    """同期実行"""
    service.pull_artifacts(task_id, dest)

@app.command()
def prune():
    """掃除実行"""
    service.prune_containers()

if __name__ == "__main__":
    app()