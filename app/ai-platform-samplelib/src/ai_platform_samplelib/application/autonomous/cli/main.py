import typer
import asyncio
from pathlib import Path
from typing import Optional
import time

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
    sources: Optional[list[Path]] = typer.Option(
        None,
        "--src",
        "-s",
        help="コンテナへ渡すソース（複数指定可）",
    ),
    task_id: Optional[str] = typer.Option(None, "--id"),
    timeout: int = 300,
    wait: bool = True,
    dest: Path = typer.Option("./src-updated", help="成果物の同期先ディレクトリ"),
):
    """新しいタスクを実行します。"""
    if sources:
        for src in sources:
            if not src.exists():
                raise typer.BadParameter(f"存在しないパスです: {src}", param_hint="--src/-s")
            if not (src.is_file() or src.is_dir()):
                raise typer.BadParameter(f"ファイル/ディレクトリではありません: {src}", param_hint="--src/-s")

    async def main():
        await TaskService.run(
        actions,
        prompt,
        sources,
        task_id,
        timeout,
        wait,
        dest
    )
        
    asyncio.run(main())


@app.command(hidden=True)
def monitor(
    task_id: str,
    interval: float = typer.Option(2.0, help="ポーリング間隔（秒）"),
    max_seconds: int = typer.Option(3600, help="最大監視時間（秒）"),
    tail: int = typer.Option(200, help="ログ取得行数"),
    quiet: bool = typer.Option(True, help="出力せず DB 更新のみ行う"),
):
    """デタッチ実行用の内部モニタ（status の自動更新）"""

    async def main():
        start = time.monotonic()
        while True:
            status_data = await TaskManager.show_status(task_id, tail=tail)
            if not quiet:
                actions.after_get_status_action(task_id, status_data)

            if status_data.status not in ("running", "pending"):
                return

            if time.monotonic() - start > max_seconds:
                return

            await asyncio.sleep(interval)

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