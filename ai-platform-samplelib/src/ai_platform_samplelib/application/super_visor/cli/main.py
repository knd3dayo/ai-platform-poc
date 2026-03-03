import asyncio
import pathlib
import typer
from typing import Optional, Callable, Awaitable, cast
from typing_extensions import Annotated
from ..core.parallel_agent_workflow import run_integrated_agent_core

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
    source_dir: Annotated[Optional[pathlib.Path], typer.Option("--source-dir", "-s", exists=True)] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="計画承認をスキップ")] = False,
):
    """
    計画を立て、ユーザーの承認を得てから自律エージェントを実行します。
    """
    if source_dir is None:
        inferred = _infer_repo_root(pathlib.Path.cwd())
        if inferred is not None:
            source_dir = inferred
            typer.secho(
                f"[super-visor] --source-dir 未指定のため自動設定しました: {source_dir}",
                fg=typer.colors.BLUE,
            )
        else:
            typer.secho(
                "[super-visor] --source-dir が未指定のため /workspace は空の可能性があります。"
                " 必要なら -s でリポジトリルートを指定してください。",
                fg=typer.colors.YELLOW,
            )
    async def _main() -> None:
        runner = cast(
            Callable[[str, Optional[pathlib.Path], bool], Awaitable[None]],
            run_integrated_agent_core,
        )
        await runner(message, source_dir, yes)

    asyncio.run(_main())
    

if __name__ == "__main__":
    app()