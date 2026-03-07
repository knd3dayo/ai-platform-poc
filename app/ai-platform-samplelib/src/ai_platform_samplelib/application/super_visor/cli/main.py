import asyncio
import pathlib
import typer
from typing import Optional, Callable, Awaitable, cast
from typing_extensions import Annotated
from ..core.parallel_agent_workflow import run_integrated_agent_core, run_integrated_agent_hitl_cli

# インポートパスは環境に合わせて適宜調整してください

app = typer.Typer(help="統合エージェント実行 CLI (Planning対応)", add_completion=False)


def _infer_repo_root(start: pathlib.Path) -> Optional[pathlib.Path]:
    """`--source-dir` 未指定時の既定作業ディレクトリを推測する。

    CLI をリポジトリ配下のどこから実行しても、PoC のルート
    (例: 14-front/, ai-platform-samplelib/ が存在する階層) を見つけて返す。
    """
    start = start.resolve()
    for candidate in (start, *start.parents):
        if (candidate / "14-front" / "package.json").exists() and (candidate / "ai-platform-samplelib").exists():
            return candidate
    return None

# ==========================================
# 4. Typer コマンド定義
# ==========================================
# CLIコマンドの定義
@app.command()
def run(
    message: Annotated[str, typer.Argument(help="指示内容")],
    source_dirs: Annotated[
        Optional[list[pathlib.Path]],
        typer.Option(
            "--source-dir",
            "-s",
            exists=True,
            help="executor の /workspace に取り込むホスト側パス（複数指定可。例: -s ./14-front -s ./ai-platform-samplelib）",
        ),
    ] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="計画承認をスキップ")] = False,
    session_dir: Annotated[
        Optional[pathlib.Path],
        typer.Option(
            "--session-dir",
            exists=False,
            file_okay=False,
            dir_okay=True,
            help="HITL一時停止ファイルの保存先（省略時は推測したリポジトリ配下 .sv_sessions）",
        ),
    ] = None,
):
    """
    計画を立て、ユーザーの承認を得てから自律エージェントを実行します。
    """
    if not source_dirs:
        inferred = _infer_repo_root(pathlib.Path.cwd())
        if inferred is not None:
            source_dirs = [inferred]
            typer.secho(
                f"[super-visor] --source-dir 未指定のため自動設定しました: {inferred}",
                fg=typer.colors.BLUE,
            )
        else:
            typer.secho(
                "[super-visor] --source-dir が未指定のため /workspace は空の可能性があります。"
                " 必要なら -s でリポジトリルートを指定してください。",
                fg=typer.colors.YELLOW,
            )
    if session_dir is None:
        inferred = _infer_repo_root(pathlib.Path.cwd())
        if inferred is not None:
            session_dir = inferred / ".sv_sessions"
        else:
            session_dir = pathlib.Path.cwd() / ".sv_sessions"

    async def _main() -> None:
        if yes:
            runner = cast(
                Callable[[str, Optional[list[pathlib.Path]], bool], Awaitable[None]],
                run_integrated_agent_core,
            )
            await runner(message, source_dirs, yes)
            return

        # HITL（停止→resume）モード
        await run_integrated_agent_hitl_cli(
            message=message,
            source_dirs=source_dirs or [],
            session_dir=session_dir,
            auto_approve=False,
        )

    asyncio.run(_main())


@app.command()
def resume(
    session_file: Annotated[
        pathlib.Path,
        typer.Argument(exists=True, dir_okay=False, file_okay=True, help="HITLセッションJSONのパス"),
    ],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="残りサブタスクを全て自動承認")]=False,
):
    """HITLで一時停止したセッションを再開する。"""

    async def _main() -> None:
        await run_integrated_agent_hitl_cli(
            message="",
            source_dirs=[],
            resume_from=session_file,
            auto_approve=yes,
        )

    asyncio.run(_main())
    

if __name__ == "__main__":
    app()