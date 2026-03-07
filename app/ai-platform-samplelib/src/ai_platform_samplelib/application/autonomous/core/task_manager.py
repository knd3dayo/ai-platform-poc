from typing import Optional, ClassVar, Generator
import pathlib
import json
import os, pathlib
import json
from fastapi import HTTPException
from python_on_whales import docker as whales
from ..model.models import TaskStatus

# --- 設定：環境に合わせて調整 ---
HOST_PROJECTS_ROOT = os.getenv("HOST_PROJECTS_ROOT", "/home/user/ai-platform/data/projects")
TASKS_FILE = pathlib.Path(HOST_PROJECTS_ROOT) / "tasks_db.json"


class TaskManager:
    """タスク管理クラス（シングルトン）"""
    tasks: ClassVar[dict[str, TaskStatus]] = {}
    
    @classmethod
    def get_projects_root(cls) -> pathlib.Path:
        return pathlib.Path(HOST_PROJECTS_ROOT)
    
    @classmethod
    def get_tasks_file_path(cls) -> pathlib.Path:
        return TASKS_FILE
    
    @classmethod
    def get_task(cls, task_id: str) -> Optional[TaskStatus]:
        return cls.tasks.get(task_id)
    
    @classmethod
    def upsert_task(cls, status: TaskStatus):
        cls.tasks[status.task_id] = status
        cls.save_tasks()

    @classmethod
    def get_all_tasks(cls) -> dict[str, TaskStatus]:
        return cls.tasks
    
    @classmethod
    def remove_task(cls, task_id: str):
        if task_id in cls.tasks:
            del cls.tasks[task_id]
        cls.save_tasks()

    @classmethod
    def save_tasks(cls):
        """現在のタスク状態をファイルに保存する"""
        TaskManager.get_tasks_file_path().parent.mkdir(parents=True, exist_ok=True)
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
                    # 旧フォーマット互換（任意）:
                    # 以前は trace_id を TaskStatus.metadata["trace_id"] に入れていた。
                    # DBを作り直さない運用でも壊れないよう、読み込み時だけ第一級フィールドへ移植する。
                    if isinstance(v, dict) and not v.get("trace_id"):
                        md = v.get("metadata")
                        if isinstance(md, dict) and isinstance(md.get("trace_id"), str) and md.get("trace_id"):
                            v = {**v, "trace_id": md.get("trace_id")}

                    cls.tasks[k] = TaskStatus(**v)


    @classmethod
    def list_tasks(cls) -> list[TaskStatus]:
        """タスクの一覧表示"""
        TaskManager.load_tasks()
        tasks = TaskManager.get_all_tasks()
        if not tasks:
            # self.actions.after_task_not_found_action()
            return []
        
        return list(tasks.values())

    @classmethod
    async def show_status(cls, task_id: str, tail: int) -> TaskStatus:
        """ステータスとログの表示（async版に統一）"""
        data = await TaskManager.get_status(task_id, tail=tail)
        return data

    # --- ステータス取得の修正 ---
    @classmethod
    async def get_status(cls, task_id: str, tail: int | None = 200) -> TaskStatus:
        # CLI はコマンドごとに別プロセスで起動されるため、永続ストアから都度復元する
        TaskManager.load_tasks()
        task = TaskManager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # デタッチ実行などで monitor が走らない場合でも、status 取得時にコンテナ状態を再評価して追従する。
        if task.container_id:
            try:
                container = whales.container.inspect(task.container_id)
                # state を最新化
                container.reload()

                # logs の取得（running/exited いずれも取得可能）
                if tail is None:
                    logs = whales.container.logs(task.container_id)
                else:
                    logs = whales.container.logs(task.container_id, tail=tail)

                if isinstance(logs, str):
                    logs_str = logs
                else:
                    logs_str = "".join(
                        b.decode("utf-8", errors="replace") if isinstance(b, bytes) else str(b)
                        for _, b in logs
                    )

                status = getattr(getattr(container, "state", None), "status", None)
                exit_code = getattr(getattr(container, "state", None), "exit_code", None)

                if status == "exited":
                    # 監視プロセスがいなくても、ここで最終状態へ寄せる
                    if exit_code == 0:
                        task.completed()
                    else:
                        task.failed()
                    task.stdout = logs_str
                    TaskManager.upsert_task(task)
                    return task

                # running の場合は増分ログを返す（保存はしない）
                return TaskStatus(**task.model_dump(exclude={"stdout"}), stdout=logs_str)
            except Exception as e:
                # コンテナが既に削除されている等。
                # 既に stdout が保存済みならそれを返し、無い場合のみエラーを埋める。
                if task.stdout is not None or task.status == "exited":
                    return task
                return TaskStatus(**task.model_dump(exclude={"stderr"}), stderr=f"Log/state fetch failed: {e}")

        return task

    # --- キャンセルの修正 ---
    @classmethod
    async def cancel_task(cls, task_id: str):
        TaskManager.load_tasks()
        task = TaskManager.get_task(task_id)
        if task and task.status == "running" and task.container_id:
            try:
                # whales で強制終了
                whales.container.kill(task.container_id)
                task.cancelled()
                TaskManager.upsert_task(task)
                return {"message": f"Task {task_id} cancelled."}
            except Exception as e:
                return {"message": f"Cancel failed: {str(e)}"}
        return {"message": "Task not found or not running."}

    @classmethod
    def prune_containers(cls, compose_service_name: str) -> Generator[str, None, None]:
        """掃除ロジック"""
        containers = whales.container.list(filters={"label": f"managed_by={compose_service_name}"})
        for c in containers:
            c.remove(force=True)
            yield f"Removed container {c.id[:12]}"
