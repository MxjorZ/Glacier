"""Filesystem scanner and analysis.

Scans one or more libraries, reads metadata for every supported audio file,
computes library statistics, and persists an inventory cache per library so
downstream operations (organize, duplicates, exclusivity, cleanup) do not
re-read every file.

Design (optimized for large FLAC libraries):
  * ONE directory walk per scan. The walk itself produces the file index
    (path -> size/mtime), which doubles as the change-detection snapshot, the
    fingerprint, and the progress denominator. The old implementation walked
    the tree up to 4 times per scan.
  * PARALLEL metadata reads. FLAC parsing is I/O + CPU bound and releases the
    GIL inside mutagen's C bits, so a small worker pool gives a large speedup
    on spinning disks and big libraries.
  * INCREMENTAL scans. When the cache index matches the fresh walk, unchanged
    files are served from the in-memory/disk cache and only new/modified
    files are read. A full re-read is never forced unless the user asks.
  * IN-MEMORY cache layer in front of the JSON file so hot operations
    (stats, tracks table, duplicates) don't re-parse a 50k-entry JSON.
  * ATOMIC cache writes (tmp + rename) so a crash can't leave a truncated
    cache that silently resets the library.

Cache files live under ``~/.glacier_cache/<library_id>.json``.
"""

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import metadata
from .. import events
from ..cancel import is_cancelled, JobCancelled

CACHE_DIR = Path.home() / ".glacier_cache"
_io_lock = threading.Lock()          # serializes cache file IO
_mem_cache = {}                       # lib_id -> full cache entry dict
_mem_lock = threading.Lock()

