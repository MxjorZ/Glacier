"""Probe for the recent-session fixes (SSE connect, fast list-dir, 409 dup)."""
import os
import tempfile

import glacier_backend.config as config
import glacier_backend.settings as settings_mod
import glacier_backend.app as app_mod
import glacier_backend.api as api_mod
from glacier_backend import events, browser

# --- 1) SSE hub connect() no longer crashes ---
q = events.hub.connect()
events.hub.disconnect(q)
print("SSE connect()/disconnect() OK (no _event crash)")

# --- 2) list-dir is non-recursive for subfolders (fast) ---
tmp = tempfile.mkdtemp(prefix="glac_fix_")
os.makedirs(os.path.join(tmp, "Artist", "Album"))
open(os.path.join(tmp, "Artist", "Album", "01.flac"), "w").close()
open(os.path.join(tmp, "Artist", "top.mp3"), "w").close()
open(os.path.join(tmp, "readme.txt"), "w").close()

d = browser.list_dir(tmp)
# 'Artist' has 1 direct audio file (top.mp3); the nested 01.flac is NOT counted
# in the per-dir direct count (that's the fast path).
artist = next(x for x in d["dirs"] if x["name"] == "Artist")
assert artist["audio"] == 1, artist
# Current folder recursive total counts both.
assert d["audio_total"] == 2, d
assert d["audio_here"] == 0, d  # readme.txt is not audio
print(f"list-dir fast: Artist dir audio(direct)={artist['audio']}, "
      f"audio_total(current recursive)={d['audio_total']}, audio_here={d['audio_here']}")

# roots include Root / on Linux
if os.name != "nt":
    roots = browser.list_roots()["dirs"]
    assert any(r["name"] == "Root /" for r in roots), roots
    print("Linux roots include 'Root /'")

# --- 3) add_library duplicate -> 409, not a 500 ---
settings_mod.config.SETTINGS_PATH = os.path.join(tmp, "s.json")
new_store = settings_mod.Store(os.path.join(tmp, "s.json"))
settings_mod.store = new_store
api_mod.store = new_store
app = app_mod.create_app()
c = app.test_client()

libdir = os.path.join(tmp, "music"); os.makedirs(libdir)
r1 = c.post("/api/libraries", json={"name": "Music", "path": libdir})
assert r1.status_code == 201, (r1.status_code, r1.get_json())
r2 = c.post("/api/libraries", json={"name": "Music", "path": libdir})
assert r2.status_code == 409, (r2.status_code, r2.get_json())
j = r2.get_json()
assert j.get("already_exists") is True and j.get("ok") is False, j
print(f"add_library duplicate -> {r2.status_code} (already_exists={j['already_exists']}) OK")

print("\nALL RECENT-SESSION FIX PROBES PASSED")
