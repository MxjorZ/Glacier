"""Quick probe for the Stage 3 library-enabled feature (dev-only, not part of
the shipped test suite). Verifies:
  * GET /api/libraries/status returns enabled + exists
  * PATCH /api/libraries/<id> toggles enabled
  * batch analyze skips disabled libraries
"""
import os
import tempfile

import glacier_backend.config as config
import glacier_backend.settings as settings_mod
import glacier_backend.app as app_mod
import glacier_backend.api as api_mod

# Isolate settings so we never touch the real ~/.glacier_settings.json.
tmp = tempfile.mkdtemp(prefix="glacier_probe_")
settings_mod.config.SETTINGS_PATH = os.path.join(tmp, ".glacier_settings.json")
new_store = settings_mod.Store(os.path.join(tmp, ".glacier_settings.json"))
settings_mod.store = new_store
api_mod.store = new_store  # routes use this module-level singleton

# Two real temp library dirs.
d1 = os.path.join(tmp, "lib_one"); os.makedirs(d1)
d2 = os.path.join(tmp, "lib_two"); os.makedirs(d2)

store = settings_mod.store
lib_a = store.add_library("One", d1)
lib_b = store.add_library("Two", d2)

app = app_mod.create_app()
c = app.test_client()

status = c.get("/api/libraries/status").get_json()
assert status["ok"] is True
assert len(status["libraries"]) == 2, status
for lib in status["libraries"]:
    assert lib["enabled"] is True, lib
    assert lib["exists"] is True, lib
print("status: 2 libraries, both enabled, both exist -> OK")

# Disable library B via PATCH.
res = c.patch(f"/api/libraries/{lib_b['id']}", json={"enabled": False}).get_json()
assert res["ok"] is True
by_id = {l["id"]: l for l in res["libraries"]}
assert by_id[lib_b["id"]]["enabled"] is False
print("PATCH enabled=False persisted -> OK")

status = c.get("/api/libraries/status").get_json()
by_id = {l["id"]: l for l in status["libraries"]}
assert by_id[lib_b["id"]]["enabled"] is False
assert by_id[lib_a["id"]]["enabled"] is True
print("status reflects disabled flag -> OK")

# Write a silent FLAC-like inventory so the scanner has content (smoke-test
# helpers build real files; here we just confirm the enabled filter path runs).
from glacier_backend.api import op_analyze, _enabled_libs
enabled = _enabled_libs()
assert [l["id"] for l in enabled] == [lib_a["id"]], enabled
print(f"enabled-lib helper excludes disabled -> OK ({len(enabled)} active)")

# To fully exercise op_analyze, add one tiny MP3-style inventory per empty lib.
# Empty dirs: scanner yields zero tracks but still returns per-library entries.
r = op_analyze(None)  # library_ids=None -> batch analyze (enabled only)
assert r["ok"] is True
assert set(r["libraries"].keys()) == {lib_a["id"]}, set(r["libraries"].keys())
print("batch analyze skipped the disabled library -> OK")

# Existing settings invariants still hold through normalization.
s = settings_mod._normalize(store.get())
for lib in s["libraries"]:
    assert lib.get("enabled") is not None
print("normalize keeps enabled flag -> OK")

print("\nALL LIBRARY-ENABLED PROBES PASSED")
