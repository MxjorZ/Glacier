"""Job supervisor (concurrent).

Multiple filesystem-heavy jobs may run at the same time. Each job runs in its
own daemon thread and streams SSE events keyed by its job id, so the UI can
track several activities at once (analysis, organize, covers, report, ...).
``start`` always accepts and creates a new job — there is no single-job lock.

Job ids are monotonic and unique (the old time-based ids collided when two
jobs started in the same millisecond, which made terminate hit the wrong job).
Every job emits: a job_state event at start, progress events from its workers
(tagged with the job id), and a done + final job_state event at the end — so
the ActivityDock can always show progress/ETA and log the outcome.
"""

import itertools
import threading
import time

from . import events
from . import errors as errors_store
from . import operations as operations_store
from . import cancel as cancel

_id_counter = itertools.count(1)
_id_lock = threading.Lock()


def _new_id():
    with _id_lock:
        return next(_id_counter)


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

    def cancel(self, job_id):
        """Request termination of a running job (cooperative).

        Returns True if a running job with that id exists and a termination
        was armed; False otherwise (e.g. it already finished).
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            op_name = job.get("operation", job_id)
        cancel.request(job_id)
        events.log(f"Terminate requested for job #{job_id} ({op_name})", "warning")
        return True

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

    def _finish(self, job, status, result):
        """Move a job from running to history (caller holds no lock)."""
        with self._lock:
            job["status"] = status
            job["end"] = time.time()
            job["result"] = result
            self._jobs.pop(job["id"], None)
            self._history = (self._history + [dict(job)])[-200:]

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

        cancel.register(job["id"])
        events.log(f"Job #{job['id']} started: {operation}"
                   + (f" ({library})" if library else ""), "info")
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
                if cancel.is_cancelled(job["id"]):
                    raise cancel.JobCancelled()
                result = callback(*args, **kwargs)
                self._finish(job, "complete", result)
                record_operation("complete", result, job["end"] - job["start"])
                events.done("Operation complete", result)
                events.job_state({**job, "running": False})
            except cancel.JobCancelled:
                result = {"ok": False, "error": "Job terminated",
                          "cancelled": True}
                self._finish(job, "cancelled", result)
                record_operation("cancelled", result, job["end"] - job["start"])
                events.log(f"Job '{operation}' terminated by user", "warning")
                events.done("Operation cancelled", result)
                events.job_state({**job, "running": False, "status": "cancelled"})
            except Exception as exc:  # noqa: BLE001
                result = {"ok": False, "error": str(exc)}
                self._finish(job, "error", result)
                record_operation("error", result, job["end"] - job["start"])
                errors_store.store.report_exception(
                    f"Job '{operation}' failed", module="jobs", job_id=job["id"])
                events.log(f"Job '{operation}' failed: {exc}", "error")
                events.error(str(exc), job_id=job["id"])
                events.done(f"Operation failed: {exc}", result)
                events.job_state({**job, "running": False})
            finally:
                cancel.unregister(job["id"])
                events.set_job_id(None)

        threading.Thread(target=runner, daemon=True).start()
        return True, job


supervisor = Supervisor()
