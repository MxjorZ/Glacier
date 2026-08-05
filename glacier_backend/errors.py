"""Global Error Center (Stage 4).

Every error Glacier encounters is captured here so it stays visible in the UI
even if the user never looks at Docker logs. Errors are persisted to
``~/.glacier_errors.json`` (surviving restarts) and remain available until the
user manually clears or exports them.

An entry carries:
  * id          — stable identifier (for copy / dismiss)
  * ts          — unix timestamp
  * title       — short human-readable title
  * message     — detailed error message
  * module      — source module that raised the error
  * severity    — error | warning | info
  * job_id      — originating background job, if any
  * traceback   — captured stack trace (expandable in the UI)
"""

import json
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path

from . import config

MAX_ERRORS = 500


class ErrorStore:
    def __init__(self, path=None):
        self._path = Path(path or config.ERRORS_PATH)
        self._lock = threading.Lock()
        self._errors = self._load()

    def _load(self):
        try:
            with open(self._path, "r", encoding="utf-8-sig") as fh:
                data = json.load(fh)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _flush(self):
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(self._errors[-MAX_ERRORS:], fh,
                          indent=2, ensure_ascii=False)
        except Exception:
            pass

    def add(self, title, message="", module=None, severity="error",
            exc=None, job_id=None, trace=None):
        entry = {
            "id": uuid.uuid4().hex[:12],
            "ts": time.time(),
            "title": title or "Error",
            "message": message or "",
            "module": module or "",
            "severity": severity if severity in ("error", "warning", "info") else "error",
            "job_id": job_id,
            "traceback": trace
                         or ("".join(traceback.format_exception(
                             type(exc), exc, exc.__traceback__))
                             if exc else None),
        }
        with self._lock:
            self._errors.append(entry)
            if len(self._errors) > MAX_ERRORS:
                self._errors = self._errors[-MAX_ERRORS:]
            self._flush()
        return dict(entry)

    def report_exception(self, message=None, module=None, job_id=None):
        """Capture the exception currently being handled, with its traceback."""
        exc = sys.exc_info()[1]
        return self.add(
            message or ("Operation failed" if exc else "Error"),
            str(exc) if exc else (message or ""),
            module=module, severity="error", exc=exc, job_id=job_id)

    def list(self):
        with self._lock:
            return [dict(e) for e in self._errors]

    def clear(self):
        with self._lock:
            self._errors = []
        self._flush()


# Module-level singleton used by the Flask app and job supervisor.
store = ErrorStore()
