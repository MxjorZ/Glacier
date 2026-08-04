"""Job supervisor.

Only one filesystem-heavy operation may run at a time. The supervisor guards an
active job, exposes its state to the UI, streams SSE events, and rejects new
jobs while another is running. Every job is restart-safe: it is entirely
in-memory and the operation functions themselves tolerate individual failures.
"""

import threading
import time
import uuid

from . import events


def _new_id():
    return int(time.time() * 1000) % 1000000


class Supervisor:
    def __init__(self):
        self._lock = threading.Lock()
        self._current = None
        self._history = []

    @property
    def current(self):
        with self._lock:
            return self._current

    @property
    def history(self):
        with self._lock:
            return list(self._history)

    def running(self):
        with self._lock:
            return self._current is not None

    def reject(self):
        return {"ok": False, "error": "Another job is already running"}

    def start(self, operation, callback, *args, **kwargs):
        """Start ``callback`` as a background job if none is running.

        Returns (ok, job_info). The job runs in a daemon thread and always
        terminates its own SSE stream with a 'done' event.
        """
        with self._lock:
            if self._current is not None:
                return False, None
            job = {
                "id": _new_id(),
                "operation": operation,
                "status": "running",
                "start": time.time(),
                "end": None,
                "result": None,
            }
            self._current = job

        events.job_state({**job, "running": True})

        def runner():
            try:
                result = callback(*args, **kwargs)
                with self._lock:
                    job["result"] = result
                    job["status"] = "complete"
                    job["end"] = time.time()
                    self._history.append(dict(job))
                    self._current = None
                events.done("Operation complete", result)
                events.job_state({**job, "running": False})
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    job["result"] = {"ok": False, "error": str(exc)}
                    job["status"] = "error"
                    job["end"] = time.time()
                    self._history.append(dict(job))
                    self._current = None
                events.log(f"Job failed: {exc}", "error")
                events.done(f"Operation failed: {exc}", job["result"])
                events.job_state({**job, "running": False})

        threading.Thread(target=runner, daemon=True).start()
        return True, job


supervisor = Supervisor()
