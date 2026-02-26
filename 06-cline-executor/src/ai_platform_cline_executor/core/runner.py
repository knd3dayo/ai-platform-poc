from typing import Dict, Optional, List, Any, cast, Tuple
import os
import uuid
import pathlib
import tempfile
import asyncio
import json
from datetime import datetime

from fastapi import UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from python_on_whales import docker as whales, DockerClient, Container 
import docker

from .model import TaskStatus, tasks
from .utils import ExecutorUtil

# --- 設定：環境に合わせて調整 ---
HOST_PROJECTS_ROOT = os.getenv("HOST_PROJECTS_ROOT", "/home/user/ai-platform/data/projects")
CLINE_IMAGE = "cline-executor-image"
NETWORK_NAME = "ai_platform_net"
TASKS_FILE = pathlib.Path(HOST_PROJECTS_ROOT) / "tasks_db.json"

docker_client = docker.from_env()

class ComposeRunner:
    """docker-compose.yml から設定を動的に読み取り、Cline を実行するクラス"""
    def __init__(self, task_id: Optional[str] = None, project_directory: str = ".", file: str = "docker-compose.yml"):
        self.project_directory = os.path.abspath(project_directory)
        self.compose_file = os.path.join(self.project_directory, file)
        self.task_id = task_id or str(uuid.uuid4())  # タスクごとに一意のIDを生成
        self.task_dir = pathlib.Path(HOST_PROJECTS_ROOT) / self.task_id
        self.task_dir.mkdir(parents=True, exist_ok=True)

        # クライアントは一度作れば使い回せます
        self.docker = DockerClient(
            compose_files=[self.compose_file],
            compose_project_directory=self.project_directory,
            compose_project_name="executor_service"
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

    def launch_container(self, service_name: str, command: str = "", volumes: list = [], env: dict = {}):
        """
        コンテナを起動し、task_id を返します。
        volumes: [(ホストパス, コンテナパス, モード), ...] のリスト
        """
        params = {
            "service": service_name,
            "detach": True,
            "remove": True, # 終了時に自動削除
        }
        
        if command:
            params["command"] = command.split() if isinstance(command, str) else command
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
        if self.task_id in tasks and tasks[self.task_id].status == "running":
            raise RuntimeError(f"Task {self.task_id} is already running")           
        
        # 2. 環境変数からコマンドを生成
        """ComposeRunner を使ってコマンドを実行し、container_id を返します。"""
        volumes = [(str(self.task_dir), "/workspace", "rw")]

        # 3. コンテナ起動（self 内のメソッドを呼ぶ）
        container = self.launch_container(
            service_name="executor", # docker-compose.yml 内のサービス名
            command=command,
            volumes=volumes,
            env=env
        )
        if not container:
            raise RuntimeError("Failed to launch container")

        # 4. ステータス更新（Pydanticモデルを使用）
        tasks[self.task_id] = TaskStatus(
            task_id=self.task_id,
            status="running",
            created_at=datetime.now(),
            container_id=container.id,
        )

        # 5. 監視開始（非同期タスクとして実行） 
        if background_tasks:
            background_tasks.add_task(self.monitor_container, self.task_id, container, self.task_dir, timeout)
        return self.task_id


    # --- 内部ロジック ---

    async def monitor_container(self, task_id: str, container, task_dir: pathlib.Path, timeout: int):
        try:
            # 完了を待機
            start_time = asyncio.get_event_loop().time()
            while True:
                container.reload()
                if container.status == 'exited':
                    break
                if (asyncio.get_event_loop().time() - start_time) > timeout:
                    container.kill()
                    # timeout 時点のログを可能なら保存
                    try:
                        out_logs, err_logs = ExecutorUtil.get_container_logs(container, tail=1000)
                        tasks[task_id].stdout = out_logs
                        tasks[task_id].stderr = err_logs
                    except Exception:
                        pass
                    tasks[task_id].status = "timeout"
                    return
                await asyncio.sleep(1)

            # 実行結果の回収
            res = container.wait()
            # ログを個別に取得して print してみる
            out_logs, err_logs = ExecutorUtil.get_container_logs(container, tail=1000)
            
            print(f"DEBUG [{task_id}] ExitCode: {res['StatusCode']}")
            print(f"DEBUG [{task_id}] STDOUT: {out_logs}")
            print(f"DEBUG [{task_id}] STDERR: {err_logs}")

            # 成果物（ファイル名）のスキャン
            artifacts = [str(f.relative_to(task_dir)) for f in task_dir.glob("**/*") if f.is_file()]

            tasks[task_id].status = "completed" if res["StatusCode"] == 0 else "failed"
            tasks[task_id].stdout = out_logs
            tasks[task_id].stderr = err_logs
            tasks[task_id].artifacts = artifacts
        except Exception as e:
            tasks[task_id].status = "failed"
            tasks[task_id].stderr = str(e)
        finally:
            try:
                container.remove(force=True)
            except:
                pass

    @classmethod
    async def create_and_run(
        cls, 
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
        project_dir = os.getenv("COMPOSE_PROJECT_DIRECTORY", ".")
        compose_file = os.getenv("COMPOSE_FILE", "docker-compose.yml")
        
        runner = cls(
            task_id=task_id, 
            project_directory=project_dir, 
            file=compose_file
        )

        # 2. ファイルの配置（ZIPまたは初期ファイル）
        if zip_file:
            runner.add_zip_file(zip_file)
        if initial_files:
            runner.add_initial_files(initial_files)

        # 3. コマンドと実行設定
        command_base = os.getenv('COMMAND', 'cline -y')
        command = f"{command_base} '{prompt}'"
        
        # 4. 実行開始（内部で launch_container と monitor_container を呼び出す）
        # runner.run() は以前実装した「ステータス更新と監視開始」を行うメソッドです
        return await runner.run(background_tasks, command, timeout=timeout)

    @classmethod
    async def get_status(cls, task_id: str, tail: int = 200) -> TaskStatus:
        """
        指定したタスクの状態を取得します。
        実行中の場合は Docker コンテナから最新のログを取得してマージしたモデルを返します。
        """
        if task_id not in tasks:
            raise HTTPException(status_code=404, detail="Task not found")

        task = tasks[task_id]

        # 実行中の場合のみ、最新のログを動的に取得して反映したモデルを作る
        if task.status == "running" and task.container_id:
            try:
                # Docker コンテナからログを取得
                container = docker_client.containers.get(task.container_id)
                stdout, stderr = ExecutorUtil.get_container_logs(container, tail=tail)

                # 既存のデータをベースに、最新ログを上書きした新しい TaskStatus を作成して返す
                # ※ tasks[task_id] 自体は更新せず、レスポンス用の一時的なモデルを作る
                return TaskStatus(
                    **task.model_dump(exclude={"stdout", "stderr"}), 
                    stdout=stdout, 
                    stderr=stderr
                )
            except Exception as e:
                # ログ取得に失敗した場合でも、エラー情報を乗せた TaskStatus を返す
                return TaskStatus(
                    **task.model_dump(exclude={"stderr"}), 
                    stderr=f"Failed to fetch running logs: {e}"
                )

        # 完了済み、またはエラー済みの場合は保存されているモデルをそのまま返す
        return task

    @classmethod
    async def download_artifacts_zip(cls, task_id: str):
        """タスクの作業用ディレクトリをZIP化して返します。"""
        task_dir = pathlib.Path(HOST_PROJECTS_ROOT) / task_id
        if not task_dir.exists() or not task_dir.is_dir():
            raise HTTPException(status_code=404, detail="Artifacts directory not found")

        # 実行中は結果が不安定になり得るので、原則 completed のみ許可
        task = tasks.get(task_id)
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
    async def cancel_task(cls, task_id: str):
        """実行中のタスクを強制終了します"""
        task = tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        if task.status == "running":
            try:
                container_id = task.container_id
                if not container_id:
                    return {"message": "container_id not found for this task"}

                container = docker_client.containers.get(container_id)
                # kill 前に直近ログを取得しておく（取得不可でも握りつぶす）
                try:
                    stdout, stderr = ExecutorUtil.get_container_logs(container, tail=200)
                    task.stdout = stdout
                    task.stderr = stderr
                except Exception:
                    pass

                container.kill()
                task.status = "cancelled"
                return {"message": f"Task {task_id} has been cancelled."}
            except Exception as e:
                return {"message": f"Task already finished or error: {str(e)}"}
        
        return {"message": f"Task is in {task.status} state and cannot be cancelled."}

    @classmethod
    def save_tasks(cls):
        """現在のタスク状態をファイルに保存する"""
        from .model import tasks # 循環参照を避けるためメソッド内でインポート
        with open(TASKS_FILE, "w") as f:
            data = {k: v.model_dump(mode='json') for k, v in tasks.items()}
            json.dump(data, f, indent=2)

    @classmethod
    def load_tasks(cls):
        """ファイルからタスク状態を復元する"""
        from .model import tasks, TaskStatus
        if TASKS_FILE.exists():
            with open(TASKS_FILE, "r") as f:
                data = json.load(f)
                for k, v in data.items():
                    tasks[k] = TaskStatus(**v)