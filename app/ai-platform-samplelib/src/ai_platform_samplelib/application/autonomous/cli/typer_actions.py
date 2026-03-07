from typing import Callable, Generator
import typer
import asyncio
from pathlib import Path
from tabulate import tabulate  # pip install tabulate (一覧表示用)
import signal

from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from pathlib import Path
from python_on_whales import docker as whales


# 内部パッケージのインポート
from ..core.abstract_actions import AbstractActions
from ..model.models import TaskStatus, ComposeConfig
from ..model.models import TaskStatus, ComposeConfig
from ..core.coding_agent_runner import CodingAgentRunner

from ..core.task_manager import TaskManager

class TyperActions(AbstractActions) :

    console = Console()

    def after_start_task_action(self, tid: str) -> None:
        """タスク開始後のアクション"""
        self.console.print(f"[bold green]🚀 タスクを開始しました: {tid}[/bold green]")
        
    def after_start_detach_task_action(self, tid: str) -> None:
        self.console.print(f"🔗 [yellow]バックグラウンドで実行中です。'status {tid}' で確認してください。[/yellow]")

    # 進捗表示処理
    async def progress_action(self, tid: str) -> TaskStatus:
        # ここでは例として、タスクの状態を定期的にチェックして表示するロジックを記述します。
        # 実際には ComposeRunner.get_status() を呼び出して、タスクの状態やログを取得することになります。
        last_line_count = 0
        last_stderr_count = 0
        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()

        with Live(Spinner("dots", text="実行中...", style="cyan"), refresh_per_second=4, transient=True) as live:
            try:
                while not stop_event.is_set():
                    status_data = await TaskManager.get_status(tid, tail=1000)
                    
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
                self.console.print(f"[bold red]❌ エラーが発生しました: {e}[/bold red]")
            finally:
                for sig in (signal.SIGINT, signal.SIGTERM):
                    loop.remove_signal_handler(sig)

        # ループを抜けた後の処理
        status_data = await TaskManager.get_status(tid)

        self.console.print(f"\n🏁 終了ステータス: [bold cyan]{status_data.status}[/bold cyan]")

        # 中断時の処理
        if stop_event.is_set():
            if typer.confirm("⚠️ 中断しました。コンテナを停止して削除しますか？", default=True):
                await TaskManager.cancel_task(tid)
                self.console.print(f"🛑 タスク {tid} をキャンセルしました。")
                status_data.status = "cancelled"  # キャンセルフラグを立てる（必要に応じて）
        return status_data

    def after_complete_action(
            self, runner: CodingAgentRunner,dest: Path) -> None:
        if typer.confirm("✅ 完了しました。成果物をローカルに同期（pull）しますか？", default=True):
            # 既存の pull コマンドロジックを再利用
            try:
                import shutil
                shutil.copytree(runner.workspace, dest, dirs_exist_ok=True)
                self.console.print(f"[bold green]✨ 成果物を {dest} に同期しました。[/bold green]")
            except Exception as e:
                self.console.print(f"[bold red]❌ 同期中にエラーが発生しました: {e}[/bold red]")

    def after_task_not_found_action(self) -> None:
        typer.echo("タスクは見つかりませんでした。")

    def after_list_action(self, table: list) -> None:
        typer.echo(tabulate(table, headers=["Task ID", "Status", "Created At"]))

    def after_cancel_action(self, task_id: str) -> None:
        self.console.print(f"[bold yellow]🛑 タスク {task_id} をキャンセルしました。[/bold yellow]")

    def after_get_status_action(self, task_id: str, status_data: TaskStatus) -> None:
        self.console.print(f"=== Task: {task_id} [{status_data.status}] ===")
        if status_data.stdout:
            self.console.print(f"\n[STDOUT]\n{status_data.stdout}")
        if status_data.stderr:
            self.console.print(f"\n[STDERR]\n{status_data.stderr}", style="red")
        if status_data.artifacts:
            self.console.print(f"\n[Artifacts]\n{', '.join(status_data.artifacts)}")

    def before_pull_action(self, runner: CodingAgentRunner) -> None:
        if not runner.workspace.exists():
            # 赤文字でエラーを表示して終了
            typer.secho(f"❌ エラー: タスクディレクトリ {runner.workspace} が見つかりません。", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

    def pull_progress_action(self, func: Callable, dest: Path):
        try:
            # 展開先をクリーンアップするか、上書きコピー
            func()
            typer.secho(f"✅ 成果物を {dest} に同期しました。", fg=typer.colors.GREEN)
        except Exception as e:
            typer.secho(f"❌ 同期中にエラーが発生しました: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

    def prune_progress_action(self, generator: Generator[str, None, None]):
        """管理対象の孤立したコンテナを強制掃除します (APIサーバーの終了処理と同等)"""
        
        typer.echo("🧹 掃除を開始します...")
        try:
            for msg in generator:
                typer.echo(f"✅ {msg}")
                # コンテナを削除するロジックは generator 内で実行される想定
        except Exception as e:
            typer.secho(f"❌ 掃除中にエラー: {e}", fg=typer.colors.RED)

