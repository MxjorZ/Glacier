"""Filesystem scanner and analysis.

Scans one or more libraries, reads metadata for every supported audio file,
computes library statistics, and persists an inventory cache per library so
downstream operations (organize, duplicates, exclusivity, cleanup) do not
re-read every file.

Cache files live under ``~/.glacier_cache/<library_id>.json`` and are keyed by
a lightweight directory fingerprint so a re-scan is only forced when the tree
actually changes.
"""

import json
import os
from pathlib import Path
import threading

from . import metadata
from .. import events

CACHE_DIR = Path.home() / ".glacier_cache"
_lock = threading.Lock()


def _fingerprint(root, extensions, excluded):
    """Lightweight structural fingerprint: sum of (name,size,mtime) of matches."""
    total = 0
    count = 0
    excluded_lower = {e.lower() for e in excluded if e}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d.lower() not in excluded_lower and not d.startswith(".")
        ]
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext not in extensions:
                continue
            try:
                p = os.path.join(dirpath, name)
                st = os.stat(p)
                total += st.st_size + int(st.st_mtime)
                count += 1
            except OSError:
                pass
    return f"{count}:{total}"


def _cache_path(lib_id):
    return CACHE_DIR / f"{lib_id}.json"


def load_cache(lib_id):
    try:
        with open(_cache_path(lib_id), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("tracks", [])
    except Exception:
        return []


def save_cache(lib_id, fingerprint, tracks, index=None):
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(_cache_path(lib_id), "w", encoding="utf-8") as fh:
            json.dump({"fingerprint": fingerprint, "tracks": tracks, "index": index},
                      fh, ensure_ascii=False)
    except Exception:
        pass


def scan_library(lib, extensions, excluded, emit=True, use_cache=True):
    """Scan a single library dict and return a list of track records.

    If ``use_cache`` and a valid cache fingerprint matches, return cached data
    immediately.
    """
    root = lib["path"]
    if not root or not os.path.isdir(root):
        raise FileNotFoundError(f"Library path does not exist: {root}")

    excluded_lower = {e.lower() for e in excluded if e}
    fp = _fingerprint(root, extensions, excluded_lower)
    if use_cache:
        cached = load_cache(lib["id"])
        if cached:
            try:
                with open(_cache_path(lib["id"]), "r", encoding="utf-8") as fh:
                    entry = json.load(fh)
                if entry.get("fingerprint") == fp:
                    return cached
            except Exception:
                pass

    tracks = []
    total_count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d.lower() not in excluded_lower and not d.startswith(".")
        ]
        for name in filenames:
            if os.path.splitext(name)[1].lower() in extensions:
                total_count += 1

    processed = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d.lower() not in excluded_lower and not d.startswith(".")
        ]
        for name in filenames:
            full = os.path.join(dirpath, name)
            if os.path.splitext(name)[1].lower() not in extensions:
                continue
            processed += 1
            try:
                st = os.stat(full)
                rec = metadata.read(full)
                rec["path"] = full
                rec["library_id"] = lib["id"]
                rec["size"] = st.st_size
                rec["mtime"] = st.st_mtime
            except Exception as exc:  # noqa: BLE001
                rec = {
                    "path": full, "format": None, "tags": {}, "error": str(exc),
                    "library_id": lib["id"], "size": 0, "mtime": 0,
                }
            tracks.append(rec)
            if emit:
                events.log(f"Loaded: {full}", "verbose")
            if emit and processed % 50 == 0:
                events.progress(processed, total_count, f"Scanning {lib['name']}")
                events.log(f"{lib['name']}: {processed}/{total_count}", "info")

    save_cache(lib["id"], fp, tracks,
               index={t["path"]: (t.get("size", 0), int(t.get("mtime") or 0))
                      for t in tracks})
    if emit:
        events.progress(total_count, total_count, f"Scanning {lib['name']}")
        events.log(f"Scanned {lib['name']}: {len(tracks)} tracks", "success")
    return tracks


def build_library_stats(tracks):
    """Compute per-library / aggregate statistics for a list of tracks."""
    artists = set()
    albums = set()
    by_ext = {}
    total_size = 0
    bitrates = []
    durations = []
    for t in tracks:
        total_size += t.get("size", 0)
        fmt = t.get("format") or "unknown"
        by_ext[fmt] = by_ext.get(fmt, 0) + 1
        tags = t.get("tags", {})
        if tags.get("artist"):
            artists.add(tags["artist"].strip().lower())
        if tags.get("album"):
            key = (tags.get("albumartist") or tags.get("artist") or "",
                   tags["album"]).__repr__()
            albums.add(key)
        if t.get("bitrate"):
            bitrates.append(t["bitrate"])
        if t.get("duration"):
            durations.append(t["duration"])

    total_sec = sum(durations)
    return {
        "tracks": len(tracks),
        "artists": len(artists),
        "albums": len(albums),
        "size": total_size,
        "extensions": dict(sorted(by_ext.items(), key=lambda kv: -kv[1])),
        "avg_bitrate": int(sum(bitrates) / len(bitrates)) if bitrates else 0,
        "duration_seconds": total_sec,
        "errors": sum(1 for t in tracks if t.get("error")),
        "has_cover": sum(1 for t in tracks if t.get("has_cover")),
    }


