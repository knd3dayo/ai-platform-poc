import io
import base64
from pathlib import Path
from typing import Any, Dict, Optional
import base64
import requests

from langchain_core.tools import tool

from langgraph.prebuilt import ToolNode

from ..model.models import ServerConfig
from ..core.utils import JobUtils
from .utils import JobUtils, ZipUtils, error_result, poll_status

class Tools:

    @tool
    @staticmethod
    def run_autonomous_agent_executor(
        prompt: str,
        initial_files: Optional[Dict[str, str]] = None,
        timeout: int = 300,
    ) -> Dict[str, Any]:
        """Executor Service(コーディングエージェント実行API) を呼び出して結果を返す（同期ツール）。

        呼び出し:
        1) POST /execute で task_id を取得
        2) GET /status/{task_id} を完了までポーリング
        3) completed/failed/timeout 等の最終結果を返す
        
        NOTE:
            LangGraph の ToolNode は同期実行パスを通ることがあるため、このツールは同期関数にしている。
        """

        server_config = ServerConfig.load_from_env()
        try:
            base_url = server_config.executor_base_url
            payload: Dict[str, Any] = {"prompt": prompt, "timeout": timeout}
            if initial_files:
                payload["initial_files"] = initial_files

            res = requests.post(f"{base_url}/execute", json=payload, timeout=30)
            res.raise_for_status()
            task_id = res.json()["task_id"]

            try:
                final_status = poll_status(task_id, timeout_sec=timeout + 30)
            except Exception as e:
                return error_result(f"Failed to poll status: {e}", task_id=task_id)

            # 完了後に成果物ZIPを取得して返す。
            # NOTE: base64 でクライアントへ返すのは PoC 用の便法。
            #       ファイルサイズが大きいとレスポンス肥大・メモリ圧迫・転送コスト増となり不向き。
            #       将来的にはシステム全体で成果物置き場（S3/Box等）を構築し、URL参照（署名付きURL等）で
            #       受け渡す方式を検討する。
            try:
                zip_bytes = ZipUtils.download_artifacts_zip_bytes(task_id)
                zip_b64 = base64.b64encode(zip_bytes).decode("ascii")
                file_list, text_previews = JobUtils.inspect_zip_bytes(zip_bytes)
            except Exception as e:
                # 成果物取得に失敗しても、実行結果自体は返す
                return {
                    "task_id": task_id,
                    **final_status,
                    "artifacts_zip_error": str(e),
                }

            return {
                "task_id": task_id,
                **final_status,
                "artifacts_zip_bytes": len(zip_bytes),
                "artifacts_zip_base64": zip_b64,
                "artifacts_zip_file_list": file_list,
                "artifacts_zip_text_previews": text_previews,
            }
        except Exception as e:
            return error_result(f"run_autonomous_agent_executor failed: {e}")


    @tool
    @staticmethod
    def run_autonomous_agent_executor_zip(
        prompt: str,
        dir_path: Optional[str] = None,
        zip_path: Optional[str] = None,
        timeout: int = 600,
    ) -> Dict[str, Any]:
        """Executor Service の /execute/zip を使い、関連ファイル一式をアップロードして実行する（同期ツール）。

        `dir_path` または `zip_path` のどちらか一方を指定する。

        処理の流れ:
        1) dir_path の場合はディレクトリをZIP化（zip_path の場合はそのまま読む）
        2) multipart/form-data で POST /execute/zip
        3) GET /status/{task_id} を完了までポーリング
        """
        server_config = ServerConfig.load_from_env()  # 先にロードしておいて、エラーがあれば早めに返す  

        if (dir_path is None and zip_path is None) or (dir_path is not None and zip_path is not None):
            raise ValueError("Specify exactly one of dir_path or zip_path")

        try:
            base_url = server_config.executor_base_url

            if dir_path is not None:
                zip_bytes = ZipUtils.zip_dir_to_bytes(dir_path)
                file_tuple = ("project.zip", io.BytesIO(zip_bytes), "application/zip")
            else:
                p = Path(zip_path)  # type: ignore[arg-type]
                if not p.exists() or not p.is_file():
                    raise ValueError(f"zip_path must be an existing zip file: {zip_path}")
                file_tuple = (p.name, p.open("rb"), "application/zip")

            data = {"prompt": prompt, "timeout": str(timeout)}
            files = {"file": file_tuple}
            try:
                res = requests.post(f"{base_url}/execute/zip", data=data, files=files, timeout=60)
                res.raise_for_status()
                task_id = res.json()["task_id"]

                try:
                    final_status = poll_status(task_id, timeout_sec=timeout + 30)
                except Exception as e:
                    return error_result(f"Failed to poll status: {e}", task_id=task_id)

                try:
                    zip_bytes = ZipUtils.download_artifacts_zip_bytes(task_id)
                    zip_b64 = base64.b64encode(zip_bytes).decode("ascii")
                    file_list, text_previews = JobUtils.inspect_zip_bytes(zip_bytes)
                except Exception as e:
                    return {
                        "task_id": task_id,
                        **final_status,
                        "artifacts_zip_error": str(e),
                    }

                return {
                    "task_id": task_id,
                    **final_status,
                    "artifacts_zip_bytes": len(zip_bytes),
                    "artifacts_zip_base64": zip_b64,
                    "artifacts_zip_file_list": file_list,
                    "artifacts_zip_text_previews": text_previews,
                }
            finally:
                # zip_path の場合だけファイルハンドルを閉じる
                if zip_path is not None:
                    try:
                        file_tuple[1].close()  # type: ignore[union-attr]
                    except Exception:
                        pass
        except Exception as e:
            return error_result(f"run_autonomous_agent_executor_zip failed: {e}")

    tools: list = [run_autonomous_agent_executor, run_autonomous_agent_executor_zip]
    tools_node = ToolNode(tools)
