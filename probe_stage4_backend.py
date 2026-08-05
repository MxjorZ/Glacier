"""Probe: Stage 4 backend features — error center, operations history, quick
scan / change detection, genres, and the paged track table."""
import os
import sys
import time
import json
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from glacier_backend import settings as settings_mod
from glacier_backend import errors as errors_mod
from glacier_backend import operations as operations_mod
from glacier_backend.app import create_app
from glacier_backend.library import scanner as scanner_mod


def _minimal_flac(path):
    import struct
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sr, ch, bps = 44100, 2, 16
    combined = sr << 44 | (ch - 1) << 41 | (bps - 1) << 36
    si = struct.pack(">HH3s3sQ", 4096, 4096, b"\x00" * 3, b"\x00" * 3, combined) + bytes(16)
    header = bytes([0x80]) + struct.pack(">I", len(si))[1:]
    with open(path, "wb") as fh:
        fh.write(b"fLaC" + header + si)


def _flac(path, artist, album, title, track, genre="Rock"):
    from mutagen.flac import FLAC
    _minimal_flac(path)
    f = FLAC(path)
    f["artist"] = [artist]; f["albumartist"] = [artist]
    f["album"] = [album]; f["title"] = [title]
    f["tracknumber"] = [str(track)]; f["genre"] = [genre]
    f.save()
    return path


def main():
    tmp = tempfile.mkdtemp(prefix="glacier_stage4_")
    lib = os.path.join(tmp, "lib")
    _flac(os.path.join(lib, "ArtistA", "AlbumX", "01 - Song.flac"),
          "Artist A", "Album X", "Song One", 1, "Rock")
    _flac(os.path.join(lib, "ArtistA", "AlbumX", "02 - Song.flac"),
          "Artist A", "Album X", "Song Two", 2, "Metal")
    _flac(os.path.join(lib, "ArtistB", "AlbumY", "01 - Tune.flac"),
          "Artist B", "Album Y", "Tune One", 1, "Pop")

    # Isolated stores
    e_path = os.path.join(tmp, "errors.json")
    o_path = os.path.join(tmp, "ops.json")
    errors_mod.store = errors_mod.ErrorStore(path=e_path)
    operations_mod.store = operations_mod.OperationStore(path=o_path)

    settings_mod.store.replace({
        "libraries": [{"name": "Lib", "path": lib}],
        "extensions": [".flac"], "excluded_folders": [],
    })
    app = create_app(host="127.0.0.1", port=5051)
    c = app.test_client()
    libs = settings_mod.store.get()["libraries"]
    lid = libs[0]["id"]

    def wait_job(start_resp, op):
        data = start_resp.get_json() if hasattr(start_resp, "get_json") else start_resp
        jid = data.get("job", {}).get("id")
        for _ in range(40):
            time.sleep(0.1)
            hist = c.get("/api/jobs/history").get_json()["jobs"]
            for j in hist:
                if j["status"] != "running" and (jid is None or j["id"] == jid):
                    return j["result"]
        raise RuntimeError(f"job {op} did not finish")


    print("=== genres list ===")
    g = c.post("/api/genres", json={"library_id": lid}).get_json()
    assert g["ok"] and len(g["genres"]) == 3, g
    by_name = {x["genre"]: x for x in g["genres"]}
    assert by_name["Rock"]["tracks"] == 1, g
    print("genres ok:", [x["genre"] for x in g["genres"]])

    print("=== quick-scan (add/remove/modify change detection) ===")
    # First build the per-file index via a full scan through the analyze endpoint.
    wait_job(c.post("/api/run/analyze", json={}), "analyze")
    # Add a new file + modify an existing one.
    _flac(os.path.join(lib, "ArtistC", "AlbumZ", "01 - New.flac"),
          "Artist C", "Album Z", "New Track", 1, "Jazz")
    from mutagen.flac import FLAC
    f = FLAC(os.path.join(lib, "ArtistA", "AlbumX", "01 - Song.flac"))
    f["genre"] = ["Blues"]; f.save()
    q = wait_job(c.post("/api/run/quick-scan", json={"library_ids": [lid]}), "quick-scan")
    print("quick-scan raw:", json.dumps(q, default=str)[:500])
    assert q["ok"], q
    lres = q["libraries"][lid]
    assert lres["new"], "expected a new file detected"
    print("quick-scan changes -> new:", len(lres["new"]), "modified:", len(lres["modified"]))

    print("=== genres after quick-scan ===")
    g2 = c.post("/api/genres", json={"library_id": lid}).get_json()
    assert "Blues" in [x["genre"] for x in g2["genres"]], g2
    print("Blues present, genres count:", len(g2["genres"]))

    print("=== tracks paged table ===")
    t = c.post("/api/tracks", json={"library_id": lid, "page": 1, "per_page": 2,
                                    "sort": "title", "order": "asc"}).get_json()
    assert t["ok"] and t["total"] == 4 and len(t["items"]) == 2, t
    tq = c.post("/api/tracks", json={"library_id": lid, "page": 1, "per_page": 50,
                                     "query": "Artist A"}).get_json()
    assert tq["total"] == 2, tq
    print(f"tracks total={t['total']} page1={len(t['items'])} filtered={tq['total']}")

    print("=== genre merge + delete ===")
    m = wait_job(c.post("/api/run/genres/merge", json={"library_id": lid, "from": ["Rock", "Metal"], "to": "Heavy"}), "genres")
    d = wait_job(c.post("/api/run/genres/delete", json={"library_id": lid, "genre": "Pop"}), "genres")
    g3 = c.post("/api/genres", json={"library_id": lid}).get_json()
    names = [x["genre"] for x in g3["genres"]]
    assert "Heavy" in names and "Rock" not in names and "Pop" not in names, names
    print("merged+deleted genres:", names)

    print("=== errors + operations endpoints ===")
    errors_mod.store.add("Test error", "boom", module="probe", severity="error")
    er = c.get("/api/errors").get_json()
    assert any(e["title"] == "Test error" for e in er["errors"]), er
    assert er["errors"][0]["module"] == "probe"
    ce = c.delete("/api/errors").get_json()
    assert ce["errors"] == []
    ops = c.get("/api/operations").get_json()
    assert ops["ok"] and any(o["operation"] == "quick-scan" for o in ops["operations"]), ops
    sample = ops["operations"][0]
    assert "duration" in sample and "ts" in sample, sample
    print(f"operations recorded: {[o['operation'] for o in ops['operations'][:6]]}")

    print("\nALL STAGE 4 BACKEND PROBES PASSED")


if __name__ == "__main__":
    main()
