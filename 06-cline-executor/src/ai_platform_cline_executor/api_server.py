import os
import uuid
import pathlib
import docker
import asyncio
import zipfile
import io
from fastapi import UploadFile, File, Form
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Dict, Optional, List
from datetime import datetime
from dotenv import load_dotenv

# --- 設定：環境に合わせて調整 ---
HOST_PROJECTS_ROOT = os.getenv("HOST_PROJECTS_ROOT", "/home/user/ai-platform/data/projects")
CLINE_IMAGE = "cline-executor-image"
NETWORK_NAME = "ai_platform_net"

load_dotenv()
app = FastAPI(title="Cline Executor Service")
client = docker.from_env()

# タスク管理ストア（本番はRedis推奨）
tasks: Dict[str, dict] = {}

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

# --- 内部ロジック ---

async def monitor_container(task_id: str, container, task_dir: pathlib.Path, timeout: int):
    try:
        # 完了を待機
        start_time = asyncio.get_event_loop().time()
        while True:
            container.reload()
            if container.status == 'exited':
                break
            if (asyncio.get_event_loop().time() - start_time) > timeout:
                container.kill()
                tasks[task_id].update({"status": "timeout"})
                return
            await asyncio.sleep(1)

        # 実行結果の回収
        res = container.wait()
# ログを個別に取得して print してみる
        out_logs = container.logs(stdout=True, stderr=False).decode('utf-8')
        err_logs = container.logs(stdout=False, stderr=True).decode('utf-8')
        
        print(f"DEBUG [{task_id}] ExitCode: {res['StatusCode']}")
        print(f"DEBUG [{task_id}] STDOUT: {out_logs}")
        print(f"DEBUG [{task_id}] STDERR: {err_logs}")

        # 成果物（ファイル名）のスキャン
        artifacts = [str(f.relative_to(task_dir)) for f in task_dir.glob("**/*") if f.is_file()]

        tasks[task_id].update({
            "status": "completed" if res["StatusCode"] == 0 else "failed",
            "stdout": out_logs,
            "stderr": err_logs,
            "artifacts": artifacts
        })
    except Exception as e:
        tasks[task_id].update({"status": "failed", "stderr": str(e)})
    finally:
        try:
            container.remove(force=True)
        except:
            pass

# --- API エンドポイント ---

@app.post("/execute", response_model=Dict[str, str])
async def execute_cline(request: ClineRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    task_dir = pathlib.Path(HOST_PROJECTS_ROOT) / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    # 1. 初期ファイルの配置
    if request.initial_files:
        for name, content in request.initial_files.items():
            (task_dir / name).write_text(content, encoding='utf-8')

    try:
        # 2. コンテナの起動（成功した docker run の条件を再現）
        container = client.containers.run(
            image=CLINE_IMAGE,
            command=f"cline -y '{request.prompt}'",
            # ネットワークを繋いで LLM と通信可能にする
            network=NETWORK_NAME,
            # ホストのプロジェクトディレクトリをマウント
            volumes={
                str(task_dir): {'bind': '/workspace', 'mode': 'rw'}
            },
            working_dir="/workspace",
            detach=True,
            labels={"managed_by": "executor-service", "task_id": task_id},
            # 認証情報を環境変数で渡す（ホストの環境変数をリレー）
            environment= { 
                "CLINE_API_PROVIDER": os.getenv("CLINE_API_PROVIDER", ""),
                "CLINE_API_KEY": os.getenv("CLINE_API_KEY", ""),
                "CLINE_API_BASE_URL": os.getenv("CLINE_API_BASE_URL", ""),
                "CLINE_MODEL_ID": os.getenv("CLINE_MODEL_ID", ""),
            }
        )

        tasks[task_id] = {
            "task_id": task_id,
            "status": "running",
            "created_at": datetime.now()
        }

        # バックグラウンドで監視開始
        background_tasks.add_task(monitor_container, task_id, container, task_dir, request.timeout)
        
        return {"task_id": task_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/execute/zip")
async def execute_cline_zip(
    background_tasks: BackgroundTasks,
    prompt: str = Form(...),              # JSONではなくFormで受け取る
    file: UploadFile = File(...),         # ZIPファイル
    timeout: int = Form(300)
):
    task_id = str(uuid.uuid4())
    task_dir = pathlib.Path(HOST_PROJECTS_ROOT) / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. アップロードされたZIPを展開
        contents = await file.read()
        with zipfile.ZipFile(io.BytesIO(contents)) as zip_ref:
            # セキュリティチェック（Zip Slip 対策）
            for member in zip_ref.namelist():
                target_path = os.path.normpath(os.path.join(task_dir, member))
                if not target_path.startswith(os.path.abspath(task_dir)):
                    raise HTTPException(status_code=400, detail="不正なファイルパスがZIPに含まれています")
            
            zip_ref.extractall(task_dir)

        # 2. コンテナの起動（基本ロジックは前回と同じ）
        container = client.containers.run(
            image=CLINE_IMAGE,
            command=f"cline -y '{prompt}'",
            network=NETWORK_NAME,
            volumes={
                str(task_dir): {'bind': '/workspace', 'mode': 'rw'}
            },
            environment={
                "CLINE_API_PROVIDER": os.getenv("CLINE_API_PROVIDER", ""),
                "CLINE_API_KEY": os.getenv("CLINE_API_KEY", ""),
                "CLINE_API_BASE_URL": os.getenv("CLINE_API_BASE_URL", ""),
                "CLINE_MODEL_ID": os.getenv("CLINE_MODEL_ID", ""),
            },
            working_dir="/workspace",
            detach=True,
            labels={"managed_by": "executor-service", "task_id": task_id}
        )

        tasks[task_id] = {
            "task_id": task_id,
            "status": "running",
            "created_at": datetime.now(),
            "artifacts": []
        }

        background_tasks.add_task(monitor_container, task_id, container, task_dir, timeout)
        
        return {"task_id": task_id}

    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="無効なZIPファイルです")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.get("/status/{task_id}", response_model=TaskStatus)
async def get_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks[task_id]

@app.delete("/cancel/{task_id}")
async def cancel_task(task_id: str):
    """実行中のタスクを強制終了します"""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task["status"] == "running":
        try:
            container = client.containers.get(task["container_id"])
            container.kill()
            task["status"] = "cancelled"
            return {"message": f"Task {task_id} has been cancelled."}
        except Exception as e:
            return {"message": f"Task already finished or error: {str(e)}"}
    
    return {"message": f"Task is in {task['status']} state and cannot be cancelled."}

@app.on_event("shutdown")
async def shutdown_event():
    """API終了時に、動いている全コンテナを掃除する"""
    print("Cleaning up containers before shutdown...")
    containers = client.containers.list(filters={"label": "managed_by=executor-service"})
    for c in containers:
        try:
            c.remove(force=True)
            print(f"Removed container {c.id}")
        except:
            pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
