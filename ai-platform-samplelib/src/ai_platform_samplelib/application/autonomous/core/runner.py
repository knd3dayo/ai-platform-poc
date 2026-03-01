from typing import Dict, Optional, cast, ClassVar
from datetime import datetime
import os
import uuid
import pathlib
import tempfile
import asyncio
import json
import shlex
from datetime import datetime

from fastapi import UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from python_on_whales import docker as whales, Container, DockerClient
from ..model.models import TaskStatus, ComposeConfig
from .utils import ExecutorUtil
from .task_manager import TaskManager


class ComposeRunner:
    """docker-compose.yml から設定を動的に読み取り、コンテナを実行するクラス"""

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

    def add_initial_files(self, initial_files: Dict[str, str] | None):
        """初期ファイルを task_dir に配置します。"""
        if not initial_files:
            return
        for name, content in initial_files.items():
            (self.task_dir / name).write_text(content, encoding='utf-8')

    def add_zip_file(self, zip_file: UploadFile):
        """アップロードされた ZIP ファイルを task_dir に展開します。"""
        ExecutorUtil.extract_zip_to_dir(zip_file, self.task_dir)

    def launch_container(self, command: str = "", volumes: list = [], env: dict = {}):
        """
        コンテナを起動し、task_id を返します。
        volumes: [(ホストパス, コンテナパス, モード), ...] のリスト
        """
        params = {
            "service": self.compose_config.service_name,
            "detach": True,
            # "remove": True, # 終了時に自動削除
            "tty": False,   # ★明示的に False を指定（あるいは省略）
        }
        
        if command:
            params["command"] = shlex.split(command)  # コマンドをリスト形式で渡す    
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
            command: str,
            volumes: list = [], env: dict = {},
            timeout: int = 300
        ) -> str:
        
        # 1. 既存の実行を確認（多重実行防止）
        task = TaskManager.get_task(self.task_id)
        
        if task and task.status == "running":
            raise RuntimeError(f"Task {self.task_id} is already running")           
        
        # 2. 環境変数からコマンドを生成
        """ComposeRunner を使ってコマンドを実行し、container_id を返します。"""
        volumes = [(str(self.task_dir), "/workspace", "rw")]

        # 3. コンテナ起動（self 内のメソッドを呼ぶ）
        container = self.launch_container(
            command=command,
            volumes=volumes,
            env=env
        )
        if not container:
            raise RuntimeError("Failed to launch container")

        # 4. ステータス更新（Pydanticモデルを使用）
        TaskManager.upsert_task(self.task_id, TaskStatus(
            task_id=self.task_id,
            status="running",
            created_at=datetime.now(),
            container_id=container.id,
        ))

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
        # debug用 containerの設定内容
        print(f"container.config: {container.config}")
        print(f"container.args: {container.args}")
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
        task_id: Optional[str] = None,
        timeout: int = 300
    ) -> str:
        """
        インスタンス生成からコンテナ起動までを一括で行うエントリーポイント
        """
        # 1. Runnerの準備（プロジェクトパス等は環境変数から取得）
        runner = cls(
            task_id=task_id, 
            compose_config=compose_config
        )

        # 2. ファイルの配置（ZIPまたは初期ファイル）
        if zip_file:
            runner.add_zip_file(zip_file)
        if initial_files:
            runner.add_initial_files(initial_files)

        # 3. コマンドと実行設定
        command_base = compose_config.compose_command
        command = f"{command_base} {prompt}"
        
        # 4. 実行開始（内部で launch_container と monitor_container を呼び出す）
        # runner.run() は以前実装した「ステータス更新と監視開始」を行うメソッドです
        return await runner.run(background_tasks, command, timeout=timeout)

# --- ステータス取得の修正 ---
    @classmethod
    async def get_status(cls, task_id: str, tail: int = 200) -> TaskStatus:
        task = TaskManager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if task.status == "running" and task.container_id:
            try:
                # whales を使って実行中のコンテナからログを取得
                # 戻り値は結合されたログの文字列です
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


    @classmethod
    def save_tasks(cls):
        """現在のタスク状態をファイルに保存する"""
        with open(TaskManager.get_tasks_file_path(), "w") as f:
            data = {k: v.model_dump(mode='json') for k, v in TaskManager.get_all_tasks().items()}
            json.dump(data, f, indent=2)

    @classmethod
    def load_tasks(cls):
        """ファイルからタスク状態を復元する"""
        if TaskManager.get_tasks_file_path().exists():
            with open(TaskManager.get_tasks_file_path(), "r") as f:
                data = json.load(f)
                for k, v in data.items():
                    TaskManager.upsert_task(k, TaskStatus(**v))

    @classmethod
    def get_task(cls, task_id: str):
        """タスクIDからタスク情報を取得する"""
        task = TaskManager.get_all_tasks().get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task
    
    @classmethod
    def get_all_tasks(cls):
        """全タスクの情報を取得する"""
        return TaskManager.get_all_tasks()