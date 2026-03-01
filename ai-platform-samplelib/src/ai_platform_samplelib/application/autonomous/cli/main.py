import typer
import asyncio
import json
import os
from pathlib import Path
from typing import Optional
from tabulate import tabulate  # pip install tabulate (一覧表示用)
from dotenv import load_dotenv
import shutil
import signal

# 内部パッケージのインポート
from ..core.runner import ComposeRunner
from ..model.models import TaskStatus, ComposeConfig
from ..core.task_manager import TaskManager

# 設定

app = typer.Typer(help="Cline Executor CLI Tool")


import signal
import asyncio
from typing import Optional
from pathlib import Path
import typer
from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.panel import Panel


import zipfile
import tempfile
import shutil
from pathlib import Path
import atexit

def create_temporary_zip(source_dir: Path) -> Path:
    """ディレクトリを一時的なZIPファイルに固める"""
    tmp_zip = Path(tempfile.NamedTemporaryFile(suffix=".zip", delete=False).name)
    atexit.register(lambda: tmp_zip.unlink(missing_ok=True))  # 終了時に自動削除
    with zipfile.ZipFile(tmp_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file in source_dir.rglob('*'):
            if file.is_file():
                # source_dir からの相対パスで格納
                zf.write(file, file.relative_to(source_dir))
    return tmp_zip

console = Console()

@app.command()
def run(
    prompt: str = typer.Argument(..., help="Clineへの指示内容"),
    src: Optional[Path] = typer.Option(None, "--src", "-s", help="送付するファイルまたはディレクトリ"),    
    task_id: Optional[str] = typer.Option(None, "--id", help="既存のタスクID（再開用）"),
    timeout: int = typer.Option(300, help="タイムアウト（秒）"),
    detach: bool = typer.Option(False, "--detach", "-d", help="バックグラウンドで実行する"),
    dest: Path = typer.Option("./src-updated", help="成果物の同期先"),
):


    """新しいタスクを実行し、ログ表示・エラー色分け・完了後の同期を行います。"""
    ComposeRunner.load_tasks()
    
    async def _execute():
        config = ComposeConfig.from_env()

        # --- ファイル準備ロジック ---
        zip_to_send = None
        temp_used = False
        
        if src and src.exists():
            if src.is_dir():
                console.print(f"📦 ディレクトリ [cyan]{src}[/cyan] をZIP化しています...")
                zip_to_send = create_temporary_zip(src)
                temp_used = True
            elif src.suffix == ".zip":
                zip_to_send = src
            else:
                # 単一ファイルの場合もZIPに包むか、既存の initial_files ロジックに流す
                # ここでは汎用性のためにZIP化を推奨
                pass

        params = {
            "background_tasks": None,  # CLIモードでは直接 await するため BackgroundTasks は使用しない
            "compose_config": config,
            "prompt": prompt,
            "task_id": task_id,
            "timeout": timeout
        }
        if zip_to_send:
            params["zip_file"] = zip_to_send

        tid = await ComposeRunner.create_and_run(
            **params
        )
        ComposeRunner.save_tasks()
        console.print(f"[bold green]🚀 タスクを開始しました: {tid}[/bold green]")

        if detach:
            console.print(f"🔗 [yellow]バックグラウンドで実行中です。'status {tid}' で確認してください。[/yellow]")
            return

        # --- ログ表示 & 中断監視ループ ---
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()
        last_line_count = 0
        last_stderr_count = 0

        def handle_interrupt():
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, handle_interrupt)

        # 2. スピナー（進捗表示）の導入
        with Live(Spinner("dots", text="実行中...", style="cyan"), refresh_per_second=4, transient=True) as live:
            try:
                while not stop_event.is_set():
                    status_data = await ComposeRunner.get_status(tid, tail=1000)
                    
                    # 1. 標準出力の表示
                    if status_data.stdout:
                        lines = status_data.stdout.splitlines()
                        if len(lines) > last_line_count:
                            for line in lines[last_line_count:]:
                                live.console.print(f"  [white]{line}[/white]")
                            last_line_count = len(lines)

                    # 1. エラー(STDERR)の色分け表示
                    if status_data.stderr:
                        err_lines = status_data.stderr.splitlines()
                        if len(err_lines) > last_stderr_count:
                            for line in err_lines[last_stderr_count:]:
                                live.console.print(f"  [bold red]ERR> {line}[/bold red]")
                            last_stderr_count = len(err_lines)

                    # 終了判定
                    if status_data.status not in ["running", "pending"]:
                        break
                    
                    await asyncio.sleep(1.5)

            except Exception as e:
                console.print(f"[bold red]❌ エラーが発生しました: {e}[/bold red]")
            finally:
                for sig in (signal.SIGINT, signal.SIGTERM):
                    loop.remove_signal_handler(sig)

        # ループを抜けた後の処理
        status_data = await ComposeRunner.get_status(tid)
        console.print(f"\n🏁 終了ステータス: [bold cyan]{status_data.status}[/bold cyan]")

        # 中断時の処理
        if stop_event.is_set():
            if typer.confirm("⚠️ 中断しました。コンテナを停止して削除しますか？", default=True):
                await ComposeRunner.cancel_task(tid)
                console.print(f"🛑 タスク {tid} をキャンセルしました。")
            return

        # 3. 成果物の自動同期確認
        if status_data.status == "completed":
            if typer.confirm("✅ 完了しました。成果物をローカルに同期（pull）しますか？", default=True):
                # 既存の pull コマンドロジックを再利用
                try:
                    runner = ComposeRunner(compose_config=config, task_id=tid)
                    import shutil
                    shutil.copytree(runner.task_dir, dest, dirs_exist_ok=True)
                    console.print(f"[bold green]✨ 成果物を {dest} に同期しました。[/bold green]")
                except Exception as e:
                    console.print(f"[bold red]❌ 同期中にエラーが発生しました: {e}[/bold red]")

        ComposeRunner.save_tasks()

    asyncio.run(_execute())

@app.command(name="list")
def list_tasks():
    """タスクの一覧を表示します。"""
    ComposeRunner.load_tasks()
    tasks = ComposeRunner.get_all_tasks()
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
    asyncio.run(ComposeRunner.cancel_task(task_id))
    TaskManager.remove_task(task_id)  # タスクを管理から削除
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

@app.command()
def prune():
    """管理対象の孤立したコンテナを強制掃除します (APIサーバーの終了処理と同等)"""
    from python_on_whales import docker as whales
    
    typer.echo("🧹 掃除を開始します...")
    try:
        # APIサーバーの実装を再利用
        containers = whales.container.list(filters={"label": "managed_by=executor-service"})
        if not containers:
            typer.echo("掃除対象のコンテナはありません。")
            return
            
        for c in containers:
            c.remove(force=True)
            typer.echo(f"✅ Removed: {c.id[:12]}")
    except Exception as e:
        typer.secho(f"❌ 掃除中にエラー: {e}", fg=typer.colors.RED)

if __name__ == "__main__":
    app()