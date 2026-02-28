import typer
import asyncio
import json
import os
from pathlib import Path
from typing import Optional
from tabulate import tabulate  # pip install tabulate (一覧表示用)
from dotenv import load_dotenv
import shutil

# 内部パッケージのインポート
from ..core.runner import ComposeRunner
from ..core.model import TaskStatus, ComposeConfig

# 設定
load_dotenv()
TASKS_DB_PATH = Path(os.getenv("HOST_PROJECTS_ROOT", ".")) / "tasks_db.json"

app = typer.Typer(help="Cline Executor CLI Tool")

def load_tasks_db() -> dict:
    """ファイルからタスク情報を読み込む"""
    if not TASKS_DB_PATH.exists():
        return {}
    with open(TASKS_DB_PATH, "r") as f:
        data = json.load(f)
        # グローバルな tasks 辞書を更新 (runner.py側で定義されている想定)
        from ..core import runner
        for tid, tdata in data.items():
            runner.tasks[tid] = TaskStatus(**tdata)
        return runner.tasks

def save_tasks_db():
    """タスク情報をファイルに保存する"""
    from ..core import runner
    with open(TASKS_DB_PATH, "w") as f:
        # PydanticモデルをJSON化
        data = {k: v.model_dump(mode='json') for k, v in runner.tasks.items()}
        json.dump(data, f, indent=2)

@app.command()
def run(
    prompt: str = typer.Argument(..., help="Clineへの指示内容"),
    task_id: Optional[str] = typer.Option(None, "--id", help="既存のタスクID（再開用）"),
    timeout: int = typer.Option(300, help="タイムアウト（秒）"),
    detach: bool = typer.Option(False, "--detach", "-d", help="バックグラウンドで実行する"),
):
    """新しいタスクを実行します。"""
    load_tasks_db()
    
    async def _execute():
        # CLIではBackgroundTasksがないため、監視ロジックを制御するためにNoneを渡す
        # (Runner側で background_tasks が None の場合の考慮が必要)
        tid = await ComposeRunner.create_and_run(
            compose_config=ComposeConfig.from_env(),
            background_tasks=None, 
            prompt=prompt,
            task_id=task_id,
            timeout=timeout
        )
        save_tasks_db()
        typer.secho(f"🚀 タスクを開始しました: {tid}", fg=typer.colors.GREEN)
        
        if not detach:
            typer.echo("⏳ 完了を待機中... (Ctrl+C でデタッチ可能)")
            while True:
                status_data = await ComposeRunner.get_status(tid)
                if status_data.status not in ["running"]:
                    break
                await asyncio.sleep(2)
            
            save_tasks_db()
            typer.secho(f"\n🏁 終了ステータス: {status_data.status}", fg=typer.colors.CYAN)

    asyncio.run(_execute())

@app.command(name="list")
def list_tasks():
    """タスクの一覧を表示します。"""
    tasks = load_tasks_db()
    if not tasks:
        typer.echo("タスクは見つかりませんでした。")
        return

    table = []
    for tid, t in tasks.items():
        table.append([tid, t.status, t.created_at.strftime("%Y-%m-%d %H:%M")])
    
    typer.echo(tabulate(table, headers=["Task ID", "Status", "Created At"]))

@app.command()
def status(task_id: str, tail: int = typer.Option(20, help="ログの行数")):
    """特定のタスクの状態とログを確認します。"""
    load_tasks_db()
    
    async def _get():
        data = await ComposeRunner.get_status(task_id, tail=tail)
        typer.secho(f"=== Task: {task_id} [{data.status}] ===", fg=typer.colors.MAGENTA)
        if data.stdout:
            typer.echo(f"\n[STDOUT]\n{data.stdout}")
        if data.stderr:
            typer.secho(f"\n[STDERR]\n{data.stderr}", fg=typer.colors.RED)
        if data.artifacts:
            typer.echo(f"\n[Artifacts]\n{', '.join(data.artifacts)}")

    asyncio.run(_get())

@app.command()
def cancel(task_id: str):
    """実行中のタスクを強制終了します。"""
    load_tasks_db()
    asyncio.run(ComposeRunner.cancel_task(task_id))
    save_tasks_db()
    typer.echo(f"🛑 タスク {task_id} をキャンセルしました。")

import shutil

@app.command()
def pull(task_id: str, dest: Path = typer.Option("./src-updated", help="展開先ディレクトリ")):
    """AIが修正した成果物をローカルにダウンロードして展開します"""
    async def _pull():
        # インスタンス化してパスを特定
        runner = ComposeRunner(compose_config=ComposeConfig.from_env(), task_id=task_id)
        
        if not runner.task_dir.exists():
            # 赤文字でエラーを表示して終了
            typer.secho(f"❌ エラー: タスクディレクトリ {runner.task_dir} が見つかりません。", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        try:
            # 展開先をクリーンアップするか、上書きコピー
            # dirs_exist_ok=True は Python 3.8+ で有効
            shutil.copytree(runner.task_dir, dest, dirs_exist_ok=True)
            typer.secho(f"✅ 成果物を {dest} に同期しました。", fg=typer.colors.GREEN)
        except Exception as e:
            typer.secho(f"❌ 同期中にエラーが発生しました: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
            
    asyncio.run(_pull())
if __name__ == "__main__":
    app()