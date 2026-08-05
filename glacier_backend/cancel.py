"""Cooperative job cancellation.

Python threads cannot be force-killed, so termination is cooperative: a per-job
``threading.Event`` is armed by the supervisor when the user asks to terminate a
running job, and long-running filesystem loops (the scanner) poll
``is_cancelled()`` between files and raise ``JobCancelled`` when it is set. The
supervisor catches that exception and records the job as ``cancelled`` instead of
a normal completion/error.

The job id is correlated through ``events.get_job_id()`` (set by the supervisor
on each worker thread), so ``is_cancelled()`` needs no argument inside a worker.
"""

import threading

from . import events

_lock = threading.Lock()
_events = {}  # job_id -> threading.Event


class JobCancelled(Exception):
    """Raised by a worker when its cancellation flag has been armed."""


def register(job_id):
    """Create (or return) the cancellation event for a job id."""
    with _lock:
        evt = _events.setdefault(job_id, threading.Event())
        return evt


def request(job_id):
    """Arm the cancellation flag for ``job_id``."""
    with _lock:
        evt = _events.get(job_id)
    if evt:
        evt.set()


def unregister(job_id):
    """Drop stored state when a job has finished (complete/error/cancelled)."""
    with _lock:
        _events.pop(job_id, None)


def is_cancelled(job_id=None):
    """True if the running job (or the given id) has been asked to stop."""
    jid = job_id or events.get_job_id()
    if not jid:
        return False
    with _lock:
        evt = _events.get(jid)
    return bool(evt and evt.is_set())
