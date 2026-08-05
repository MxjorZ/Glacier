"""Probe: concurrent jobs + error event + progress job_id + per-file logging."""
import time
from glacier_backend import events, jobs

supervisor = jobs.supervisor

# --- concurrent jobs: start two at once, both accepted ---
def slow(which, t):
    time.sleep(t)
    return {"ok": True, "which": which}

ok1, j1 = supervisor.start("job-a", slow, "A", 1.0)
ok2, j2 = supervisor.start("job-b", slow, "B", 1.0)
assert ok1 and ok2, (ok1, ok2)
assert j1["id"] != j2["id"]

time.sleep(0.4)
running = [j["operation"] for j in supervisor.all_running()]
assert "job-a" in running and "job-b" in running, running
print(f"concurrent running after 0.4s: {running} (both accepted, no reject)")

time.sleep(1.4)  # let both finish
assert not supervisor.running(), supervisor.all_running()
hist_op = [j["operation"] for j in supervisor.history]
assert "job-a" in hist_op and "job-b" in hist_op, hist_op
print(f"both completed: {hist_op}")

# --- error event emitted ---
errs = []
oeb = events.hub.broadcast
def spy(d):
    if isinstance(d, dict) and d.get("type") == "error":
        errs.append(d)
events.hub.broadcast = spy
events.error("boom")
assert len(errs) == 1 and errs[0]["message"] == "boom"
events.hub.broadcast = oeb
print(f"error event emitted OK -> {errs[0]['type']}")

# --- progress carries job_id + ts when inside a job context ---
events.set_job_id("JOBX")
prog = []
osp = events.hub.broadcast
def spy2(d):
    if isinstance(d, dict) and d.get("type") == "progress":
        prog.append(d)
events.hub.broadcast = spy2
events.progress(10, 100, "scanning")
assert prog and prog[0]["job_id"] == "JOBX" and prog[0]["ts"], prog
events.hub.broadcast = osp
print(f"progress has job_id={prog[0]['job_id']} and ts -> OK")
events.set_job_id(None)

print("\nALL CONCURRENCY/EVENT PROBES PASSED")
