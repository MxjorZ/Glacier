"""Job supervisor (concurrent).

Multiple filesystem-heavy jobs may run at the same time. Each job runs in its
own daemon thread and streams SSE events keyed by its job id, so the UI can
track several activities at once (analysis, organize, covers, report, ...).
``start`` always accepts and creates a new job — there is no single-job lock.
"""

import threading
import time

from . import events
from . import errors as errors_store
from . import operations as operations_store


def _new_id():
    return int(time.time() * 1000) % 1000000


class Supervisor:
    def __init__(self):
        self._lock = threading.Lock()
        self._jobs = {}      # id -> running job dict
        self._history = []   # completed jobs (append-only, capped)

    def running(self):
        with self._lock:
            return bool(self._jobs)

    def all_running(self):
        with self._lock:
            return [dict(j) for j in self._jobs.values()]

    @property
    def current(self):
        """Most recently started running job, or None (kept for compatibility)."""
        with self._lock:
            if not self._jobs:
                return None
            return dict(max(self._jobs.values(), key=lambda j: j["start"]))

    @property
    def history(self):
        with self._lock:
            return list(self._history)

    def start(self, operation, callback, *args, library=None, **kwargs):
        """Start ``callback`` as a background job. Always accepted.

        ``library`` is an optional human-readable library name used only for the
        recent-operations history. Returns ``(ok, job)`` with ``ok`` always True.
        The job runs in a daemon thread and always terminates its own SSE stream,
        job-state event, and records its outcome in the persistent history.
        """
        job = {
            "id": _new_id(),
            "operation": operation,
            "library": library,
            "status": "running",
            "start": time.time(),
            "end": None,
            "result": None,
        }
        with self._lock:
            self._jobs[job["id"]] = job

        events.job_state({**job, "running": True})

        def record_operation(status, result, duration):
            operations_store.store.add(
                operation,
                library=library,
                status=status,
                result=result,
                duration=duration,
                message=result.get("message") if isinstance(result, dict) else None)

        def runner():
            events.set_job_id(job["id"])
            try:
                result = callback(*args, **kwargs)
                with self._lock:
                    job["result"] = result
                    job["status"] = "complete"
                    job["end"] = time.time()
                    self._jobs.pop(job["id"], None)
                    self._history = (self._history + [dict(job)])[-200:]
                record_operation("complete", result, job["end"] - job["start"])
                events.done("Operation complete", result)
                events.job_state({**job, "running": False})
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    job["result"] = {"ok": False, "error": str(exc)}
                    job["status"] = "error"
                    job["end"] = time.time()
                    self._jobs.pop(job["id"], None)
                    self._history = (self._history + [dict(job)])[-200:]
                record_operation("error", job["result"], job["end"] - job["start"])
                errors_store.store.report_exception(
                    f"Job '{operation}' failed", module="jobs", job_id=job["id"])
                events.log(f"Job '{operation}' failed: {exc}", "error")
                events.error(str(exc), job_id=job["id"])
                events.done(f"Operation failed: {exc}", job["result"])
                events.job_state({**job, "running": False})
            finally:
                events.set_job_id(None)

        threading.Thread(target=runner, daemon=True).start()
        return True, job


supervisor = Supervisor()


