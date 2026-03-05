from typing import Dict, Optional, cast, ClassVar, Sequence, Union
from datetime import datetime
import uuid
import pathlib
import tempfile
import asyncio
import shlex
from datetime import datetime
import shutil
import os
from dotenv import dotenv_values
from urllib.parse import urlparse

from fastapi import UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from python_on_whales import docker as whales, Container, DockerClient
from ..model.models import TaskStatus, ComposeConfig
from .utils import ExecutorUtil
from .task_manager import TaskManager

from ai_platform_samplelib.util.logging import get_application_logger

logger = get_application_logger()

class ComposeRunner:
    """docker-compose.yml から設定を動的に読み取り、コンテナを実行するクラス"""

    @staticmethod
    def _is_loopback_base_url(url: str) -> bool:
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            return host in {"localhost", "127.0.0.1", "::1"}
        except Exception:
            return False

    def __init__(self, compose_config: ComposeConfig, task_id: Optional[str] = None):

        self.compose_config = compose_config 
        self.task_id = task_id or str(uuid.uuid4())  # タスクごとに一意のIDを生成
        self.task_dir = TaskManager.get_projects_root() / self.task_id
        self.task_dir.mkdir(parents=True, exist_ok=True)

        # クライアントは一度作れば使い回せます
        self.docker = DockerClient(
            compose_files=[self.compose_config.get_compose_path()],
            compose_project_directory=self.compose_config.project_directory,
            # service_name ではなく task_id をベースにしたユニークな名前に
            compose_project_name=f"task_{self.task_id}"
        )

    def prepare_workspace(self, 
                          initial_files: Optional[Dict[str, str]] = None, 
                          zip_file: Optional[UploadFile] = None, 
                          source_path: Optional[pathlib.Path] = None,
                          source_paths: Optional[Sequence[pathlib.Path]] = None):
        """入力ソースに関わらずワークスペースを準備する（共通化）"""
        if zip_file:
            ExecutorUtil.extract_zip_to_dir(zip_file, self.task_dir)
        if initial_files:
            for name, content in initial_files.items():
                (self.task_dir / name).write_text(content, encoding='utf-8')

        resolved_sources: list[pathlib.Path] = []
        if source_paths:
            resolved_sources.extend([p for p in source_paths if isinstance(p, pathlib.Path)])
        if isinstance(source_path, pathlib.Path):
            resolved_sources.append(source_path)

        # 互換性: 1つのディレクトリ指定は従来通り /workspace 直下に展開
        unique_sources: list[pathlib.Path] = []
        seen: set[str] = set()
        for p in resolved_sources:
            try:
                rp = str(p.resolve())
            except Exception:
                rp = str(p)
            if rp in seen:
                continue
            seen.add(rp)
            unique_sources.append(p)

        if len(unique_sources) == 1 and unique_sources[0].exists() and unique_sources[0].is_dir():
            self._safe_copy_dir(unique_sources[0], self.task_dir)
            return

        if unique_sources:
            inputs_dir = self.task_dir / "inputs"
            inputs_dir.mkdir(parents=True, exist_ok=True)

            used_names: set[str] = set()

            def _alloc_name(base: str) -> str:
                base = (base or "source").strip() or "source"
                name = base
                i = 2
                while name in used_names:
                    name = f"{base}__{i}"
                    i += 1
                used_names.add(name)
                return name

            for src in unique_sources:
                if not src.exists():
                    continue

                target_name = _alloc_name(src.name)
                target_path = inputs_dir / target_name

                if src.is_dir():
                    self._safe_copy_dir(src, target_path)
                else:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, target_path)

    @staticmethod
    def _safe_copy_dir(src: pathlib.Path, dst: pathlib.Path) -> None:
        """src ディレクトリを dst に安全にコピーする。

        - 巨大/不要/権限が怪しいディレクトリ（data, .git 等）はスキップ
        - PermissionError 等はスキップして継続
        """
        skip_top = {
            ".git",
            ".venv",
            "node_modules",
            "__pycache__",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            "data",  # clickhouse/postgres 等の永続ボリュームが入りがち
        }

        src = src.resolve()
        dst.mkdir(parents=True, exist_ok=True)

        for root, dirs, files in os.walk(src, topdown=True, followlinks=False):
            root_path = pathlib.Path(root)
            rel = root_path.relative_to(src)

            # top-level skip
            if rel.parts and rel.parts[0] in skip_top:
                dirs[:] = []
                continue

            # in-tree skip
            dirs[:] = [
                d
                for d in dirs
                if d not in {"__pycache__", "node_modules"} and not d.startswith(".git")
            ]

            target_dir = dst / rel
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                continue

            for fname in files:
                src_file = root_path / fname
                rel_file = src_file.relative_to(src)
                if rel_file.parts and rel_file.parts[0] in skip_top:
                    continue
                if "__pycache__" in rel_file.parts:
                    continue
                try:
                    (dst / rel_file).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dst / rel_file)
                except (PermissionError, FileNotFoundError, OSError):
                    # ボリューム配下や一時ファイルなど、読めない/消えるものはスキップ
                    continue

    def add_initial_files(self, initial_files: Dict[str, str] | None):
        """初期ファイルを task_dir に配置します。"""
        if not initial_files:
            return
        for name, content in initial_files.items():
            (self.task_dir / name).write_text(content, encoding='utf-8')

    def add_zip_file(self, zip_file: UploadFile):
        """アップロードされた ZIP ファイルを task_dir に展開します。"""
        ExecutorUtil.extract_zip_to_dir(zip_file, self.task_dir)

    def add_files_from_path(self, src_path: pathlib.Path):
        """src_path のファイルを task_dir にコピーします。"""
        if src_path.is_file():
            shutil.copy(src_path, self.task_dir / src_path.name)
        elif src_path.is_dir():
            for item in src_path.rglob('*'):
                if item.is_file():
                    dest = self.task_dir / item.relative_to(src_path)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(item, dest)

    def launch_container(self, command: Union[str, Sequence[str]] = "", volumes: list = [], env: dict = {}, detach: bool = True) -> Container:
        """
        コンテナを起動し、task_id を返します。
        volumes: [(ホストパス, コンテナパス, モード), ...] のリスト
        """
        params = {
            "service": self.compose_config.service_name,
            "detach": detach,
            # "remove": True, # 終了時に自動削除
            "tty": False,   # ★明示的に False を指定（あるいは省略）
        }
        
        if command:
            # 自然言語プロンプトは空白を含むため、呼び出し側で配列にして渡された場合はそのまま使う。
            # 文字列で渡された場合のみ shlex.split で分解する。
            if isinstance(command, str):
                params["command"] = shlex.split(command)
            else:
                params["command"] = list(command)
        if volumes:
            params["volumes"] = volumes
        if env:
            params["envs"] = env

        # コンテナを起動（Container オブジェクトが返る）
        container = self.docker.compose.run(**params)

        if not container or isinstance(container, str):
            raise RuntimeError("Failed to start container as an object")

        return cast(Container, container) # 明示的に Container 型として返す


    async def run(
            self,
            background_tasks: BackgroundTasks | None,
            command: Union[str, Sequence[str]],
            volumes: list = [], env: dict = {},
            timeout: int = 300,
            detach: bool = True
        ) -> str:
        
        # 1. 既存の実行を確認（多重実行防止）
        task = TaskManager.get_task(self.task_id)
        
        if task and task.status == "running":
            raise RuntimeError(f"Task {self.task_id} is already running")           
        
        # 2. 環境変数からコマンドを生成
        """ComposeRunner を使ってコマンドを実行し、container_id を返します。"""
        volumes = [(str(self.task_dir), "/workspace", "rw")]

        # 3. docker compose 実行時の環境変数を確定
        # NOTE:
        # - docker compose の ${VAR} 展開は「composeコマンド実行時の環境」に依存する。
        # - Supervisor(ホスト)の環境変数（例: LLM_BASE_URL=http://localhost:4000）をそのまま引き継ぐと、
        #   コンテナ内では localhost が別物になるため接続エラーになりやすい。
        # - そこで composeプロジェクト配下の .env（例: images/cline-image/.env）を読み取り、
        #   compose.run の envs として明示的に渡して優先させる。
        compose_env: Dict[str, str] = {}
        try:
            env_path = pathlib.Path(self.compose_config.project_directory) / ".env"
            if env_path.exists() and env_path.is_file():
                values = dotenv_values(str(env_path))
                compose_env = {k: v for k, v in values.items() if isinstance(k, str) and isinstance(v, str)}
        except Exception as e:
            logger.warning(f"Failed to load compose env file: {e}")

        # composeプロジェクト配下の .env は「コンテナ内から見える値（例: litellm:4000）」を持つ。
        # 一方で呼び出し元（Supervisor/CLI）環境はホスト向け（例: localhost:4000）になりがち。
        # そのため、呼び出し元が loopback を指定している場合は .env 側を優先する。
        merged_env = {**compose_env, **(env or {})}
        base_url = merged_env.get("LLM_BASE_URL")
        if isinstance(base_url, str) and self._is_loopback_base_url(base_url):
            compose_base_url = compose_env.get("LLM_BASE_URL")
            if isinstance(compose_base_url, str) and compose_base_url:
                merged_env["LLM_BASE_URL"] = compose_base_url

        # 4. コンテナ起動（self 内のメソッドを呼ぶ）
        container = self.launch_container(
            command=command,
            volumes=volumes,
            env=merged_env,
            detach=detach,
        )
        if not container:
            raise RuntimeError("Failed to launch container")

        # 4. ステータス更新（Pydanticモデルを使用）
        task_status = TaskStatus(
            task_id=self.task_id,
            status="running",
            created_at=datetime.now(),
            container_id=container.id,
        )
        TaskManager.upsert_task(self.task_id, task_status)

        # 5. 監視開始
        
        if background_tasks:
            # FastAPI経由: レスポンス返却後に実行
            background_tasks.add_task(self.monitor_container, self.task_id, container, self.task_dir, timeout)
        else:
            # CLIなど: イベントループでタスクを作成
            # 💡 ループ内でタスクへの参照を保持しておくと、ガベージコレクションによる消失を防げます
            monitor_coro = self.monitor_container(self.task_id, container, self.task_dir, timeout)
            task = asyncio.create_task(monitor_coro)
            
            # CLIで --detach が指定されていない場合は、呼び出し元でこのタスクの終了を待つ設計にすると親切です
            # (現在は create_task なので、この run メソッド自体は即座に task_id を返します)

        return self.task_id


    # --- 内部ロジック ---

    async def monitor_container(self, task_id: str, container: Container, task_dir: pathlib.Path, timeout: int):
        # debug用: container設定/引数は秘匿情報(ENV)を含みうるため、デフォルトでは出さない。
        if os.getenv("AI_PLATFORM_DEBUG_CONTAINER") == "1":
            try:
                cfg = getattr(container, "config", None)
                args = getattr(container, "args", None)

                safe_env = None
                env_list = getattr(cfg, "env", None) if cfg is not None else None
                if isinstance(env_list, list):
                    safe_env = []
                    for item in env_list:
                        if not isinstance(item, str) or "=" not in item:
                            safe_env.append(item)
                            continue
                        key, value = item.split("=", 1)
                        upper = key.upper()
                        if any(k in upper for k in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
                            safe_env.append(f"{key}=***")
                        else:
                            safe_env.append(item)

                logger.debug(
                    "container.debug id=%s image=%s cmd=%s entrypoint=%s env=%s",
                    getattr(container, "id", None),
                    getattr(cfg, "image", None) if cfg is not None else None,
                    getattr(cfg, "cmd", None) if cfg is not None else None,
                    getattr(cfg, "entrypoint", None) if cfg is not None else None,
                    safe_env,
                )
                logger.debug("container.args=%s", args)
            except Exception:
                # デバッグログの失敗で本処理を落とさない
                pass
        try:
            start_time = asyncio.get_event_loop().time()
            while True:
                # reload() で最新の状態（state）を同期
                container.reload()
                # debug用
                # print(f"Monitoring container {container.id[:12]}: status={container.state.status}, elapsed={int(asyncio.get_event_loop().time() - start_time)}s")
                # whales のコンテナ状態チェック
                if container.state.status == 'exited':
                    break
                
                if (asyncio.get_event_loop().time() - start_time) > timeout:
                    container.kill()
                    task = TaskManager.get_task(task_id)
                    if task:
                        TaskManager.upsert_task(task_id, TaskStatus(
                            task_id=task_id,
                            status="failed",
                            created_at=task.created_at,
                            container_id=container.id,
                            stderr=f"Task timed out after {timeout} seconds"
                        ))
                    return
                await asyncio.sleep(1)

            # 終了コードの取得
            exit_code = container.state.exit_code
            
            # ログ取得 (whales では直接 logs() が呼べ、文字列で返ります)
            out_logs = container.logs()
            
            artifacts = [str(f.relative_to(task_dir)) for f in task_dir.glob("**/*") if f.is_file()]
            task = TaskManager.get_task(task_id)
            if task:
                task.status = "completed" if exit_code == 0 else "failed"
                task.stdout = out_logs
                task.artifacts = artifacts
                TaskManager.upsert_task(task_id, task)

        except Exception as e:
            task = TaskManager.get_task(task_id)
            if task:
                TaskManager.upsert_task(task_id, TaskStatus(
                    task_id=task_id,
                    status="failed",
                    created_at=task.created_at,
                    container_id=container.id,
                    stderr=f"Monitor Error: {str(e)}"
                ))
        finally:
            # 既に remove=True で起動しているが、念のため
            try: container.remove(force=True)
            except: pass
            
    @classmethod
    async def create_and_run(
        cls, 
        compose_config: ComposeConfig,
        background_tasks: BackgroundTasks | None,
        prompt: str,
        initial_files: Optional[Dict[str, str]] = None,
        zip_file: Optional[UploadFile] = None,
        source_path: Optional[pathlib.Path] = None,
        source_paths: Optional[Sequence[pathlib.Path]] = None,
        task_id: Optional[str] = None,
        timeout: int = 300,
        detach: bool = True,
    ) -> str:
        """
        インスタンス生成からコンテナ起動までを一括で行うエントリーポイント
        """
        # 1. Runnerの準備（プロジェクトパス等は環境変数から取得）
        runner = cls(
            task_id=task_id, 
            compose_config=compose_config
        )

        runner.prepare_workspace(
            initial_files=initial_files,
            zip_file=zip_file,
            source_path=source_path,
            source_paths=source_paths,
        )        # 2. ファイルの配置（ZIPまたは初期ファイル）

        # 3. コマンドと実行設定
        command_base = compose_config.compose_command
        command = shlex.split(command_base)
        if prompt:
            command.append(prompt)
        
        # 4. 実行開始（内部で launch_container と monitor_container を呼び出す）
            # runner.run() は以前実装した「ステータス更新と監視開始」を行うメソッドです
        return await runner.run(background_tasks, command, timeout=timeout, detach=detach)

# --- ステータス取得の修正 ---
    @classmethod
    async def get_status(cls, task_id: str, tail: int | None = 200) -> TaskStatus:
        task = TaskManager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if task.status == "running" and task.container_id:
            try:
                # whales を使って実行中のコンテナからログを取得
                # 戻り値は結合されたログの文字列です
                if tail is None:
                    logs = whales.container.logs(task.container_id)
                else:
                    logs = whales.container.logs(task.container_id, tail=tail)
                if isinstance(logs, str):
                    logs_str = logs
                else:
                    # Convert iterable of (stream, bytes) to string
                    logs_str = "".join(
                        b.decode("utf-8", errors="replace") if isinstance(b, bytes) else str(b)
                        for _, b in logs
                    )
                return TaskStatus(**task.model_dump(exclude={"stdout"}), stdout=logs_str)
            except Exception as e:
                return TaskStatus(**task.model_dump(exclude={"stderr"}), stderr=f"Log fetch failed: {e}")

        return task

    # --- キャンセルの修正 ---
    @classmethod
    async def cancel_task(cls, task_id: str):
        task = TaskManager.get_task(task_id)
        if task and task.status == "running" and task.container_id:
            try:
                # whales で強制終了
                whales.container.kill(task.container_id)
                TaskManager.upsert_task(task_id, TaskStatus(
                    task_id=task_id,
                    status="cancelled",
                    created_at=task.created_at,
                    container_id=task.container_id,
                    stderr=task.stderr
                ))
                return {"message": f"Task {task_id} cancelled."}
            except Exception as e:
                return {"message": f"Cancel failed: {str(e)}"}
        return {"message": "Task not found or not running."}
    
    @classmethod
    async def download_artifacts_zip(cls, task_id: str):
        """タスクの作業用ディレクトリをZIP化して返します。"""
        task_dir =  TaskManager.get_projects_root() / task_id
        if not task_dir.exists() or not task_dir.is_dir():
            raise HTTPException(status_code=404, detail="Artifacts directory not found")

        # 実行中は結果が不安定になり得るので、原則 completed のみ許可
        task = TaskManager.get_task(task_id)
        if task and task.status not in ("completed", "failed"):
            raise HTTPException(status_code=409, detail=f"Task is {task.status}, artifacts may not be ready for download")

        # 一時ファイルへZIPを作成し、FileResponseで返す（レスポンス完了後に削除）
        tmp = tempfile.NamedTemporaryFile(prefix=f"{task_id}-", suffix=".zip", delete=False)
        tmp_path = pathlib.Path(tmp.name)
        tmp.close()

        try:
            ExecutorUtil.make_zip_from_dir(task_dir, tmp_path)
        except Exception:
            ExecutorUtil.cleanup_file(str(tmp_path))
            raise

        filename = f"{task_id}.zip"
        return FileResponse(
            path=str(tmp_path),
            media_type="application/zip",
            filename=filename,
            background=BackgroundTask(ExecutorUtil.cleanup_file, str(tmp_path)),
        )


