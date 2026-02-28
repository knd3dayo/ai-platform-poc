from dataclasses import dataclass
from typing import Dict, Any, Optional
import threading

# =====================================================
# In-memory job store (PoC)
# =====================================================
# NOTE:
#   本番用途では Redis / DB など永続ストアに移すこと。


@dataclass
class Job:
    thread_id: str
    status: str  # queued, running, completed, failed
    # status polling で返すための進捗情報（PoC）
    progress: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


jobs_lock = threading.Lock()

jobs: Dict[str, Job] = {}


