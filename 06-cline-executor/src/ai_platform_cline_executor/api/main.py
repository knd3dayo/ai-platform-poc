from typing import Dict, Optional
import os
import asyncio
import zipfile
from contextlib import asynccontextmanager

from fastapi import UploadFile, File, Form, FastAPI, HTTPException, BackgroundTasks
from dotenv import load_dotenv

from ..core.runner import ComposeRunner, docker_client
from ..core.model import ClineRequest, TaskStatus


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
    containers = docker_client.containers.list(filters={"label": "managed_by=executor-service"})
    for c in containers:
        try:
            c.remove(force=True)
            print(f"Removed container {c.id}")
        except Exception as e:
            print(f"Failed to remove container {c.id}: {e}")

# lifespan を指定してアプリを初期化
app = FastAPI(title="Cline Executor Service", lifespan=lifespan)

# --- API エンドポイント ---

@app.post("/execute", response_model=Dict[str, str])
async def execute_cline(
    request: ClineRequest, background_tasks: BackgroundTasks, task_id: Optional[str] = None):
    try:
        # ロジックを完全に委譲
        new_task_id = await ComposeRunner.create_and_run(
            background_tasks=background_tasks,
            prompt=request.prompt,
            initial_files=request.initial_files,
            task_id=task_id,
            timeout=request.timeout
        )
        return {"task_id": new_task_id}
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
        new_task_id = await ComposeRunner.create_and_run(
            background_tasks=background_tasks,
            prompt=prompt,
            zip_file=file,
            task_id=task_id,
            timeout=timeout
        )
        return {"task_id": new_task_id}

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

def main():
    load_dotenv()

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

if __name__ == "__main__":
    main()
