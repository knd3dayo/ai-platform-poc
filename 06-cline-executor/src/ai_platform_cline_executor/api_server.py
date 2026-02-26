import os
import uuid
import pathlib
import tempfile
import docker
import asyncio
import zipfile
import io
from fastapi import UploadFile, File, Form
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field
from typing import Dict, Optional, List, Any
from datetime import datetime
from dotenv import load_dotenv
from python_on_whales import docker as whales
from python_on_whales import DockerClient
from typing import Dict, Optional, List, Any, cast, Tuple
from python_on_whales import DockerClient, Container # Container を追加
from contextlib import asynccontextmanager

load_dotenv()

# --- 設定：環境に合わせて調整 ---
HOST_PROJECTS_ROOT = os.getenv("HOST_PROJECTS_ROOT", "/home/user/ai-platform/data/projects")
CLINE_IMAGE = "cline-executor-image"
NETWORK_NAME = "ai_platform_net"

# --- Lifespan: アプリの起動と終了のライフサイクル管理 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # [Startup]: アプリ起動時の処理
    print("🚀 API Server starting up...")
    # 必要に応じて、起動時に死んでいるコンテナを掃除したり、
    # 既存のタスクをスキャンするロジックをここに書けます。
    
    yield  # ここでアプリが稼働する

    # [Shutdown]: アプリ終了時の処理
    print("🧹 API Server shutting down. Cleaning up containers...")
    try:
        # 非同期で掃除を実行（念のため同期ライブラリの呼び出しを考慮）
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, cleanup_orphaned_containers)
    except Exception as e:
        print(f"Error during cleanup: {e}")

def cleanup_orphaned_containers():
    """管理対象のコンテナを全削除する同期関数"""
    # フィルタは labels={"managed_by": "executor-service"} でも可
    containers = client.containers.list(filters={"label": "managed_by=executor-service"})
    for c in containers:
        try:
            c.remove(force=True)
            print(f"Removed container {c.id}")
        except Exception as e:
            print(f"Failed to remove container {c.id}: {e}")

# lifespan を指定してアプリを初期化
app = FastAPI(title="Cline Executor Service", lifespan=lifespan)
client = docker.from_env()


# --- リクエスト/レスポンスモデル ---

class ClineRequest(BaseModel):
    prompt: str = Field(..., examples=["hello.py を修正して"])
    initial_files: Optional[Dict[str, str]] = None # 事前に配置したいファイル
    timeout: int = Field(default=300, ge=1, le=1800)

class TaskStatus(BaseModel):
    task_id: str
    status: str  # running, completed, failed, timeout
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    artifacts: Optional[List[str]] = None
    created_at: datetime
    container_id: Optional[str] = None


# タスク管理ストア（本番はRedis推奨）
tasks: Dict[str, TaskStatus] = {}


class ExecutorUtil:
    """タスクの実行と管理に関するユーティリティ関数をまとめたクラスです。"""
    @staticmethod
    def make_zip_from_dir(src_dir: pathlib.Path, zip_path: pathlib.Path) -> None:
        """ディレクトリ全体をzip化します（zip_path は上書き）。"""
        if not src_dir.exists() or not src_dir.is_dir():
            raise FileNotFoundError(f"Directory not found: {src_dir}")

        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in src_dir.rglob("*"):
                if not p.is_file():
                    continue
                # zip 内のパスは src_dir からの相対
                zf.write(p, arcname=str(p.relative_to(src_dir)))

    @staticmethod
    def cleanup_file(path: str) -> None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass

    @staticmethod
    def get_container_logs(container, tail: int = 200) -> tuple[str, str]:
        """docker コンテナの stdout/stderr を取得して (stdout, stderr) を返します。"""
        # docker SDK の tail は str/int を受け付ける
        out = container.logs(stdout=True, stderr=False, tail=tail)
        err = container.logs(stdout=False, stderr=True, tail=tail)
        return out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")

    @staticmethod
    def extract_zip_to_dir(zip_file: UploadFile, dest_dir: pathlib.Path) -> None:
        """アップロードされた ZIP ファイルを指定ディレクトリに展開します。"""
        contents = zip_file.file.read()
        with zipfile.ZipFile(io.BytesIO(contents)) as zip_ref:
            # セキュリティチェック（Zip Slip 対策）
            for member in zip_ref.namelist():
                target_path = os.path.normpath(os.path.join(dest_dir, member))
                if not target_path.startswith(os.path.abspath(dest_dir)):
                    raise HTTPException(status_code=400, detail="不正なファイルパスがZIPに含まれています")
            zip_ref.extractall(dest_dir)


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
            background_tasks: BackgroundTasks,
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
        background_tasks.add_task(self.monitor_container, self.task_id, container, self.task_dir, timeout=timeout)
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

    @staticmethod
    async def get_status(task_id: str, tail: int = 200):
        if task_id not in tasks:
            raise HTTPException(status_code=404, detail="Task not found")

        task = tasks[task_id]
        # running のときだけ、コンテナからログを都度取得してレスポンスへ反映
        if task.status == "running":
            container_id = task.container_id
            if container_id:
                try:
                    container = client.containers.get(container_id)
                    stdout, stderr = ExecutorUtil.get_container_logs(container, tail=tail)
                    # tasks を汚染せずレスポンスだけに乗せる
                    return {**task.model_dump(), "stdout": stdout, "stderr": stderr}
                except Exception as e:
                    # ログ取得に失敗しても status 自体は返す
                    return {**task.model_dump(), "stderr": f"Failed to fetch running logs: {e}"}

        return task

    @staticmethod
    async def download_artifacts_zip(task_id: str):
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

    @staticmethod
    async def cancel_task(task_id: str):
        """実行中のタスクを強制終了します"""
        task = tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        if task.status == "running":
            try:
                container_id = task.container_id
                if not container_id:
                    return {"message": "container_id not found for this task"}

                container = client.containers.get(container_id)
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



