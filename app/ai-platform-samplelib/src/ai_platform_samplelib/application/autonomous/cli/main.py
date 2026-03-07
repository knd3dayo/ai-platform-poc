import typer
import asyncio
from pathlib import Path
from typing import Optional

# 内部パッケージのインポート
from ..core.task_manager import TaskManager
from ..core.task_service import TaskService
from ..core.coding_agent_runner import CodingAgentRunner
from ..core.abstract_actions import AbstractActions
from ..model.models import TaskStatus, ComposeConfig, CodingAgentConfig
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
    TaskManager.load_tasks()
    async def main():
        params = {
            "background_tasks": None,
            "prompt": prompt,
            "task_id": task_id,
        }
        if src and src.exists():
            params["source_paths"] = src

        runner = await CodingAgentRunner.create_runner(**params)
        async for status in TaskService.run_task(runner, timeout, dest, wait):
            if status.sub_status == "starting":
                actions.after_start_task_action(status.task_id)
            elif status.sub_status == "running-background":
                actions.after_start_detach_task_action(status.task_id)
                break  # バックグラウンドで走らせる場合はここでループを抜ける
            elif status.status == "completed":
                actions.after_complete_action(runner, dest)
                break  # 完了したらループを抜ける
            
            await actions.progress_action(status.task_id)    
        
    asyncio.run(main())

@app.command(name="list")
def list_tasks():
    """一覧表示"""
    actions.after_list_action(TaskManager.list_tasks())

@app.command()
def status(task_id: str, tail: int = 20):
    """状態確認"""
    asyncio.run(TaskManager.show_status(task_id, tail))

@app.command()
def cancel(task_id: str):
    """強制終了"""
    asyncio.run(TaskManager.cancel_task(task_id))

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