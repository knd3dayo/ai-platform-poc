from collections import deque
from typing import Deque, Dict, Any, List, Tuple, Optional
from pathlib import Path
import zipfile
import io
import os
import time
import requests
from langchain_openai import ChatOpenAI
from pydantic import SecretStr


from ..model.models import Job, jobs_lock, jobs, ServerConfig


class LLMUtils:
    @staticmethod
    def create_llm() -> ChatOpenAI:
        """LLMのインスタンスを生成する関数（必要に応じてカスタマイズ）"""
        # .envファイルから環境変数を読み込む
        server_config = ServerConfig.load_from_env()
        params = {
            "model": server_config.llm_model,
            "api_key": SecretStr(server_config.llm_api_key or ""),
        }
        if server_config.llm_base_url:
            base_url = server_config.llm_base_url
            params["base_url"] = base_url
        
        llm = ChatOpenAI(
            **params
            )
        return llm

class JobUtils:
    @classmethod
    def append_server_log(cls, job: Job, line: str, max_lines: int = 200) -> None:
        """サーバ側の進捗ログをリングバッファで保持する（/api/status で返す用）。"""
        logs: Deque[str] = job.progress.setdefault("server_logs", deque(maxlen=max_lines))  # type: ignore[assignment]
        # deque は json 化できないので、返却時に list 化する
        if isinstance(logs, deque):
            logs.append(line)

    @classmethod
    def get_cancel_flag(cls, job: Job) -> bool:
        return bool(job.progress.get("cancel_requested"))


    @classmethod
    def set_cancel_flag(cls, job: Job) -> None:
        job.progress["cancel_requested"] = True
        job.progress["cancel_requested_at"] = time.time()


    @classmethod
    def try_cancel_executor_task(cls, job: Job) -> None:
        """tool 結果に task_id が入っていれば Autonomous Agent Executor へ cancel を投げる（ベストエフォート）。"""
        last_tool = job.progress.get("last_tool")
        if not isinstance(last_tool, dict):
            return
        task_id = last_tool.get("task_id")
        if not task_id:
            return

        base_url = job.progress.get("executor_base_url")
        if not isinstance(base_url, str) or not base_url:
            return

        try:
            import requests

            requests.delete(f"{base_url.rstrip('/')}/cancel/{task_id}", timeout=10)
            cls.append_server_log(job, f"Sent cancel to executor task_id={task_id}")
        except Exception as e:
            cls.append_server_log(job, f"Failed to cancel executor task: {e}")


    @classmethod
    def is_probably_text_file(cls, path: str) -> bool:
        ext = Path(path).suffix.lower()
        return ext in {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".log"}


    @classmethod
    def inspect_zip_bytes(
        cls,
        zip_bytes: bytes,
        *,
        max_preview_files: int = 50,
        max_preview_chars_per_file: int = 2000,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        """ZIP(bytes)の内容を簡易的に検査して返す。

        Returns:
            (file_list, text_previews)

        - file_list: [{"path": str, "size": int}, ...]
        - text_previews: {"path": "先頭N文字...", ...}

        NOTE:
            Supervisor が成果物の中身を確認して次の実行計画を立て直せるよう、
            LLMに渡しやすい形（一覧＋テキストプレビュー）に整形する。
        """
        file_list: List[Dict[str, Any]] = []
        text_previews: Dict[str, str] = {}

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            infos = zf.infolist()
            for info in infos:
                if info.is_dir():
                    continue
                file_list.append({"path": info.filename, "size": info.file_size})

            # テキストっぽいファイルだけ、先頭をプレビューする
            preview_count = 0
            for info in infos:
                if preview_count >= max_preview_files:
                    break
                if info.is_dir():
                    continue
                if not cls.is_probably_text_file(info.filename):
                    continue

                try:
                    raw = zf.read(info.filename)
                    txt = raw.decode("utf-8", errors="replace")
                    text_previews[info.filename] = txt[:max_preview_chars_per_file]
                    preview_count += 1
                except Exception:
                    # プレビュー不能（バイナリ/壊れ等）はスキップ
                    continue

        return file_list, text_previews

class ZipUtils:
    @staticmethod
    def create_zip_bytes_from_dir(dir_path: str) -> bytes:
        """指定されたディレクトリをZIP化してbytesで返す。"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(dir_path):
                for file in files:
                    full_path = os.path.join(root, file)
                    arcname = os.path.relpath(full_path, start=dir_path)
                    zf.write(full_path, arcname=arcname)
        return buf.getvalue()
    
    @staticmethod
    def zip_dir_to_bytes(dir_path: str) -> bytes:
        """ディレクトリをZIP化してbytesで返す（同期関数）

        - .git/.venv/node_modules/__pycache__ などはデフォルトで除外
        """
        base = Path(dir_path)
        if not base.exists() or not base.is_dir():
            raise ValueError(f"dir_path must be an existing directory: {dir_path}")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in base.rglob("*"):
                if p.is_file():
                    # ZIP内のパスはディレクトリ相対
                    arcname = p.relative_to(base).as_posix()
                    if ZipUtils.should_exclude_path(arcname):
                        continue
                    zf.write(p, arcname=arcname)
        return buf.getvalue()


    @staticmethod
    def download_artifacts_zip_bytes(task_id: str) -> bytes:
        """Autonomous Agent Executor Service の成果物ZIPをダウンロードして bytes で返す（同期関数）"""
        server_config = ServerConfig.load_from_env()
        base_url = server_config.executor_base_url
        res = requests.get(f"{base_url}/artifacts/{task_id}/zip", timeout=60)
        res.raise_for_status()
        return res.content



    @staticmethod
    def should_exclude_path(rel_posix: str) -> bool:
        """ZIP化対象から除外するパスかどうかを判定する（ディレクトリ相対のPOSIXパス）"""
        # 先頭セグメントで除外（プロジェクト直下の .git や node_modules 等を想定）
        first = rel_posix.split("/", 1)[0]
        if first in {".git", ".venv", "venv", "node_modules", ".mypy_cache", ".pytest_cache"}:
            return True

        # どこに居ても除外したいディレクトリ名
        if "/__pycache__/" in f"/{rel_posix}/":
            return True

        # よくある大容量/不要ファイル
        if rel_posix.endswith(".pyc"):
            return True

        return False


def error_result(message: str, *, task_id: Optional[str] = None) -> Dict[str, Any]:
    res: Dict[str, Any] = {
        "status": "failed",
        "stdout": "",
        "stderr": message,
        "artifacts": [],
    }
    if task_id is not None:
        res["task_id"] = task_id
    return res

def poll_status(task_id: str, timeout_sec: int) -> Dict[str, Any]:
    """Autonomous Agent Executor Service の /status をポーリングして完了を待つ（同期関数）"""
    base_url = ServerConfig.load_from_env().executor_base_url
    deadline = time.time() + timeout_sec

    while True:
        # NOTE: executor 側が running 中でも stdout/stderr を返せるようになったため tail を付与
        #       （executor 側デフォルトも 200 だが明示しておく）
        res = requests.get(f"{base_url}/status/{task_id}", params={"tail": 200}, timeout=10)
        res.raise_for_status()
        status_data = res.json()
        status = status_data.get("status")

        if status in ["completed", "failed", "timeout", "cancelled"]:
            return status_data

        if time.time() > deadline:
            # Executor側のtimeoutとは別に、Supervisor側の待機も打ち切れるようにしておく
            raise TimeoutError(f"Timed out while waiting executor task completion: task_id={task_id}")

        time.sleep(1.0)
