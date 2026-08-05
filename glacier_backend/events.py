"""Server-Sent Events (SSE) hub.

The hub keeps a set of connected client queues and broadcasts events to all of
them. It is thread-safe: producers call ``broadcast`` from worker threads and
clients drain their own queue from a Flask request stream.

Event payloads are plain dicts; helpers provide the documented event shapes
(connected, log, progress, done, job_state).
"""

import contextvars
import json
import queue
import threading
import time
from collections import deque

# Job-id correlation: jobs set this (via events.set_job_id) on their worker
# thread so progress events carry the originating job id for per-job tracking.
_job_id_cv = contextvars.ContextVar('glacier_job_id', default=None)


def set_job_id(job_id):
    _job_id_cv.set(job_id)


def get_job_id():
    return _job_id_cv.get()



class _Hub:
    def __init__(self, max_buffer=2000):
        self._lock = threading.Lock()
        self._clients = set()
        self._history = deque(maxlen=max_buffer)

    def connect(self):
        """Register a new client and return its own queue.

        The new client is immediately sent a ``connected`` event onto its own
        queue so the SSE stream produces a first chunk right away (also makes
        the stream flush its headers immediately).
        """
        ev = _event("connected", at=time.time())
        q = queue.Queue()
        with self._lock:
            self._clients.add(q)
            self._history.append(ev)
        q.put_nowait(ev)
        return q

    def disconnect(self, q):
        with self._lock:
            self._clients.discard(q)

    def broadcast(self, data):
        """Broadcast a dict payload to every connected client."""
        if isinstance(data, dict):
            data = data.copy()
        payload = _sse(data)
        with self._lock:
            self._history.append(data)
            for q in list(self._clients):
                try:
                    q.put_nowait(payload)
                    # Trim overflow on slow clients so we never block.
                    while q.qsize() > 512:
                        try:
                            q.get_nowait()
                        except queue.Empty:
                            break
                except queue.Full:
                    pass

    def history(self, limit=200):
        with self._lock:
            items = list(self._history)
        return items[-limit:]


# --- helpers -------------------------------------------------------------

def _sse(data):
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _event(etype, **extra):
    return {"type": etype, **extra}


def log(message, level="info"):
    """Broadcast a 'log' event."""
    hub.broadcast({"type": "log", "level": level, "message": message, "ts": time.time()})


def progress(current, total, label=None):
    """Broadcast a 'progress' event (tagged with the current job id + time)."""
    hub.broadcast({"type": "progress", "current": current, "total": total,
                   "label": label, "job_id": get_job_id(), "ts": time.time()})


def done(message="Operation complete", result=None):
    """Broadcast a 'done' event. Every job must end with this."""
    hub.broadcast({"type": "done", "message": message, "result": result,
                   "ts": time.time(), "job_id": get_job_id()})


def error(message, job_id=None):
    """Broadcast a dedicated 'error' event (surfaced in the top bar + log)."""
    hub.broadcast({"type": "error", "message": message, "ts": time.time(),
                   "job_id": job_id or get_job_id()})


def job_state(state):
    hub.broadcast({"type": "job_state", **state})


def artist_exclusivity_report(count):
    """Broadcast a structured 'artist_exclusivity_report' event (Stage 2)."""
    hub.broadcast({"type": "artist_exclusivity_report", "count": count,
                   "ts": time.time()})


hub = _Hub()
