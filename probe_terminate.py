"""Quick probe: verify job cancellation machinery end-to-end via the supervisor
with a slow callback that polls is_cancelled().  Dev-only."""
import sys
import time

sys.path.insert(0, ".")

from glacier_backend.jobs import supervisor
from glacier_backend import cancel


def slow_job():
    total = 50
    for i in range(total):
        if cancel.is_cancelled():
            raise cancel.JobCancelled()
        time.sleep(0.05)
    return {"ok": True, "items": total}


ok, job = supervisor.start("probe-slow", slow_job)
jid = job["id"]
print("started job:", jid, "ok:", ok)

time.sleep(0.3)
assert jid in [j["id"] for j in supervisor.all_running()], "job should be running"

res = supervisor.cancel(jid)
print("cancel(jid) ->", res)
assert res is True

time.sleep(0.5)
hist = supervisor.history
done = [j for j in hist if j["id"] == jid]
print("final job:", done[-1] if done else None)
assert done and done[-1]["status"] == "cancelled", done
print("SUPERVISOR CANCELLATION PROBE PASSED")