# --- API エンドポイント ---

@app.post("/execute", response_model=Dict[str, str])
async def execute_cline(
    request: ClineRequest, background_tasks: BackgroundTasks, task_id: Optional[str] = None):


    try:
        runner = ComposeRunner(task_id=task_id, project_directory=os.getenv("COMPOSE_PROJECT_DIRECTORY", "."), file=os.getenv("COMPOSE_FILE", "docker-compose.yml"))
        # 1. 初期ファイルの配置
        runner.add_initial_files(request.initial_files)
        command = f"{os.getenv('COMMAND', 'cline -y')} '{request.prompt}'"

        task_id = await runner.run(background_tasks, command, volumes=[(str(runner.task_dir), "/workspace", "rw")])
        return {"task_id": task_id}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/execute/zip")
async def execute_cline_zip(
    background_tasks: BackgroundTasks,
    task_id: Optional[str] = None,
    prompt: str = Form(...),              # JSONではなくFormで受け取る
    file: UploadFile = File(...),         # ZIPファイル
    timeout: int = Form(300)
):
    try:
        compose_project_dir = os.getenv("COMPOSE_PROJECT_DIRECTORY", ".")
        compose_file = os.getenv("COMPOSE_FILE", "docker-compose.yml")
        runner = ComposeRunner(task_id=task_id, project_directory=compose_project_dir, file=compose_file)
        # 1. アップロードされたZIPを展開
        runner.add_zip_file(file)

        volumes = [(str(runner.task_dir), "/workspace", "rw")]
        command = f"{os.getenv('COMMAND', 'cline -y')} '{prompt}'"

        task_id = await runner.run(background_tasks, command, volumes=volumes, timeout=timeout)

        return {"task_id": task_id}

    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="無効なZIPファイルです")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.get("/status/{task_id}", response_model=TaskStatus)
async def get_status(task_id: str, tail: int = 200):
    return await ComposeRunner.get_status(task_id, tail=tail)

@app.get("/artifacts/{task_id}/zip")
async def download_artifacts_zip(task_id: str):
    return await ComposeRunner.download_artifacts_zip(task_id)

@app.delete("/cancel/{task_id}")
async def cancel_task(task_id: str):
    return await ComposeRunner.cancel_task(task_id)

if __name__ == "__main__":
    # 引数でcomposeプロジェクトディレクトリ、ファイルを指定できるようにする
    import argparse
    parser = argparse.ArgumentParser(description="Docker Compose Runner API Server")
    parser.add_argument("-d", "--project-dir", type=str, default=".", help="Path to the directory containing docker-compose.yml")
    parser.add_argument("-f", "--compose-file", type=str, default="docker-compose.yml", help="Name of the docker-compose file")
    parser.add_argument("-p", "--port", type=int, default=8000, help="Port to run the API server on")

    args = parser.parse_args()
    os.environ["COMPOSE_PROJECT_DIRECTORY"] = args.project_dir
    os.environ["COMPOSE_FILE"] = args.compose_file

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=args.port)
