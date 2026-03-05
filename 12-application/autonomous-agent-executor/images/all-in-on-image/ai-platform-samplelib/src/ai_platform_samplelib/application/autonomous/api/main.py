from typing import Dict, Optional
import os
import asyncio
import zipfile
from contextlib import asynccontextmanager
from python_on_whales import docker as whales  # これを追加
from fastapi import UploadFile, File, Form, FastAPI, HTTPException, BackgroundTasks

from ..core.runner import ComposeRunner
from ..model.models import AutonomousAgentRequest, TaskStatus, ComposeConfig


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
    """管理対象のコンテナを全削除する同期関数 (python-on-whales 版)"""
    print("Searching for orphaned containers...")
    
    # filters のキーは 'label' (単数形) です。
    # ※ このフィルタを機能させるには docker-compose.yml に labels: managed_by=executor-service が必要です
    try:
        containers = whales.container.list(filters={"label": "managed_by=executor-service"})
        for c in containers:
            try:
                # whales のコンテナオブジェクトは直接 .remove() を持っています
                c.remove(force=True)
                print(f"✅ Removed container {c.id[:12]}")
            except Exception as e:
                print(f"❌ Failed to remove container {c.id[:12]}: {e}")
                
        if not containers:
            print("No orphaned containers found.")
            
    except Exception as e:
        print(f"Error listing containers: {e}")
        
# lifespan を指定してアプリを初期化
app = FastAPI(title="Autonomous Agent Executor Service", lifespan=lifespan)


# --- API エンドポイント ---

@app.post("/execute", response_model=Dict[str, str])
async def execute_autonomous_agent(
    request: AutonomousAgentRequest, background_tasks: BackgroundTasks, task_id: Optional[str] = None):
    try:
        # ロジックを完全に委譲
        compose_config = ComposeConfig.from_env()
        
        new_task_id = await ComposeRunner.create_and_run(
            background_tasks=background_tasks,
            compose_config=compose_config,
            prompt=request.prompt,
            # initial_filesをtask_dirに保存する。
            initial_files=request.initial_files,
            task_id=task_id,
            timeout=request.timeout
        )
        return {"task_id": new_task_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/execute/zip")
async def execute_autonomous_agent_zip(
    background_tasks: BackgroundTasks,
    task_id: Optional[str] = None,
    prompt: str = Form(...),              # JSONではなくFormで受け取る
    file: UploadFile = File(...),         # ZIPファイル
    timeout: int = Form(300)
):
    try:
        compose_config = ComposeConfig.from_env()
        new_task_id = await ComposeRunner.create_and_run(
            compose_config=compose_config,
            background_tasks=background_tasks,
            prompt=prompt,
            # ZIPファイルを task_dir に保存してから runner に渡す
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

    # 引数でcomposeプロジェクトディレクトリ、ファイルを指定できるようにする
    import argparse
    parser = argparse.ArgumentParser(description="Docker Compose Runner API Server")
    parser.add_argument("-p", "--port", type=int, default=7101, help="Port to run the API server on")
    # -e --env-file オプションを追加して、環境変数ファイルを指定できるようにする
    parser.add_argument("-e", "--env-file", type=str, default=".env", help="Path to the .env file for configuration")

    args = parser.parse_args()
    port = args.port
    env_file = args.env_file

    ComposeConfig.set_env_file(env_file)  # 環境変数ファイルをセット
    # ComposeConfigの内容を出力
    compose_config = ComposeConfig.from_env()
    print(f"Using Compose Config: {compose_config}")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
