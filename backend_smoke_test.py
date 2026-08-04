"""Functional smoke test for the Glacier backend.

Creates temporary FLAC/MP3 libraries (with real tags), configures an isolated
settings store, and exercises the core operations end to end.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from glacier_backend import settings as settings_mod
from glacier_backend.library import scanner, organizer, exclusivity, duplicates
from glacier_backend.tags import editor as tag_editor
from glacier_backend.cleanup import cleaner
from glacier_backend.reports import exporter
from glacier_backend.app import create_app


def _minimal_flac(path):
    """Write a minimal, valid empty FLAC stream so mutagen can open it."""
    import struct
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sample_rate, channels, bps = 44100, 2, 16
    combined = sample_rate << 44 | (channels - 1) << 41 | (bps - 1) << 36
    streaminfo = (struct.pack(">HH3s3sQ", 4096, 4096, b"\x00" * 3, b"\x00" * 3, combined)
                  + bytes(16))
    header = bytes([0x80]) + struct.pack(">I", len(streaminfo))[1:]
    with open(path, "wb") as fh:
        fh.write(b"fLaC" + header + streaminfo)


def _flac(path, artist, album, title, track, year="2020", isrc=""):
    from mutagen.flac import FLAC
    _minimal_flac(path)
    f = FLAC(path)
    f["artist"] = [artist]
    f["albumartist"] = [artist]
    f["album"] = [album]
    f["title"] = [title]
    f["tracknumber"] = [str(track)]
    f["date"] = [year]
    if isrc:
        f["isrc"] = [isrc]
    f.save()
    return path


def _mp3(path, artist, album, title, track, year="2021"):
    from mutagen.id3 import ID3, TIT2, TPE1, TPE2, TALB, TRCK, TDRC
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # MPEG-1 Layer III, 128 kbps, 44.1 kHz, stereo; frame size = 417 bytes.
    header = b"\xff\xfb\x90\x00"
    frame = header + (b"\x00" * (417 - len(header)))
    with open(path, "wb") as fh:
        for _ in range(30):
            fh.write(frame)
    tags = ID3()
    tags.delall("TIT2"); tags.delall("TPE1"); tags.delall("TPE2")
    tags.delall("TALB"); tags.delall("TRCK"); tags.delall("TDRC")
    tags.add(TIT2(encoding=3, text=[title]))
    tags.add(TPE1(encoding=3, text=[artist]))
    tags.add(TPE2(encoding=3, text=[artist]))
    tags.add(TALB(encoding=3, text=[album]))
    tags.add(TRCK(encoding=3, text=[str(track)]))
    tags.add(TDRC(encoding=3, text=[year]))
    tags.save(path)
    return path




def main():
    tmp = tempfile.mkdtemp(prefix="glacier_test_")
    lib_a = os.path.join(tmp, "lib_a")
    lib_b = os.path.join(tmp, "lib_b")
    os.makedirs(lib_a)
    os.makedirs(lib_b)

    # Library A (FLAC): 2-song album + 1 internal duplicate + an empty folder.
    duf = _flac(os.path.join(lib_a, "ArtistA", "AlbumX", "01 - Song.flac"),
                "Artist A", "Album X", "Song One", 1)
    _flac(os.path.join(lib_a, "ArtistA", "AlbumX", "02 - Song.flac"),
          "Artist A", "Album X", "Song Two", 2)
    _flac(os.path.join(lib_a, "ArtistA", "Old", "Song One.flac"),
          "Artist A", "Album X", "Song One", 1)
    os.makedirs(os.path.join(lib_a, "ArtistA", "EmptyFolder"), exist_ok=True)

    # Library B (MP3): same identity as a Library A track -> exclusivity violation.
    _mp3(os.path.join(lib_b, "ArtistA", "AlbumX", "01 - Song One.mp3"),
         "Artist A", "Album X", "Song One", 1)

    # --- isolated settings store ---
    settings_path = Path(tmp) / "settings.json"
    settings_mod.store._path = settings_path
    settings_mod.store.load()
    settings_mod.store.replace({
        "libraries": [
            {"name": "Lib A", "path": lib_a},
            {"name": "Lib B", "path": lib_b},
        ],
        "extensions": [".flac", ".mp3"],
        "excluded_folders": ["playlists"],
        "folder_pattern": "{albumartist}/{album} ({year})",
        "naming_pattern": "{artist} - {album} - {track:02d} - {title}",
        "exclusivity": {"identity": "auto", "default_policy": "report_only",
                        "preferred_library_id": ""},
    })

    print("=== scanner ===")
    libs = settings_mod.store.get()["libraries"]
    inv_a = scanner.scan_library(libs[0], [".flac", ".mp3"], ["playlists"],
                                 emit=False, use_cache=False)
    assert len(inv_a) == 3, f"expected 3 tracks in A, got {len(inv_a)}"
    stats = scanner.build_library_stats(inv_a)
    print(f"library A: {stats['tracks']} tracks, {stats['artists']} artists, "
          f"{stats['albums']} albums")

    print("=== organize dry run ===")
    plan = organizer.plan_library(inv_a, lib_a, "{albumartist}/{album} ({year})",
                                  "{artist} - {album} - {track:02d} - {title}")
    print(f"organize plan entries: {len(plan)} (expected 1: the unorganized file)")
    for p in plan:
        print("  ", p["source_name"], "->", os.path.relpath(p["destination"], lib_a))

    print("=== in-library duplicates ===")
    groups = duplicates.detect_inventory(inv_a, "auto")
    assert len(groups) == 1 and groups[0]["count"] == 2, groups
    print(f"duplicate groups: {len(groups)}, first has {groups[0]['count']} tracks")

    print("=== cross-library exclusivity ===")
    inv_b = scanner.scan_library(libs[1], [".flac", ".mp3"], ["playlists"],
                                 emit=False, use_cache=False)
    viol = exclusivity.scan_violations(
        {libs[0]["id"]: inv_a, libs[1]["id"]: inv_b}, "auto", "")
    assert len(viol) == 1, f"expected 1 violation, got {len(viol)}"
    print(f"violations: {len(viol)}, tracks involved: {viol[0]['count']}")

    print("=== tags ===")
    read = tag_editor.read_batch([duf])
    assert read[0]["tags"]["artist"] == "Artist A"
    applied, errs = tag_editor.apply([duf], "genre", "Electronic")
    assert applied == 1 and not errs
    read2 = tag_editor.read_batch([duf])
    assert read2[0]["tags"]["genre"] == "Electronic"
    print("write+read genre:", read2[0]["tags"]["genre"])

    print("=== cleanup ===")
    empty = cleaner.find_empty_folders(lib_a, ["playlists"])
    print("empty folders found:", len(empty))

    print("=== covers & playlists ===")
    c_count, _e = exporter.extract_covers(inv_a)
    p_count, _e2 = exporter.generate_playlists(inv_a)
    print(f"covers: {c_count}, playlists: {p_count}")

    print("=== resolver (keep_best_quality) ===")
    res = exclusivity.resolve_group(viol[0], "keep_best_quality", "")
    keep_fmt = [t["format"] for t in res["keep"]]
    print("keep formats:", keep_fmt, "action:", res["action"])
    assert keep_fmt == ["flac"]

    print("=== API client ===")
    app = create_app(host="127.0.0.1", port=5050)
    c = app.test_client()
    assert c.get("/api/system").get_json()["name"] == "Glacier"
    assert len(c.get("/api/settings").get_json()["libraries"]) == 2
    ld = c.post("/api/list-dir", json={"path": lib_a}).get_json()
    assert "dirs" in ld
    print("list-dir subdir count:", len(ld["dirs"]))

    print("\nALL BACKEND SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()

