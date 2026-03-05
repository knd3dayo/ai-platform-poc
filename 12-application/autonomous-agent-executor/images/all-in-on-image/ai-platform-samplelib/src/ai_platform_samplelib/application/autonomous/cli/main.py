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
service = TaskService()
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
    TaskManager.load_tasks()
    async def main():
        async for status in service.run_task(prompt, src, task_id, timeout, dest, wait):
            if status.sub_status == "starting":
                actions.after_start_task_action(status.task_id)
            elif status.sub_status == "running-background":
                actions.after_start_detach_task_action(status.task_id)
                break  # バックグラウンドで走らせる場合はここでループを抜ける
            elif status.status == "completed":
                actions.after_complete_action(status.task_id, dest)
                break  # 完了したらループを抜ける
            
            await actions.progress_action(status.task_id)    
        
    asyncio.run(main())

@app.command(name="list")
def list_tasks():
    """一覧表示"""
    actions.after_list_action(service.list_tasks())

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
    def pull_func():
        service.pull_artifacts(task_id, dest)
    actions.pull_progress_action(pull_func, dest)

@app.command()
def prune():
    """掃除実行"""
    actions.prune_progress_action(service.prune_containers())

if __name__ == "__main__":
    app()