def get_cache_entry(lib_id):
    """Return the full stored cache entry dict (fingerprint + per-file index)."""
    try:
        with open(_cache_path(lib_id), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _index_files(root, extensions, excluded_lower):
    """Walk a tree and return {path: (size, mtime)} for matching audio files."""
    index = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d.lower() not in excluded_lower and not d.startswith(".")
        ]
        for name in filenames:
            if os.path.splitext(name)[1].lower() not in extensions:
                continue
            p = os.path.join(dirpath, name)
            try:
                st = os.stat(p)
                index[p] = (st.st_size, int(st.st_mtime))
            except OSError:
                pass
    return index


def detect_changes(lib, extensions, excluded):
    """Fast change detection for one library.

    Compares the current on-disk tree against the stored per-file index (path ->
    size/mtime). Returns a summary with changes grouped by type:
      new, deleted, modified, renamed, unchanged — plus whether the cache is
      usable at all (first scan when there is no prior index).
    """
    root = lib["path"]
    excluded_lower = {e.lower() for e in excluded if e}
    entry = get_cache_entry(lib["id"])

    # Legacy/first-scan caches don't carry a per-file index -> full rescan needed.
    if not isinstance(entry.get("index"), dict):
        return {"full_scan": True, "new": [], "deleted": [], "modified": [],
                "renamed": 0, "unchanged": 0}

    prior = entry["index"]
    current = _index_files(root, extensions, excluded_lower)

    prior_keys = set(prior)
    current_keys = set(current)
    new = [p for p in sorted(current_keys - prior_keys)]
    deleted = [p for p in sorted(prior_keys - current_keys)]
    shared = prior_keys & current_keys
    modified = [
        p for p in sorted(shared)
        if prior[p] != current[p]
    ]
    renamed = 0
    # Heuristic: a deleted path whose (size, mtime) matches a new path is likely a
    # rename. Cheap and gives useful feedback without hashing file contents.
    deleted_by_fp = {}
    for p in deleted:
        sig = prior[p]
        if sig not in deleted_by_fp:
            deleted_by_fp[sig] = []
        deleted_by_fp[sig].append(p)
    for p in new:
        sig = current[p]
        if sig in deleted_by_fp and deleted_by_fp[sig]:
            renamed += 1
            deleted_by_fp[sig].pop(0)

    return {
        "full_scan": False,
        "new": new,
        "deleted": deleted,
        "modified": modified,
        "renamed": renamed,
        "unchanged": len(shared) - len(modified),
    }


def quick_scan(lib, extensions, excluded, emit=True):
    """Fast startup-style scan: only process changed files.

    Returns a dict describing what was changed and (re)read. When there is no
    usable per-file index yet (or a full scan is demanded), falls back to a full
    ``scan_library`` so the index is built/refreshed.
    """
    root = lib["path"]
    if not root or not os.path.isdir(root):
        raise FileNotFoundError(f"Library path does not exist: {root}")

    excluded_lower = {e.lower() for e in excluded if e}
    entry = get_cache_entry(lib["id"])
    changes = detect_changes(lib, extensions, excluded)

    if changes.get("full_scan") or not (changes["new"] or changes["modified"] or changes["deleted"]):
        # Nothing changed or no index -> return the change summary without work.
        return {"library": lib["name"], "full_scan": changes.get("full_scan", False),
                **{k: changes[k] for k in ("new", "deleted", "modified", "renamed", "unchanged")},
                "processed": 0}

    # Only re-read metadata for new + modified files; keep the rest cached.
    cached = entry.get("tracks", [])
    by_path = {t["path"]: t for t in cached}
    changed_paths = set(changes["new"]) | set(changes["modified"])
    total = len(changed_paths)
    processed = 0
    for p in sorted(changed_paths):
        processed += 1
        try:
            st = os.stat(p)
            rec = metadata.read(p)
            rec["path"] = p
            rec["library_id"] = lib["id"]
            rec["size"] = st.st_size
            rec["mtime"] = st.st_mtime
        except Exception as exc:  # noqa: BLE001
            rec = {"path": p, "format": None, "tags": {}, "error": str(exc),
                   "library_id": lib["id"], "size": 0, "mtime": 0}
        by_path[p] = rec
        if emit and processed % 50 == 0:
            events.progress(processed, total, f"Updating {lib['name']}")

    # Drop entries that no longer exist on disk.
    new_tracks = [by_path[p] for p in sorted(by_path) if os.path.exists(p)]
    fp = _fingerprint(root, extensions, excluded_lower)
    save_cache(lib["id"], fp, new_tracks, index=_index_files(root, extensions, excluded_lower))
    if emit:
        events.progress(total, total, f"Updating {lib['name']}")
        events.log(
            f"Quick scan '{lib['name']}': {len(new_tracks)} tracks "
            f"({len(changes['new'])} new, {len(changes['modified'])} modified, "
            f"{len(changes['deleted'])} removed, {len(changes['deleted']) - 0} stale)",
            "success")
    return {"library": lib["name"], "full_scan": False,
            **{k: changes[k] for k in ("new", "deleted", "modified", "renamed", "unchanged")},
            "tracks": len(new_tracks), "processed": processed}


def get_inventory(lib, extensions, excluded):
    """Return the inventory for one library, scanning if there is no valid cache."""
    try:
        return scan_library(lib, extensions, excluded, emit=False, use_cache=True)
    except Exception:
        return scan_library(lib, extensions, excluded, emit=False, use_cache=False)


