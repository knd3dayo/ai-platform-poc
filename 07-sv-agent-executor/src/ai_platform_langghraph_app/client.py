"""SV Agent Executor API のテスト用クライアント

このクライアントは `api_server.py` の新仕様に合わせています。

- POST /api/submit (multipart/form-data)
    - message: str (必須)
    - file: zip (任意)
- GET /api/status/{thread_id}
    - status (queued/running/completed/failed)
    - progress.server_logs / progress.stdout / progress.stderr

Usage:
    # ZIPなし
    uv run --active python -m ai_platform_langghraph_app.client --message "hello" \
        --api-url http://localhost:5202

    # ZIPあり
    uv run --active python -m ai_platform_langghraph_app.client --message "このZIPを見て" \
        --zip-path ./project.zip --api-url http://localhost:5202
"""

from __future__ import annotations

import argparse
import json
import signal
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests


def submit_job(api_url: str, message: str, zip_path: Optional[str]) -> str:
    api_url = api_url.rstrip("/")

    files = None
    file_handle = None
    try:
        if zip_path:
            p = Path(zip_path)
            if not p.exists() or not p.is_file():
                raise ValueError(f"zip_path not found: {zip_path}")
            file_handle = p.open("rb")
            files = {"file": (p.name, file_handle, "application/zip")}

        res = requests.post(
            f"{api_url}/api/submit",
            data={"message": message},
            files=files,
            timeout=60,
        )
        res.raise_for_status()
        return res.json()["thread_id"]
    finally:
        if file_handle is not None:
            try:
                file_handle.close()
            except Exception:
                pass


def get_status(api_url: str, thread_id: str) -> Dict[str, Any]:
    api_url = api_url.rstrip("/")
    res = requests.get(f"{api_url}/api/status/{thread_id}", timeout=30)
    res.raise_for_status()
    return res.json()


def cancel_job(api_url: str, thread_id: str) -> None:
    api_url = api_url.rstrip("/")
    try:
        requests.delete(f"{api_url}/api/cancel/{thread_id}", timeout=10)
    except Exception:
        # キャンセル通知に失敗しても、クライアント終了を優先
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="SV Agent Executor API test client")
    parser.add_argument("--api-url", default="http://localhost:5202", help="SV Agent Executor API base url")
    parser.add_argument("--message", required=True, help="user message")
    parser.add_argument("--zip-path", default=None, help="optional zip file path")
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--max-wait-sec", type=int, default=180)
    parser.add_argument("--print-json", action="store_true", help="print full status json on each poll")

    args = parser.parse_args()

    thread_id = submit_job(args.api_url, args.message, args.zip_path)
    print(f"submitted thread_id={thread_id}")

    # Ctrl+C を受けたら cancel を送って終了する
    cancel_requested = False

    def _handle_sigint(_sig, _frame):
        nonlocal cancel_requested
        if cancel_requested:
            raise KeyboardInterrupt
        cancel_requested = True
        print("\nCtrl+C detected. Sending cancel request...")
        cancel_job(args.api_url, thread_id)
        print("cancel request sent. exiting...")
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _handle_sigint)

    deadline = time.time() + args.max_wait_sec
    last_logs_len = 0

    while True:
        st = get_status(args.api_url, thread_id)
        status = st.get("status")
        progress = st.get("progress") or {}
        logs = progress.get("server_logs") or []

        if args.print_json:
            print(json.dumps(st, ensure_ascii=False, indent=2))
        else:
            # 差分だけ出す
            new_logs = logs[last_logs_len:]
            for line in new_logs:
                print(f"[server] {line}")
            last_logs_len = len(logs)

            latest = progress.get("latest_message")
            if latest:
                print(f"latest_message: {latest}")

            stderr = progress.get("stderr")
            if stderr:
                print(f"stderr: {stderr}")

        if status in ("completed", "failed"):
            print(f"done status={status}")
            if st.get("error"):
                print(f"error: {st['error']}")
            break

        if time.time() > deadline:
            raise TimeoutError(f"Timed out: thread_id={thread_id}")

        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
