import uuid
import docker
import asyncio
import os
import pathlib
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Dict, Optional
from datetime import datetime

# ホスト側（WSL2側）のプロジェクト保存ルート
# Difyの構成に合わせて、../../data/dify/projects に保存する設定
HOST_PROJECTS_ROOT = os.getenv("HOST_PROJECTS_ROOT", "/home/user/ai-platform/data/dify/projects")

app = FastAPI(title="Secure Code Executor API")
client = docker.from_env()

# 実行中のタスクを管理するメモリ上のストア
# 本格運用の場合はここを Redis に置き換えると、API再起動に強くなります
tasks: Dict[str, dict] = {}

class CodeRequest(BaseModel):
    # Pydantic v2 では `example=` は非推奨/未定義（型スタブでも弾かれる）なため、
    # OpenAPI schema 用の例は `examples=` を使う。
    code: str = Field(..., examples=["print('Hello World')"])
    timeout: int = Field(default=30, ge=1, le=300)

class TaskStatus(BaseModel):
    task_id: str
    status: str  # running, completed, failed, cancelled, timeout
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    exit_code: Optional[int] = None
    created_at: datetime

# --- 内部ユーティリティ ---

async def monitor_container(task_id: str, container, timeout: int):
    """コンテナの終了を監視し、結果を回収するバックグラウンドタスク"""
    try:
        # 非同期で待機（ブロックせずにループで確認）
        start_time = asyncio.get_event_loop().time()
        while True:
            container.reload()
            if container.status == 'exited':
                break
            
            # タイムアウト判定
            if (asyncio.get_event_loop().time() - start_time) > timeout:
                container.kill()
                tasks[task_id].update({
                    "status": "timeout",
                    "stderr": f"Execution exceeded timeout of {timeout}s"
                })
                return

            await asyncio.sleep(0.5)

        # 結果の回収
        res = container.wait()
        tasks[task_id].update({
            "status": "completed" if res["StatusCode"] == 0 else "failed",
            "stdout": container.logs(stdout=True, stderr=False).decode('utf-8'),
            "stderr": container.logs(stdout=False, stderr=True).decode('utf-8'),
            "exit_code": res["StatusCode"]
        })

    except Exception as e:
        tasks[task_id].update({"status": "failed", "stderr": str(e)})
    finally:
        # コンテナを削除してリソースを解放
        try:
            container.remove(force=True)
        except:
            pass

# --- API エンドポイント ---

@app.post("/execute")
async def execute_project(request: CodeRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    # 1. ホスト側にプロジェクトディレクトリを作成
    project_path = pathlib.Path(HOST_PROJECTS_ROOT) / task_id
    project_path.mkdir(parents=True, exist_ok=True)

    # 2. コードをファイルとして保存（エージェントが複数ファイルを作る際もここに追加可能）
    code_file = project_path / "main.py"
    with open(code_file, "w") as f:
        f.write(request.code)

    """コード実行を開始し、task_id を返します"""
    task_id = str(uuid.uuid4())
    try:
        # 3. コンテナ起動時にボリュームをマウント
        container = client.containers.run(
            image="python:3.11-slim",
            command=["python3", "/workspace/main.py"], # ファイルを実行
            volumes={
                str(project_path): {
                    'bind': '/workspace',
                    'mode': 'rw'
                }
            },
            working_dir="/workspace",
            network_disabled=True,
            mem_limit="128m",
            detach=True,
            labels={"managed_by": "executor-service", "task_id": task_id}
        )

        tasks[task_id] = {
            "task_id": task_id,
            "status": "running",
            "container_id": container.id,
            "created_at": datetime.now(),
            "stdout": "",
            "stderr": "",
            "exit_code": None
        }

        # 監視タスクをバックグラウンドで開始
        background_tasks.add_task(monitor_container, task_id, container, request.timeout)
        
        return {"task_id": task_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start container: {str(e)}")

@app.get("/status/{task_id}", response_model=TaskStatus)
async def get_status(task_id: str):
    """タスクの状態と結果を取得します"""
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