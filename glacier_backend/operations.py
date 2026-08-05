"""Recent operations history (Stage 4).

Tracks every background operation Glacier runs with enough detail for the UI to
show a useful history: timestamp, operation name, the library it acted on, the
overall result, and how long it took. Persisted to ``~/.glacier_operations.json``
so history survives restarts.
"""

import json
import threading
import time
from pathlib import Path

from . import config

MAX_OPS = 300


class OperationStore:
    def __init__(self, path=None):
        self._path = Path(path or config.OPERATIONS_PATH)
        self._lock = threading.Lock()
        self._ops = self._load()

    def _load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _flush(self):
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(self._ops[-MAX_OPS:], fh, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def add(self, operation, library=None, status="complete", result=None,
            duration=None, message=None):
        """Append one finished operation record. Returns the live list."""
        with self._lock:
            self._ops.append({
                "ts": time.time(),
                "operation": operation,
                "library": library,
                "status": status if status in ("complete", "error", "cancelled") else "complete",
                "result": result,
                "duration": duration,
                "message": message,
            })
            if len(self._ops) > MAX_OPS:
                self._ops = self._ops[-MAX_OPS:]
            self._flush()

    def list(self, limit=100):
        with self._lock:
            return [dict(o) for o in self._ops[-limit:]]


# Module-level singleton used by the job supervisor.
store = OperationStore()
