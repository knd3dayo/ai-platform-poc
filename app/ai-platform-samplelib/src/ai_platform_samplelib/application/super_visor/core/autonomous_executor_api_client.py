from __future__ import annotations

from typing import Any, Dict, Optional

import requests


class AutonomousExecutorApiClient:
    def __init__(self, base_url: str, *, timeout_sec: float = 30.0):
        base_url = (base_url or "").strip().rstrip("/")
        if not base_url:
            raise ValueError("base_url is required")
        self._base_url = base_url
        self._timeout_sec = timeout_sec

    @property
    def base_url(self) -> str:
        return self._base_url

    def execute(
        self,
        *,
        prompt: str,
        workspace_path: str,
        timeout: int = 300,
        task_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> str:
        payload: Dict[str, Any] = {
            "prompt": prompt,
            "workspace_path": workspace_path,
            "timeout": timeout,
        }
        if task_id:
            payload["task_id"] = task_id
        if trace_id:
            payload["trace_id"] = trace_id

        res = requests.post(f"{self._base_url}/execute", json=payload, timeout=self._timeout_sec)
        res.raise_for_status()
        data = res.json()
        tid = data.get("task_id")
        if not isinstance(tid, str) or not tid:
            raise RuntimeError(f"Invalid execute response: {data}")
        return tid

    def get_status(self, task_id: str, *, tail: Optional[int] = 200) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if tail is not None:
            params["tail"] = tail
        res = requests.get(f"{self._base_url}/status/{task_id}", params=params, timeout=self._timeout_sec)
        res.raise_for_status()
        data = res.json()
        if not isinstance(data, dict):
            raise RuntimeError(f"Invalid status response: {data}")
        return data

    def cancel(self, task_id: str) -> Dict[str, Any]:
        res = requests.delete(f"{self._base_url}/cancel/{task_id}", timeout=self._timeout_sec)
        res.raise_for_status()
        data = res.json()
        if not isinstance(data, dict):
            return {"message": str(data)}
        return data