# Metadata worker count: file parsing parallelizes well; too many workers just
# thrashes the disk queue. Capped so huge libraries don't spawn 100 threads.
MAX_METADATA_WORKERS = max(2, min(16, (os.cpu_count() or 4) // 2))


# ---------------------------------------------------------------------------
# Index walk — one pass, no double stat
# ---------------------------------------------------------------------------

def _walk_index(root, extensions, excluded_lower, want_stats=True):
    """Walk ``root`` once and return {path: (size, mtime)} for audio files.

    Raises ``JobCancelled`` when the user terminates the job. This is the
    single source of truth for scanning, fingerprinting and change detection.
    """
    index = {}
    ext_set = set(extensions)
    for dirpath, dirnames, filenames in os.walk(root):
        if is_cancelled():
            raise JobCancelled()
        dirnames[:] = [
            d for d in dirnames
            if d.lower() not in excluded_lower and not d.startswith(".")
        ]
        for name in filenames:
            if os.path.splitext(name)[1].lower() not in ext_set:
                continue
            full = os.path.normpath(os.path.join(dirpath, name))
            try:
                if want_stats:
                    st = os.stat(full)
                    # ns-resolution mtime: a re-tag that keeps the file size
                    # and lands in the same second still gets detected.
                    index[full] = (st.st_size, st.st_mtime_ns)
                else:
                    index[full] = None
            except OSError:
                continue
    return index


def _fingerprint_from_index(index):
    """Stable fingerprint of the walked tree (order-independent)."""
    total_size = 0
    total_mtime = 0
    for size, mtime in index.values():
        total_size += size or 0
        total_mtime += mtime or 0
    return f"{len(index)}:{total_size}:{total_mtime}"


# ---------------------------------------------------------------------------
# Cache IO (in-memory layer + atomic disk writes)
# ---------------------------------------------------------------------------

def _cache_path(lib_id):
    return CACHE_DIR / f"{lib_id}.json"


def _load_entry(lib_id):
    """Return the full cache entry dict for a library (memory first, disk second)."""
    with _mem_lock:
        if lib_id in _mem_cache:
            return _mem_cache[lib_id]
    with _io_lock:
        try:
            with open(_cache_path(lib_id), "r", encoding="utf-8") as fh:
                entry = json.load(fh)
        except Exception:
            entry = {}
    with _mem_lock:
        _mem_cache[lib_id] = entry
    return entry


def load_cache(lib_id):
    """Return the cached track list for a library (no scan)."""
    return _load_entry(lib_id).get("tracks", [])


def save_cache(lib_id, fingerprint, tracks, index=None):
    """Persist a cache entry atomically and refresh the in-memory copy."""
    entry = {
        "fingerprint": fingerprint,
        "tracks": tracks,
        "index": {p: list(sig) if sig else None for p, sig in (index or {}).items()},
        "track_count": len(tracks),
    }
    payload = json.dumps(entry, ensure_ascii=False)
    with _mem_lock:
        _mem_cache[lib_id] = entry
    with _io_lock:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = _cache_path(lib_id).with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, _cache_path(lib_id))  # atomic on NTFS & POSIX
        except Exception:
            pass


def get_cache_entry(lib_id):
    """Return the full stored cache entry dict (fingerprint + per-file index)."""
    return _load_entry(lib_id)


def invalidate_cache(lib_id=None):
    """Drop cached entries (all, or one library) — next scan re-reads from disk."""
    with _mem_lock:
        if lib_id is None:
            _mem_cache.clear()
        else:
            _mem_cache.pop(lib_id, None)


# ---------------------------------------------------------------------------
# Core scan
# ---------------------------------------------------------------------------

def _read_file(full, lib_id):
    """Read one track record; best-effort, never raises."""
    try:
        rec = metadata.read(full)
        st = os.stat(full)
        rec["size"] = st.st_size
        rec["mtime"] = st.st_mtime_ns
    except Exception as exc:  # noqa: BLE001
        rec = {"path": full, "format": None, "tags": {}, "error": str(exc),
               "library_id": lib_id, "size": 0, "mtime": 0}
    rec["path"] = full
    rec["library_id"] = lib_id
    return rec


def _read_files_parallel(paths, lib_id, lib_name, emit):
    """Read metadata for many files in parallel with progress + cancellation."""
    tracks = {}
    total = len(paths)
    done = 0
    if not total:
        return []
    if emit:
        events.progress(0, total, f"Reading metadata: {lib_name}")
    with ThreadPoolExecutor(max_workers=MAX_METADATA_WORKERS) as pool:
        futures = {pool.submit(_read_file, p, lib_id): p for p in paths}
        try:
            for fut in as_completed(futures):
                if is_cancelled():
                    raise JobCancelled()
                rec = fut.result()
                tracks[rec["path"]] = rec
                done += 1
                if emit and (done % 100 == 0 or done == total):
                    events.progress(done, total, f"Reading metadata: {lib_name}")
        except JobCancelled:
            for f in futures:
                f.cancel()
            raise
    # Preserve the caller's path order.
    return [tracks[p] for p in paths if p in tracks]


def scan_library(lib, extensions, excluded, emit=True, use_cache=True,
                 force_reread=False):
    """Scan a single library dict and return a list of track records.

    ``use_cache=True`` reuses cached records for files whose (size, mtime)
    signature is unchanged; only new/modified files are actually read.
    ``force_reread=True`` bypasses the cache and re-reads every file
    (previously the default — now only used when explicitly requested).
    """
    root = lib["path"]
    if not root or not os.path.isdir(root):
        raise FileNotFoundError(f"Library path does not exist: {root}")

    lib_id = lib["id"]
    excluded_lower = {e.lower() for e in excluded if e}

    # ONE walk: this is the index, the fingerprint source, and the progress
    # denominator all at once.
    index = _walk_index(root, extensions, excluded_lower)
    fingerprint = _fingerprint_from_index(index)
    total_count = len(index)

    entry = _load_entry(lib_id) if use_cache else {}
    cached_tracks = entry.get("tracks") or []
    cached_index = entry.get("index")

    changed = set()
    if use_cache and isinstance(cached_index, dict) and cached_tracks:
        # Incremental: read only new/modified entries.
        for p, sig in index.items():
            old = cached_index.get(p)
            if old is None or tuple(old) != sig:
                changed.add(p)
        # Anything cached that vanished from disk will be dropped below.
    else:
        changed = set(index)

    if force_reread:
        changed = set(index)

    cached_by_path = {t["path"]: t for t in cached_tracks}
    paths_sorted = sorted(index)

    if emit:
        events.progress(0, total_count, f"Scanning {lib['name']}")

    # Read only what changed, in parallel.
    new_by_path = {r["path"]: r for r in _read_files_parallel(
        sorted(changed), lib_id, lib.get("name", ""), emit)}

    tracks = []
    for p in paths_sorted:
        if p in changed:
            rec = new_by_path.get(p)
        else:
            rec = cached_by_path.get(p)
        if rec is not None:
            tracks.append(rec)

    save_cache(lib_id, fingerprint, tracks, index=index)
    if emit:
        events.progress(total_count, total_count, f"Scanning {lib['name']}")
        if changed:
            events.log(f"Scanned {lib['name']}: {len(tracks)} tracks "
                       f"({len(changed)} re-read, {len(tracks) - len(changed)} from cache)",
                       "success")
        else:
            events.log(f"Scanned {lib['name']}: {len(tracks)} tracks (cache hit)",
                       "success")
    return tracks


# ---------------------------------------------------------------------------
# Quick scan (change detection only)
# ---------------------------------------------------------------------------

def detect_changes(lib, extensions, excluded):
    """Fast change detection for one library (one walk).

    Returns a summary with changes grouped by type:
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
    current = _walk_index(root, extensions, excluded_lower)

    prior_keys = set(prior)
    current_keys = set(current)
    new = sorted(current_keys - prior_keys)
    deleted = sorted(prior_keys - current_keys)
    shared = prior_keys & current_keys
    modified = sorted(p for p in shared
                      if tuple(prior[p]) != tuple(current[p]))
    renamed = 0
    # Heuristic: a deleted path whose (size, mtime) matches a new path is likely a
    # rename. Cheap and gives useful feedback without hashing file contents.
    deleted_by_fp = {}
    for p in deleted:
        sig = tuple(prior[p])
        deleted_by_fp.setdefault(sig, []).append(p)
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

    Falls back to a full ``scan_library`` when there is no usable index yet
    (first scan), so the index gets built. Reuses scan_library's incremental
    machinery — one walk, parallel reads of only what changed.
    """
    root = lib["path"]
    if not root or not os.path.isdir(root):
        raise FileNotFoundError(f"Library path does not exist: {root}")

    entry = get_cache_entry(lib["id"])
    changes = detect_changes(lib, extensions, excluded)

    if changes.get("full_scan"):
        tracks = scan_library(lib, extensions, excluded, emit=emit, use_cache=True)
        return {"library": lib["name"], "full_scan": True,
                "new": [], "deleted": [], "modified": [], "renamed": 0,
                "unchanged": len(tracks), "tracks": len(tracks), "processed": len(tracks)}

    if not (changes["new"] or changes["modified"] or changes["deleted"]):
        return {"library": lib["name"], "full_scan": False,
                **{k: changes[k] for k in ("new", "deleted", "modified",
                                           "renamed", "unchanged")},
                "tracks": len(entry.get("tracks") or []),
                "processed": 0}

    tracks = scan_library(lib, extensions, excluded, emit=emit, use_cache=True)

    deleted = changes["deleted"]
    return {"library": lib["name"], "full_scan": False,
            **{k: changes[k] for k in ("new", "modified", "renamed", "unchanged")},
            "deleted": deleted,
            "tracks": len(tracks),
            "processed": len(changes["new"]) + len(changes["modified"])}


# ---------------------------------------------------------------------------
# Inventory + stats
# ---------------------------------------------------------------------------

def get_inventory(lib, extensions, excluded):
    """Return the inventory for one library, scanning if there is no valid cache."""
    try:
        return scan_library(lib, extensions, excluded, emit=False, use_cache=True)
    except Exception:
        return scan_library(lib, extensions, excluded, emit=False, use_cache=False)


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
