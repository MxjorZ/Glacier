"""Glacier REST API routes.

These routes are registered on the Flask app by ``app.py``. Heavy operations
are dispatched through the job supervisor so the SSE stream and UI stay
responsive and only one filesystem-heavy job runs at a time.

Every destructive operation (organize apply, exclusivity resolution, cleanup
apply) requires an explicit ``confirm`` flag — Glacier never silently changes
files.
"""

import os
import shutil
import time
import re

from flask import request, jsonify, Response, stream_with_context

from . import config
from . import events
from . import errors as errors_store
from . import operations as operations_store
from .jobs import supervisor
from .settings import store
from . import browser
from .library import scanner, organizer, duplicates as dup_mod, exclusivity, extract
from .library.exclusivity import normalize
from .library import audio_analysis
from .tags import editor as tag_editor
from .tags import genres as genre_ops
from .cleanup import cleaner
from .reports import exporter
from .plex import client as plex_client
from .plex import sync as plex_sync
from . import mover
from .cancel import is_cancelled, JobCancelled


def _libs():
    return store.get()["libraries"]


def _enabled_libs():
    return [l for l in _libs() if l.get("enabled", True) is not False]


def _settings():
    return store.get()


def _json_body():
    return request.get_json(silent=True) or {}


def _plex_creds(body):
    s = store.get().get("plex", {})
    url = (body.get("url") or s.get("url") or "").strip()
    token = (body.get("token") or s.get("token") or "").strip()
    section = (body.get("section") or s.get("music_section") or "").strip()
    return url, token, section


def _volatile(**kw):
    return jsonify(kw)


# --- Operation callbacks (run inside the job supervisor) ----------------

def op_analyze(library_ids=None):
    """Scan libraries. Incremental: unchanged files are served from the
    inventory cache; only new/modified files are re-read (the old behavior
    forced a full re-read of every file on every scan)."""
    settings = store.get()
    libs = _libs()
    if library_ids:
        libs = [l for l in libs if l["id"] in library_ids]
    else:
        libs = _enabled_libs()
    if not libs:
        raise ValueError("No libraries configured")
    events.progress(0, len(libs), "Scanning libraries")
    per_library = {}
    all_tracks = []
    ext = settings["extensions"]
    excl = settings["excluded_folders"]
    for i, lib in enumerate(libs):
        if not os.path.isdir(lib["path"]):
            events.log(f"Skipping missing path: {lib['path']}", "warning")
            per_library[lib["id"]] = {"error": "missing path"}
            continue
        tracks = scanner.scan_library(lib, ext, excl, emit=True, use_cache=True)
        all_tracks.extend(tracks)
        st = scanner.build_library_stats(tracks)
        per_library[lib["id"]] = {
            "name": lib["name"], "path": lib["path"],
            "total_tracks": len(tracks),
            "size": st["size"],
            "stats": st,
        }
        store.set_scan(lib["id"], {
            "at": time.time(),
            "tracks": len(tracks),
            "errors": st["errors"],
        })
        events.progress(i + 1, len(libs), "Scanning libraries")
    totals = scanner.build_library_stats(all_tracks)
    events.log(
        f"Analysis complete: {totals['tracks']} tracks across {len(libs)} libraries",
        "success")
    browser.invalidate_counts()
    return {"ok": True, "libraries": per_library, "total": totals}


def op_quick_scan(library_ids=None):
    settings = store.get()
    libs = _libs()
    if library_ids:
        libs = [l for l in libs if l["id"] in library_ids]
    else:
        libs = _enabled_libs()
    if not libs:
        raise ValueError("No libraries configured")
    per_library = {}
    ext = settings["extensions"]
    excl = settings["excluded_folders"]
    for lib in libs:
        if not os.path.isdir(lib["path"]):
            events.log(f"Skipping missing path: {lib['path']}", "warning")
            per_library[lib["id"]] = {"error": "missing path"}
            continue
        try:
            result = scanner.quick_scan(lib, ext, excl, emit=True)
            per_library[lib["id"]] = result
            st = scanner.build_library_stats(scanner.load_cache(lib["id"]))
            store.set_scan(lib["id"], {
                "at": time.time(),
                "tracks": st["tracks"],
                "errors": st["errors"],
            })
        except Exception as exc:
            events.log(f"Quick scan failed for '{lib['name']}': {exc}", "error")
            errors_store.store.report_exception(
                f"Quick scan failed for '{lib['name']}'", module="scanner")
            per_library[lib["id"]] = {"error": str(exc)}
    total_new = sum(len(r.get("new", [])) for r in per_library.values()
                    if isinstance(r, dict))
    total_deleted = sum(len(r.get("deleted", [])) for r in per_library.values()
                         if isinstance(r, dict))
    events.log(
        f"Quick scan complete: {total_new} new, {total_deleted} removed "
        f"across {len(libs)} libraries", "success")
    browser.invalidate_counts()
    return {"ok": True, "libraries": per_library, "total_new": total_new,
            "total_deleted": total_deleted}


def op_startup_scan():
    try:
        return op_quick_scan(None)
    except Exception as exc:
        events.log(f"Startup scan failed: {exc}", "warning")
        return {"ok": True, "skipped": True, "error": str(exc)}


def _library_tracks(library_id, settings, force=False):
    lib = store.get_library(library_id)
    if not lib:
        raise ValueError("Unknown library")
    lib_settings = settings or store.get()
    # force=True re-reads every file; the default is the incremental cache.
    tracks = scanner.scan_library(
        lib, lib_settings["extensions"], lib_settings["excluded_folders"],
        emit=False, use_cache=True, force_reread=force)
    return lib, tracks


def _refresh_cache(lib):
    s = store.get()
    try:
        scanner.scan_library(lib, s["extensions"], s["excluded_folders"],
                             emit=False, use_cache=True)
    except Exception:
        pass


def op_genre_replace(library_id, from_genre, to_genre):
    lib, tracks = _library_tracks(library_id, store.get())
    paths = [t["path"] for t in tracks]
    applied, skipped, errors = genre_ops.replace(paths, from_genre, to_genre)
    if applied:
        _refresh_cache(lib)
    events.log(f"Genre replace '{from_genre}' -> '{to_genre}' "
               f"in '{lib['name']}': {applied} updated, {skipped} unchanged", "success")
    return {"ok": True, "library": lib["name"], "applied": applied,
            "skipped": skipped, "errors": errors}


def op_genre_merge(library_id, from_genres, to_genre):
    lib, tracks = _library_tracks(library_id, store.get())
    paths = [t["path"] for t in tracks]
    applied, skipped, errors = genre_ops.merge(paths, from_genres, to_genre)
    if applied:
        _refresh_cache(lib)
    events.log(f"Genre merge into '{to_genre}' in '{lib['name']}': "
               f"{applied} updated, {skipped} unchanged", "success")
    return {"ok": True, "library": lib["name"], "applied": applied,
            "skipped": skipped, "errors": errors}


def op_genre_delete(library_id, genre):
    lib, tracks = _library_tracks(library_id, store.get())
    paths = [t["path"] for t in tracks]
    applied, skipped, errors = genre_ops.delete(paths, genre)
    if applied:
        _refresh_cache(lib)
    events.log(f"Genre remove '{genre}' in '{lib['name']}': "
               f"{applied} updated, {skipped} unchanged", "success")
    return {"ok": True, "library": lib["name"], "applied": applied,
            "skipped": skipped, "errors": errors}


def op_genre_bulk_set(library_id, value):
    lib, tracks = _library_tracks(library_id, store.get())
    paths = [t["path"] for t in tracks]
    applied, skipped, errors = genre_ops.bulk_set(paths, value)
    if applied:
        _refresh_cache(lib)
    events.log(f"Genre set '{value}' across '{lib['name']}': "
               f"{applied} updated, {skipped} unchanged", "success")
    return {"ok": True, "library": lib["name"], "applied": applied,
            "skipped": skipped, "errors": errors}


def op_audio_analyze(path):
    """Decode + FFT one file and return waveform/spectrum/spectrogram data."""
    events.log(f"Analyzing audio: {os.path.basename(path)}", "info")
    events.progress(0, 1, "Decoding audio")
    result = audio_analysis.analyze(path)
    events.progress(1, 1, "Analysis complete")
    if not result.get("ok"):
        raise RuntimeError(result.get("error", "Analysis failed"))
    events.log(f"Audio analysis complete: {os.path.basename(path)} "
               f"({result['duration']}s, up to {result['spectrum']['max_hz']} Hz)", "success")
    return result


def op_ffmpeg_install():
    """Install ffmpeg on the host so waveform/spectrum analysis works."""
    events.progress(0, 1, "Installing ffmpeg")
    result = audio_analysis.install_ffmpeg()
    events.progress(1, 1, "Installing ffmpeg")
    return result


# ======================================================================
# File manager – safe, library-scoped file operations
# ======================================================================

def _resolve_in_library(path, library_id=None):
    """Return (abs_path, lib) for a path inside a managed library.

    Every file-manager mutation must resolve through here: paths outside any
    library root are rejected, and path traversal out of the library is
    blocked (realpath containment check).
    """
    path = os.path.realpath(os.path.abspath(os.path.expanduser(path or "")))
    libs = _libs()
    if library_id:
        lib = store.get_library(library_id)
        if not lib:
            raise ValueError("Unknown library")
        root = os.path.realpath(lib["path"])
        if path != root and not path.startswith(root + os.sep):
            raise ValueError("Path is outside the selected library")
        return path, lib
    for lib in libs:
        root = os.path.realpath(lib["path"])
        if path == root or path.startswith(root + os.sep):
            return path, lib
    raise ValueError("Path must be inside a managed library")


def op_file_rename(path, new_name, library_id=None):
    """Rename a file or folder inside its library."""
    full, lib = _resolve_in_library(path, library_id)
    new_name = (new_name or "").strip()
    if not new_name or new_name in (".", "..") or os.sep in new_name or "/" in new_name:
        raise ValueError("Invalid new name")
    if not os.path.exists(full):
        raise FileNotFoundError("Item not found")
    dest = os.path.join(os.path.dirname(full), new_name)
    if os.path.exists(dest):
        raise ValueError("An item with that name already exists here")
    os.rename(full, dest)
    scanner.invalidate_cache(lib["id"])
    browser.invalidate_counts()
    events.log(f"Renamed: {os.path.basename(full)} -> {new_name}", "success")
    return {"ok": True, "path": dest}


def op_file_delete(paths, library_id=None, confirm=False):
    """Delete files/folders. Destructive: requires confirm, library-scoped.

    Folders are only removed when they contain nothing but non-audio files
    or are empty — the audio itself must be deleted file-by-file (explicit).
    """
    if not confirm:
        raise ValueError("Deletion requires explicit confirmation (confirm=true)")
    deleted = 0
    errors = []
    touched_libs = set()
    for i, p in enumerate(paths or []):
        if is_cancelled():
            raise JobCancelled()
        try:
            full, lib = _resolve_in_library(p, library_id)
            touched_libs.add(lib["id"])
            if os.path.isfile(full):
                os.remove(full)
                deleted += 1
            elif os.path.isdir(full):
                # Safety: refuse to remove a folder that still holds audio.
                has_audio = any(
                    os.path.splitext(f)[1].lower() in {e.lower() for e in store.get()["extensions"]}
                    for _r, _d, files in os.walk(full) for f in files)
                if has_audio:
                    errors.append({"path": p, "error": "folder still contains audio — delete files first"})
                    continue
                shutil.rmtree(full)
                deleted += 1
            else:
                errors.append({"path": p, "error": "not found"})
        except Exception as exc:  # noqa: BLE001
            errors.append({"path": p, "error": str(exc)})
        if (i + 1) % 25 == 0 or i + 1 == len(paths):
            events.progress(i + 1, len(paths), "Deleting")
    for lid in touched_libs:
        scanner.invalidate_cache(lid)
    browser.invalidate_counts()
    events.log(f"File manager: deleted {deleted} item(s)", "success")
    return {"ok": True, "deleted": deleted, "errors": errors}


def op_file_move(paths, dest_folder, library_id=None, copy=False):
    """Move (or copy) files/folders into a destination folder in a library."""
    dest, dest_lib = _resolve_in_library(dest_folder, library_id)
    if not os.path.isdir(dest):
        raise NotADirectoryError("Destination folder not found")
    plan = []
    for p in paths or []:
        full, _lib = _resolve_in_library(p, library_id)
        if not os.path.exists(full):
            continue
        target = os.path.join(dest, os.path.basename(full))
        base, ext = os.path.splitext(target)
        i = 1
        while os.path.exists(target):
            target = f"{base} ({i}){ext}"
            i += 1
        plan.append({"source": full, "destination": target})
    moved, errors = mover.execute_plan(plan, dry_run=False, copy=copy)
    for lid in {library_id, dest_lib["id"]}:
        if lid:
            scanner.invalidate_cache(lid)
    browser.invalidate_counts()
    action = "copied" if copy else "moved"
    events.log(f"File manager: {action} {moved} item(s) into {dest}", "success")
    return {"ok": True, "moved": moved, "errors": errors}


def op_file_new_folder(path, name, library_id=None):
    """Create a subfolder inside a library."""
    parent, lib = _resolve_in_library(path, library_id)
    name = (name or "").strip()
    if not name or os.sep in name or "/" in name:
        raise ValueError("Invalid folder name")
    full = os.path.join(parent, name)
    if os.path.exists(full):
        raise ValueError("A folder with that name already exists")
    os.makedirs(full)
    browser.invalidate_counts()
    events.log(f"Created folder: {full}", "success")
    return {"ok": True, "path": full}


def op_genres_list(library_id):
    lib, tracks = _library_tracks(library_id, store.get())
    genres = genre_ops.collect(tracks)
    return {"ok": True, "library": lib["name"], "library_id": library_id,
            "genres": genres, "count": len(genres)}


def op_tag_save(paths, field, value):
    """Bulk tag write as a background job (progress + cancellable)."""
    applied, errors = tag_editor.apply(paths, field, value)
    # Tags changed on disk: the mtime changed, so the next scan re-reads them
    # incrementally — no forced invalidation needed.
    events.log(f"Tag '{field}' applied to {applied}/{len(paths)} file(s)", "success")
    return {"ok": True, "applied": applied, "errors": errors,
            "count": len(paths)}


def op_tracks_page(library_id, page, per_page, sort="title", order="asc", query=""):
    lib, tracks = _library_tracks(library_id, store.get())
    query = (query or "").strip().lower()

    def has(tags, term):
        for k in ("artist", "albumartist", "album", "title", "genre"):
            if term in (tags.get(k) or "").lower():
                return True
        return False

    if query:
        tracks = [t for t in tracks
                  if not t.get("error") and has(t.get("tags", {}), query)]

    def sort_key(t):
        tags = t.get("tags", {})
        return (tags.get(sort) or "").lower() if sort in ("artist", "albumartist",
                                                           "album", "title", "genre") \
            else (t.get("path") or "")

    tracks = sorted(tracks, key=sort_key, reverse=(order == "desc"))
    total = len(tracks)
    start = (page - 1) * per_page
    page_tracks = tracks[start:start + per_page]

    items = []
    for t in page_tracks:
        tags = t.get("tags", {})
        items.append({
            "path": t["path"],
            "format": t.get("format"),
            "artist": tags.get("artist") or "",
            "albumartist": tags.get("albumartist") or "",
            "album": tags.get("album") or "",
            "title": tags.get("title") or "",
            "track": tags.get("track") or "",
            "genre": tags.get("genre") or "",
            "year": tags.get("date") or "",
            "rating": tags.get("rating") or "",
            "has_cover": bool(t.get("has_cover")),
        })
    return {"ok": True, "library_id": library_id, "library": lib["name"],
            "items": items, "total": total, "page": page, "per_page": per_page}


# ======================================================================
# Organize – uses the simple mover engine
# ======================================================================

def op_organize(library_id, dry_run, confirm=False, plan=None):
    lib = store.get_library(library_id)
    if not lib:
        raise ValueError("Unknown library")
    if not dry_run and not confirm:
        raise ValueError("Apply requires explicit confirmation (confirm=true)")
    settings = store.get()

    if plan is not None:
        events.log(f"Executing pre‑computed plan for '{lib['name']}'", "info")
        moved, errors = mover.execute_plan(
            plan, dry_run=False,
            backup=settings.get("backup_before_move", False))
        events.log(f"Organized {moved} files in '{lib['name']}'", "success")
        scanner.invalidate_cache(library_id)
        browser.invalidate_counts()
        return {"ok": True, "dry_run": False, "moved": moved, "errors": errors, "count": len(plan)}

    tracks = scanner.get_inventory(lib, settings["extensions"], settings["excluded_folders"])
    file_paths = [t['path'] for t in tracks if not t.get('error')]
    plan = mover.plan_files(
        file_paths,
        settings["folder_pattern"],
        settings["naming_pattern"],
        lib["path"],
        skip_already_organized=True,
        emit_progress=True,
        library_name=lib["name"],
    )
    if dry_run:
        events.log(f"Organize dry‑run: {len(plan)} files would move", "info")
        return {"ok": True, "dry_run": True, "count": len(plan), "plan": plan}

    moved, errors = mover.execute_plan(plan, dry_run=False,
                                       backup=settings.get("backup_before_move", False))
    events.log(f"Organized {moved} files in '{lib['name']}'", "success")
    scanner.invalidate_cache(library_id)
    browser.invalidate_counts()
    return {"ok": True, "dry_run": False, "moved": moved, "errors": errors, "count": len(plan)}


# ======================================================================
# Duplicates – unchanged
# ======================================================================

def op_duplicates(library_id):
    lib = store.get_library(library_id)
    if not lib:
        raise ValueError("Unknown library")
    settings = store.get()
    tracks = scanner.get_inventory(lib, settings["extensions"], settings["excluded_folders"])
    events.progress(0, len(tracks), f"Duplicates: {lib['name']}")
    groups = dup_mod.detect_inventory(tracks, settings["exclusivity"]["identity"])
    events.progress(len(tracks), len(tracks), f"Duplicates: {lib['name']}")
    events.log(f"Duplicate scan '{lib['name']}': {len(groups)} groups", "success")
    return {"ok": True, "library_id": library_id, "library": lib["name"],
            "groups": groups, "count": len(groups)}


def op_duplicates_resolve(library_id, policy, dry_run, confirm=False, quarantine_dir=None):
    """Act on in-library duplicate groups.

    Policies:
      keep_best_quality — keep the highest-ranked format/bitrate copy per group
      keep_newest       — keep the most recently modified copy per group
    Losers move to the quarantine folder (~/.glacier_quarantine by default),
    never deleted. Requires dry_run first + explicit confirm to apply.
    """
    if not dry_run and not confirm:
        raise ValueError("Apply requires explicit confirmation (confirm=true)")
    lib = store.get_library(library_id)
    if not lib:
        raise ValueError("Unknown library")
    settings = store.get()
    tracks = scanner.get_inventory(lib, settings["extensions"], settings["excluded_folders"])
    groups = dup_mod.detect_inventory(tracks, settings["exclusivity"]["identity"])

    quarantine = quarantine_dir or os.path.join(os.path.expanduser("~"),
                                                ".glacier_quarantine")
    plan = []
    for g in groups:
        cands = [t for t in g["tracks"] if not t.get("error")]
        if len(cands) < 2:
            continue
        if policy == "keep_newest":
            keep = max(cands, key=lambda t: t.get("mtime") or 0)
        else:
            keep = max(cands, key=lambda t: (exclusivity._quality(t),
                                             t.get("bitrate") or 0,
                                             t.get("size") or 0))
        for t in cands:
            if t is not keep:
                plan.append({"source": t["path"], "destination":
                             os.path.join(quarantine, os.path.basename(t["path"])),
                             "identity": g["identity"]})

    if dry_run:
        return {"ok": True, "dry_run": True, "count": len(plan),
                "plan": plan[:500], "total": len(plan)}

    if not plan:
        return {"ok": True, "dry_run": False, "acted": 0, "skipped": 0, "errors": []}

    moved, errors = mover.execute_plan(
        [{"source": p["source"], "destination": p["destination"]} for p in plan],
        dry_run=False)
    scanner.invalidate_cache(library_id)
    browser.invalidate_counts()
    events.log(f"Duplicate resolution: quarantined {moved} of {len(plan)} "
               f"extra copies from '{lib['name']}'", "success")
    return {"ok": True, "dry_run": False, "acted": moved,
            "skipped": len(plan) - moved, "errors": errors}


# ======================================================================
# Exclusivity scan – unchanged
# ======================================================================

def op_exclusivity(library_ids=None):
    settings = store.get()
    libs = _enabled_libs()
    if library_ids:
        libs = [l for l in libs if l["id"] in library_ids]
    events.progress(0, len(libs), "Loading inventories")
    inventories = {}
    for i, lib in enumerate(libs):
        if is_cancelled():
            raise JobCancelled()
        if os.path.isdir(lib["path"]):
            inventories[lib["id"]] = scanner.get_inventory(
                lib, settings["extensions"], settings["excluded_folders"])
        events.progress(i + 1, len(libs), "Loading inventories")
    mode = settings["exclusivity"]["identity"]
    pref = settings["exclusivity"].get("preferred_library_id", "")
    total_tracks = sum(len(t) for t in inventories.values())
    events.progress(0, total_tracks, "Comparing identities")
    violations = exclusivity.scan_violations(inventories, mode, pref)
    events.progress(total_tracks, total_tracks, "Comparing identities")
    events.log(f"Exclusivity scan: {len(violations)} violations across libraries", "success")
    return {"ok": True, "violations": violations, "count": len(violations)}


def op_artist_exclusivity(library_ids=None):
    settings = store.get()
    libs = _enabled_libs()
    if not libs:
        events.log("No enabled libraries found – using all libraries for artist scan", "warning")
        libs = _libs()
    if library_ids:
        libs = [l for l in libs if l["id"] in library_ids]
    events.progress(0, len(libs), "Loading inventories")
    inventories = {}
    for i, lib in enumerate(libs):
        if is_cancelled():
            raise JobCancelled()
        if os.path.isdir(lib["path"]):
            inventories[lib["id"]] = scanner.get_inventory(
                lib, settings["extensions"], settings["excluded_folders"])
        events.progress(i + 1, len(libs), "Loading inventories")
    events.log(f"Artist scan: found {len(inventories)} libraries, "
               f"total tracks across libraries: {sum(len(t) for t in inventories.values())}", "info")
    exceptions = settings.get("artist_exclusivity_exceptions", [])
    exceptions = [e for e in exceptions if e and e.strip()]
    total_tracks = sum(len(t) for t in inventories.values())
    events.progress(0, total_tracks, "Grouping artists")
    groups = exclusivity.scan_artist_violations(inventories, exceptions)
    events.progress(total_tracks, total_tracks, "Grouping artists")
    events.artist_exclusivity_report(len(groups))
    events.log(f"Artist exclusivity scan: {len(groups)} violation(s)", "success")
    return {"ok": True, "groups": groups, "count": len(groups)}


# ======================================================================
# Artist exclusivity resolution – uses mover with patterns
# ======================================================================

def op_artist_resolve(policy, preferred_library_id, dry_run, confirm=False, library_ids=None):
    if not dry_run and not confirm:
        raise ValueError("Apply requires explicit confirmation (confirm=true)")
    settings = store.get()
    libs = _enabled_libs()
    if not libs:
        events.log("No enabled libraries found – using all libraries for artist resolution", "warning")
        libs = _libs()
    if library_ids:
        libs = [l for l in libs if l["id"] in library_ids]
    inventories = {}
    for lib in libs:
        if os.path.isdir(lib["path"]):
            inventories[lib["id"]] = scanner.get_inventory(
                lib, settings["extensions"], settings["excluded_folders"])
    exceptions = settings.get("artist_exclusivity_exceptions", [])
    exceptions = [e for e in exceptions if e and e.strip()]
    groups = exclusivity.scan_artist_violations(inventories, exceptions)
    plans = exclusivity.resolve_artist_groups(groups, policy, preferred_library_id)
    plans = [p for p in plans if p["remove"]]

    target_lib_path = None
    if policy == "keep_preferred_library" and preferred_library_id:
        tgt = store.get_library(preferred_library_id)
        if tgt and os.path.isdir(tgt["path"]):
            target_lib_path = tgt["path"]
        else:
            events.log(f"Preferred library '{preferred_library_id}' not found or path missing", "error")
            return {"ok": True, "dry_run": dry_run, "acted": 0, "skipped": 0, "count": 0}

    if dry_run:
        dry_plan = []
        for plan in plans:
            for tr in plan["remove"]:
                src = tr.get("path")
                if not src:
                    continue
                if target_lib_path:
                    tags = mover.read_tags(src)
                    folder = mover.render_pattern(settings["folder_pattern"], tags)
                    filename = mover.render_pattern(settings["naming_pattern"], tags)
                    ext = os.path.splitext(src)[1]
                    if '{track}' not in settings["naming_pattern"] and tags.get('tracknumber'):
                        filename = f"{filename} - {tags['tracknumber']}"
                    dest = os.path.join(target_lib_path, folder, filename + ext)
                else:
                    dest = "no target library"
                dry_plan.append({"source": src, "destination": dest})
        events.log(f"Artist exclusivity dry-run: {len(dry_plan)} files would move", "info")
        return {"ok": True, "dry_run": True, "count": len(dry_plan), "plan": dry_plan}

    if not target_lib_path:
        events.log("No valid target library for moving files", "error")
        return {"ok": True, "dry_run": False, "acted": 0, "skipped": 0, "count": 0}

    source_paths = []
    for plan in plans:
        for tr in plan["remove"]:
            src = tr.get("path")
            if src and os.path.exists(src):
                source_paths.append(src)

    if not source_paths:
        events.log("No files to move", "info")
        return {"ok": True, "dry_run": False, "acted": 0, "skipped": 0, "count": 0}

    moved, errors = mover.move_files(
        source_paths,
        settings["folder_pattern"],
        settings["naming_pattern"],
        target_lib_path,
        dry_run=False,
        backup=settings.get("backup_before_move", False)
    )
    # Moves crossed libraries: drop cached inventories so the next scan sees
    # the new locations instead of serving stale paths.
    for lid in list(inventories.keys()) + [preferred_library_id]:
        scanner.invalidate_cache(lid)
    browser.invalidate_counts()
    events.log(f"Artist exclusivity applied: {moved} moved, {len(errors)} errors", "success")
    return {"ok": True, "dry_run": False, "acted": moved, "skipped": len(errors), "errors": errors}


# ======================================================================
# Library exclusivity resolution – uses mover with patterns
# ======================================================================

def op_resolve(policy, preferred_library_id, move_target_library_id,
               dry_run, confirm=False, library_ids=None):
    if not dry_run and not confirm:
        raise ValueError("Apply requires explicit confirmation (confirm=true)")
    settings = store.get()
    libs = _enabled_libs()
    if library_ids:
        libs = [l for l in libs if l["id"] in library_ids]
    inventories = {}
    for lib in libs:
        if os.path.isdir(lib["path"]):
            inventories[lib["id"]] = scanner.get_inventory(
                lib, settings["extensions"], settings["excluded_folders"])
    mode = settings["exclusivity"]["identity"]
    violations = exclusivity.scan_violations(inventories, mode, preferred_library_id)

    plans = []
    for v in violations:
        plan = exclusivity.resolve_group(v, policy, preferred_library_id, move_target_library_id)
        if plan["remove"]:
            plans.append(plan)

    effective_policy = policy
    effective_target_id = move_target_library_id

    if policy == "keep_preferred_library":
        if preferred_library_id:
            effective_policy = "move_to_library"
            effective_target_id = preferred_library_id
        else:
            events.log("keep_preferred_library requires a preferred library id", "warning")
            return {"ok": True, "dry_run": dry_run, "acted": 0, "skipped": 0, "count": len(plans)}

    if effective_policy == "move_to_library" and not effective_target_id:
        if preferred_library_id:
            effective_target_id = preferred_library_id
        else:
            events.log("move_to_library requires a target library id", "warning")
            return {"ok": True, "dry_run": dry_run, "acted": 0, "skipped": 0, "count": len(plans)}

    quarantine_dir = os.path.join(os.path.expanduser("~"), ".glacier_quarantine")
    target_lib_path = None
    use_patterns = False
    if effective_policy == "move_to_library" and effective_target_id:
        tgt = store.get_library(effective_target_id)
        if tgt and os.path.isdir(tgt["path"]):
            target_lib_path = tgt["path"]
            use_patterns = True
            events.log(f"Moving to target library: {target_lib_path}", "info")
        else:
            events.log(f"Target library {effective_target_id} not found or invalid, using quarantine", "warning")
            effective_policy = "quarantine"
            target_lib_path = quarantine_dir
            use_patterns = False

    if effective_policy == "quarantine":
        target_lib_path = quarantine_dir
        use_patterns = False
        os.makedirs(quarantine_dir, exist_ok=True)

    if dry_run:
        dry_plan = []
        for plan in plans:
            for tr in plan["remove"]:
                src = tr.get("path")
                if not src:
                    continue
                if target_lib_path and use_patterns:
                    tags = mover.read_tags(src)
                    folder = mover.render_pattern(settings["folder_pattern"], tags)
                    filename = mover.render_pattern(settings["naming_pattern"], tags)
                    ext = os.path.splitext(src)[1]
                    if '{track}' not in settings["naming_pattern"] and tags.get('tracknumber'):
                        filename = f"{filename} - {tags['tracknumber']}"
                    dest = os.path.join(target_lib_path, folder, filename + ext)
                elif target_lib_path:
                    dest = os.path.join(target_lib_path, os.path.basename(src))
                else:
                    dest = "no target"
                dry_plan.append({"source": src, "destination": dest})
        events.log(f"Exclusivity dry-run: {len(dry_plan)} files would move", "info")
        return {"ok": True, "dry_run": True, "count": len(dry_plan), "plan": dry_plan}

    if not target_lib_path:
        events.log("No target library or quarantine directory set", "error")
        return {"ok": True, "dry_run": False, "acted": 0, "skipped": 0, "count": 0}

    source_paths = []
    for plan in plans:
        for tr in plan["remove"]:
            src = tr.get("path")
            if src and os.path.exists(src):
                source_paths.append(src)

    if not source_paths:
        events.log("No files to move", "info")
        return {"ok": True, "dry_run": False, "acted": 0, "skipped": 0, "count": 0}

    if use_patterns:
        moved, errors = mover.move_files(
            source_paths,
            settings["folder_pattern"],
            settings["naming_pattern"],
            target_lib_path,
            dry_run=False,
            backup=settings.get("backup_before_move", False)
        )
    else:
        moved = 0
        errors = []
        for src in source_paths:
            dest = os.path.join(target_lib_path, os.path.basename(src))
            base, ext = os.path.splitext(dest)
            i = 1
            while os.path.exists(dest):
                dest = f"{base} ({i}){ext}"
                i += 1
            try:
                os.makedirs(target_lib_path, exist_ok=True)
                shutil.move(src, dest)
                moved += 1
                events.log(f"Quarantined: {src} -> {dest}", "success")
            except Exception as e:
                errors.append(str(e))
                events.log(f"Failed to move {src}: {e}", "error")

    events.log(f"Exclusivity applied: {moved} moved, {len(errors)} errors", "success")
    return {"ok": True, "dry_run": False, "acted": moved, "skipped": len(errors), "errors": errors}


# ======================================================================
# Cleanup, covers, playlists, report – unchanged
# ======================================================================

def op_cleanup(library_id, kind):
    lib = store.get_library(library_id)
    if not lib:
        raise ValueError("Unknown library")
    settings = store.get()
    tracks = scanner.get_inventory(lib, settings["extensions"], settings["excluded_folders"])
    root = lib["path"]

    if kind == "empty":
        folders = cleaner.find_empty_folders(root, settings["excluded_folders"])
        events.log(f"Cleanup (empty folders): {len(folders)} found", "info")
        return {"ok": True, "kind": kind, "count": len(folders), "folders": folders}

    if kind == "dup_fold":
        shells = cleaner.find_dup_folders(tracks, root)
        events.log(f"Cleanup (dup shells): {len(shells)} found", "info")
        return {"ok": True, "kind": kind, "count": len(shells), "folders": shells}

    if kind == "missing_tags":
        items = cleaner.find_missing_tags(tracks)
        events.log(f"Cleanup (missing tags): {len(items)} found", "info")
        return {"ok": True, "kind": kind, "count": len(items), "items": items}

    if kind == "corrupt":
        items = cleaner.find_corrupt(tracks)
        events.log(f"Cleanup (corrupt): {len(items)} found", "info")
        return {"ok": True, "kind": kind, "count": len(items), "items": items}

    raise ValueError(f"Unknown cleanup kind: {kind}")


def op_cleanup_apply(library_id, kind, paths, confirm=False):
    if not confirm:
        raise ValueError("Deletion requires explicit confirmation (confirm=true)")
    removed = 0
    errors = []
    if kind in ("empty", "dup_fold"):
        if is_cancelled():
            raise JobCancelled()
        # One batched call — the old code re-sorted and re-logged the whole
        # path list once per folder (O(N log N) per deletion).
        removed, errors = cleaner.apply_remove_dirs(paths)
    events.log(f"Cleanup applied ({kind}): {removed} removed", "success")
    return {"ok": True, "removed": removed, "errors": errors}


def op_covers(library_id, force=False):
    lib = store.get_library(library_id)
    if not lib:
        raise ValueError("Unknown library")
    settings = store.get()
    tracks = scanner.get_inventory(lib, settings["extensions"], settings["excluded_folders"])
    events.log(f"Starting cover {'rebuild' if force else 'extraction'} for {lib['name']}", "info")
    created, errors = exporter.extract_covers(tracks, force=force)
    action = "Rebuilt" if force else "Extracted"
    events.log(f"{action} covers: {created} in '{lib['name']}'", "success")
    return {"ok": True, "created": created, "errors": errors}


def op_playlists(library_id):
    lib = store.get_library(library_id)
    if not lib:
        raise ValueError("Unknown library")
    settings = store.get()
    tracks = scanner.get_inventory(lib, settings["extensions"], settings["excluded_folders"])
    events.log(f"Generating playlists for {lib['name']}", "info")
    created, errors = exporter.generate_playlists(tracks)
    events.log(f"Playlists generated: {created} in '{lib['name']}'", "success")
    return {"ok": True, "created": created, "errors": errors}


def op_report(library_id=None):
    settings = store.get()
    if library_id:
        libs = [l for l in _libs() if l["id"] == library_id]
    else:
        libs = _enabled_libs()
    per_library = {}
    all_tracks = []
    for lib in libs:
        if not os.path.isdir(lib["path"]):
            continue
        tracks = scanner.get_inventory(lib, settings["extensions"], settings["excluded_folders"])
        all_tracks.extend(tracks)
        per_library[lib["name"]] = scanner.build_library_stats(tracks)
    totals = scanner.build_library_stats(all_tracks)
    problems = [t["path"] for t in all_tracks if t.get("error")]
    text = exporter.to_text(totals, per_library, problems)
    payload = {"total": totals, "per_library": per_library, "problems": problems}
    return {"ok": True, "text": text, "json": payload,
            "json_text": exporter.to_json(payload),
            "per_library": per_library, "total": totals}


def op_plex_rating_sync():
    settings = store.get()
    plex = settings["plex"]
    result = plex_sync.sync_ratings(
        plex["url"], plex["token"], plex["music_section"],
        bool(plex.get("rating_overwrite", False)))
    store.update({"plex": {
        "last_rating_sync": time.time(),
        "last_rating_sync_result": result,
    }})
    return result


def op_plex_export(url, token, section_name):
    result = plex_client.export_library(url, token, section_name)
    if not result.get("ok"):
        raise RuntimeError(result.get("error", "Plex export failed"))
    return result


def op_extract_move(name, path, filters, source_library_ids, dry_run, confirm=False,
                    plan=None):
    if not dry_run and not confirm:
        raise ValueError("Apply requires explicit confirmation (confirm=true)")
    name = (name or "").strip() or os.path.basename(path.rstrip("/\\"))
    path = os.path.abspath(path or "")
    if not path:
        raise ValueError("Destination path is required")

    settings = store.get()
    ext = settings["extensions"]
    excl = settings["excluded_folders"]
    libs = _libs()
    if source_library_ids:
        libs = [l for l in libs if l["id"] in source_library_ids]

    for lib in list(libs):
        if os.path.abspath(lib["path"]).lower() == path.lower():
            raise ValueError("Destination path must differ from source libraries")

    # Reuse the dry-run plan when provided: the user confirmed exactly those
    # moves, and it skips re-reading every source file a second time.
    if plan is not None and not dry_run:
        os.makedirs(path, exist_ok=True)
        lib = store.add_library(name, path)
        moved, errors = extract.execute_extract(plan, path)
        for lid in (source_library_ids or []):
            scanner.invalidate_cache(lid)
        scanner.invalidate_cache(lib["id"])
        browser.invalidate_counts()
        events.log(f"Created library '{name}' and moved {moved} file(s)", "success")
        return {"ok": True, "dry_run": False, "library": lib,
                "moved": moved, "errors": errors, "count": len(plan)}

    inventories = {}
    for lib in libs:
        if not os.path.isdir(lib["path"]):
            events.log(f"Skipping missing source path: {lib['path']}", "warning")
            continue
        inventories[lib["id"]] = {
            "name": lib["name"],
            "path": lib["path"],
            "tracks": scanner.get_inventory(lib, ext, excl),
        }

    plan = extract.plan_extract(inventories, filters, path)
    if dry_run:
        total_bytes = sum(p["size"] for p in plan)
        events.log(f"Extract dry-run: {len(plan)} file(s), "
                   f"{total_bytes} bytes would move", "info")
        return {"ok": True, "dry_run": True, "count": len(plan),
                "bytes": total_bytes, "samples": plan[:50], "plan": plan}

    os.makedirs(path, exist_ok=True)
    lib = store.add_library(name, path)
    moved, errors = extract.execute_extract(plan, path)
    for lid in (source_library_ids or []):
        scanner.invalidate_cache(lid)
    scanner.invalidate_cache(lib["id"])
    browser.invalidate_counts()
    events.log(f"Created library '{name}' and moved {moved} file(s)", "success")
    return {"ok": True, "dry_run": False, "library": lib,
            "moved": moved, "errors": errors, "count": len(plan)}


# ======================================================================
# Import folder – uses mover with patterns
# ======================================================================

def op_import_folder(source_path, dest_library_id, preserve_structure=True, move=True):
    """Import audio files from a source folder into a library.

    ``move=False`` copies instead of moving; ``preserve_structure=False``
    re-renders destinations from the configured patterns instead of keeping
    the source folder layout (both flags were previously ignored).
    """
    if not os.path.isdir(source_path):
        raise ValueError("Source path does not exist")
    lib = store.get_library(dest_library_id)
    if not lib:
        raise ValueError("Destination library not found")
    dest_root = lib["path"]
    if not os.path.isdir(dest_root):
        raise ValueError("Destination library path does not exist")

    settings = store.get()
    extensions = set(settings["extensions"])
    excluded = set(settings["excluded_folders"])
    folder_pattern = settings["folder_pattern"]
    naming_pattern = settings["naming_pattern"]
    backup = settings.get("backup_before_move", False)

    audio_files = []
    for dirpath, dirnames, filenames in os.walk(source_path):
        if is_cancelled():
            raise JobCancelled()
        dirnames[:] = [d for d in dirnames if d.lower() not in excluded and not d.startswith(".")]
        for f in filenames:
            if os.path.splitext(f)[1].lower() in extensions:
                audio_files.append(os.path.join(dirpath, f))

    total = len(audio_files)
    events.progress(0, total, "Importing")
    if not audio_files:
        events.log("No audio files found in source folder", "warning")
        return {"ok": True, "moved": 0, "errors": [], "total": 0}

    if preserve_structure:
        # Keep the source's folder layout under the destination root.
        plan = []
        for src in audio_files:
            rel = os.path.relpath(src, source_path)
            dest = os.path.join(dest_root, rel)
            if os.path.abspath(src) == os.path.abspath(dest):
                continue
            plan.append({'source': src, 'destination': dest,
                         'source_name': os.path.basename(src)})
    else:
        plan = mover.plan_files(audio_files, folder_pattern, naming_pattern, dest_root,
                                emit_progress=True, library_name=lib["name"])
    if not plan:
        events.log("No files could be planned", "warning")
        return {"ok": True, "moved": 0, "errors": [], "total": total}

    moved, errors = mover.execute_plan(plan, dry_run=False, backup=backup, copy=not move)
    events.log(f"Import completed: {moved} files {'moved' if move else 'copied'}, "
               f"{len(errors)} errors", "success")
    scanner.invalidate_cache(dest_library_id)
    browser.invalidate_counts()
    return {"ok": True, "moved": moved, "errors": errors, "total": total}


# --- Job dispatch helper -------------------------------------------------

def _start(operation, callback, *args, library=None, **kwargs):
    ok, job = supervisor.start(operation, callback, *args, library=library, **kwargs)
    return _volatile(ok=True, job=job), 202


# --- Route registration --------------------------------------------------

def register_routes(app):
    @app.get("/api/events")
    def sse_events():
        q = events.hub.connect()

        def gen():
            try:
                while True:
                    try:
                        payload = q.get(timeout=15)
                        yield payload
                    except Exception:
                        yield ": keepalive\n\n"
            except GeneratorExit:
                pass
            finally:
                events.hub.disconnect(q)

        return Response(stream_with_context(gen()),
                        mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache",
                                 "X-Accel-Buffering": "no"})

    @app.get("/api/system")
    def system_info():
        return jsonify({
            "name": config.APP_NAME,
            "version": config.APP_VERSION,
            "host": app.config.get("HOST", config.DEFAULT_HOST),
            "port": app.config.get("PORT", config.DEFAULT_PORT),
            "ip": config.detect_ip(),
            "settings_path": str(store._path),
            "cache_dir": str(scanner.CACHE_DIR),
        })

    @app.get("/api/jobs/current")
    def job_current():
        return jsonify({"running": supervisor.running(),
                        "jobs": supervisor.all_running(),
                        "job": supervisor.current})

    @app.get("/api/jobs/history")
    def job_history():
        limit = request.args.get("limit", default=20, type=int)
        history = supervisor.history
        return jsonify({"jobs": history[-limit:]})

    @app.post("/api/jobs/<job_id>/terminate")
    def terminate_job(job_id):
        try:
            job_id = int(job_id)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Invalid job id",
                            "cancelled": False}), 400
        if supervisor.cancel(job_id):
            return jsonify({"ok": True, "cancelled": True, "job_id": job_id})
        return jsonify({"ok": False, "error": "No running job with that id",
                        "cancelled": False, "job_id": job_id}), 404

    @app.get("/api/stats")
    def dashboard_stats():
        # Pure cache read (in-memory) — no filesystem access, no re-stat.
        per = {}
        all_tracks = []
        for lib in _enabled_libs():
            tracks = scanner.load_cache(lib["id"])
            all_tracks.extend(tracks)
            per[lib["id"]] = {
                "id": lib["id"], "name": lib["name"],
                "tracks": len(tracks),
                "stats": scanner.build_library_stats(tracks),
            }
        totals = scanner.build_library_stats(all_tracks)
        return jsonify({"ok": True, "total": totals, "per_library": per})

    @app.get("/api/logs")
    def logs():
        limit = request.args.get("limit", default=200, type=int)
        return jsonify(events.hub.history(limit))

    @app.get("/api/errors")
    def list_errors():
        return jsonify({"ok": True, "errors": errors_store.store.list()})

    @app.delete("/api/errors")
    def clear_errors():
        errors_store.store.clear()
        return jsonify({"ok": True, "errors": []})

    @app.get("/api/errors/export")
    def export_errors():
        import json
        data = json.dumps(errors_store.store.list(), indent=2, ensure_ascii=False)
        return Response(data, mimetype="application/json",
                        headers={"Content-Disposition": "attachment; filename=glacier_errors.json"})

    @app.get("/api/operations")
    def list_operations():
        limit = request.args.get("limit", default=100, type=int)
        return jsonify({"ok": True, "operations": operations_store.store.list(limit)})

    # --- Audio Quality Analyzer --------------------------------------------
    @app.post("/api/audio-info")
    def audio_info():
        """Get detailed audio information for a file."""
        body = _json_body()
        path = body.get("path")
        if not path:
            return jsonify({"ok": False, "error": "Path is required"}), 400
        if not os.path.exists(path):
            return jsonify({"ok": False, "error": "File not found"}), 404

        try:
            from mutagen import File
            audio = File(path)
            if audio is None:
                return jsonify({"ok": False, "error": "Unsupported or corrupt file"}), 400

            info = {
                "path": path,
                "format": None,
                "bitrate": None,
                "sample_rate": None,
                "channels": None,
                "duration": None,
                "codec": None,
                "bits_per_sample": None,
                "file_size": os.path.getsize(path),
                "compression_ratio": None,
            }

            if hasattr(audio, 'info'):
                info["duration"] = float(audio.info.length) if hasattr(audio.info, 'length') else 0
                info["bitrate"] = int(audio.info.bitrate) if hasattr(audio.info, 'bitrate') else 0
                info["sample_rate"] = int(audio.info.sample_rate) if hasattr(audio.info, 'sample_rate') else 0
                info["channels"] = int(audio.info.channels) if hasattr(audio.info, 'channels') else 0

            # Detect format from file extension or mutagen type
            ext = os.path.splitext(path)[1].lower()
            if ext == '.flac':
                info["format"] = "FLAC"
                info["codec"] = "FLAC"
                if hasattr(audio.info, 'bits_per_sample'):
                    info["bits_per_sample"] = int(audio.info.bits_per_sample)
            elif ext == '.mp3':
                info["format"] = "MP3"
                info["codec"] = "MPEG-1 Audio Layer 3"
            elif ext == '.ogg':
                info["format"] = "OGG"
                info["codec"] = "Vorbis"
            elif ext == '.m4a':
                info["format"] = "M4A"
                info["codec"] = "AAC / ALAC"
            elif ext == '.wav':
                info["format"] = "WAV"
                info["codec"] = "PCM"
            else:
                info["format"] = "Unknown"

            # Try to get tags
            tags = {}
            if hasattr(audio, 'get'):
                for k in ('artist', 'album', 'title', 'genre', 'tracknumber', 'date'):
                    val = audio.get(k, [''])[0] if audio.get(k) else ''
                    if val:
                        tags[k] = str(val)
            info["tags"] = tags

            return jsonify({"ok": True, "info": info})

        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.post("/api/audio-analyze")
    def audio_analyze():
        """Waveform + spectrum (0..22 kHz) + spectrogram for one file.

        Decodes via ffmpeg and runs an FFT — heavy enough that it runs as a
        job so the UI gets progress and can cancel a pathological decode.
        """
        body = _json_body()
        path = body.get("path")
        if not path:
            return jsonify({"ok": False, "error": "Path is required"}), 400
        if not os.path.exists(path):
            return jsonify({"ok": False, "error": "File not found"}), 404
        return _start("audio-analyze", op_audio_analyze, path)

    @app.post("/api/audio-analysis-status")
    def audio_analysis_status():
        """Report whether ffmpeg is available for the analyzer UI."""
        return jsonify({"ok": True,
                        "ffmpeg": audio_analysis.ffmpeg_available()})

    @app.post("/api/ffmpeg-install")
    def ffmpeg_install():
        """Install ffmpeg on this host via its package manager (runs as a job)."""
        return _start("ffmpeg-install", op_ffmpeg_install)

    # --- File manager -------------------------------------------------
    @app.post("/api/files/rename")
    def file_rename():
        body = _json_body()
        if not body.get("path") or not body.get("name"):
            return jsonify({"ok": False, "error": "path and name required"}), 400
        try:
            return jsonify(op_file_rename(body["path"], body["name"], body.get("library_id")))
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/run/file-delete")
    def file_delete():
        body = _json_body()
        return _start("file-delete", op_file_delete,
                      body.get("paths", []), body.get("library_id"),
                      bool(body.get("confirm", False)))

    @app.post("/api/run/file-move")
    def file_move():
        body = _json_body()
        if not body.get("dest"):
            return jsonify({"ok": False, "error": "dest required"}), 400
        return _start("file-move", op_file_move,
                      body.get("paths", []), body["dest"],
                      body.get("library_id"), bool(body.get("copy", False)))

    @app.post("/api/files/new-folder")
    def file_new_folder():
        body = _json_body()
        if not body.get("path") or not body.get("name"):
            return jsonify({"ok": False, "error": "path and name required"}), 400
        try:
            return jsonify(op_file_new_folder(body["path"], body["name"], body.get("library_id")))
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    # --- Settings -----------------------------------------------------
    @app.get("/api/settings")
    def get_settings():
        return jsonify(store.get())

    @app.post("/api/settings")
    def post_settings():
        body = _json_body()
        action = body.pop("action", "update")
        if action == "replace":
            store.replace(body)
        else:
            store.update(body)
        return jsonify({"ok": True, "settings": store.get()})

    @app.get("/api/settings/export")
    def export_settings():
        import json
        data = json.dumps(store.get(), indent=2, ensure_ascii=False)
        return Response(data, mimetype="application/json",
                        headers={"Content-Disposition": "attachment; filename=glacier_settings.json"})

    @app.post("/api/settings/import")
    def import_settings():
        body = _json_body()
        if "settings" in body:
            body = body["settings"]
        store.replace(body)
        return jsonify({"ok": True, "settings": store.get()})

    # --- Libraries ----------------------------------------------------
    @app.get("/api/libraries")
    def get_libraries():
        return jsonify(store.get()["libraries"])

    @app.get("/api/libraries/status")
    def get_libraries_status():
        out = []
        for lib in _libs():
            path = lib.get("path", "")
            out.append({
                "id": lib.get("id"),
                "name": lib.get("name") or lib.get("path"),
                "path": path,
                "enabled": bool(lib.get("enabled", True)),
                "exists": bool(path) and os.path.isdir(path),
                "scan": lib.get("scan"),
            })
        return jsonify({"ok": True, "libraries": out})

    @app.post("/api/libraries")
    def add_library():
        body = _json_body()
        name = (body.get("name") or "").strip()
        path = (body.get("path") or "").strip()
        if not path:
            return jsonify({"ok": False, "error": "Path is required"}), 400
        if not os.path.isdir(path):
            return jsonify({"ok": False, "error": "Path is not a directory"}), 400
        existing = next((l for l in _libs() if l["path"].lower() == path.lower()), None)
        if existing:
            return jsonify({
                "ok": False,
                "error": f"Library already exists: {existing.get('name') or existing.get('path')}",
                "already_exists": True, "library": existing,
            }), 409
        lib = store.add_library(name or path, path)
        return jsonify({"ok": True, "library": lib}), 201

    @app.patch("/api/libraries/<library_id>")
    def rename_library(library_id):
        body = _json_body()
        if "enabled" in body:
            store.set_library_enabled(library_id, bool(body["enabled"]))
        name = body.get("name")
        if name and name.strip():
            store.rename_library(library_id, name.strip())
        return jsonify({"ok": True, "libraries": store.get()["libraries"]})

    @app.delete("/api/libraries/<library_id>")
    def remove_library(library_id):
        store.remove_library(library_id)
        return jsonify({"ok": True, "libraries": store.get()["libraries"]})

    # --- Directory browser ------------------------------------------
    @app.post("/api/list-dir")
    def list_dir():
        body = _json_body()
        path = body.get("path", "")
        try:
            return jsonify(browser.list_dir(path))
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    # --- Run operations (all through the job supervisor) --------------
    @app.post("/api/run/analyze")
    def run_analyze():
        body = _json_body()
        ids = body.get("library_ids") or None
        return _start("analyze", op_analyze, ids)

    @app.post("/api/run/quick-scan")
    def run_quick_scan():
        body = _json_body()
        ids = body.get("library_ids") or None
        return _start("quick-scan", op_quick_scan, ids)

    @app.post("/api/run/organize")
    def run_organize():
        body = _json_body()
        library_id = body.get("library_id")
        dry_run = bool(body.get("dry_run", True))
        confirm = bool(body.get("confirm", False))
        plan = body.get("plan")
        if not library_id:
            return jsonify({"ok": False, "error": "library_id is required"}), 400
        return _start("organize", op_organize, library_id, dry_run, confirm, plan=plan)

    @app.post("/api/preview-path")
    def preview_path():
        body = _json_body()
        folder_pattern = body.get("folder_pattern")
        naming_pattern = body.get("naming_pattern")
        sample = body.get("sample_tags") or {}
        library_id = body.get("library_id")
        root = None
        if library_id:
            lib = store.get_library(library_id)
            if lib:
                root = lib["path"]
        ext = body.get("ext", ".flac")
        if not ext.startswith("."):
            ext = "." + ext
        result = organizer.preview_path(
            folder_pattern, naming_pattern, sample, root, ext)
        return jsonify({"ok": True, **result})

    @app.post("/api/run/duplicates")
    def run_duplicates():
        body = _json_body()
        library_id = body.get("library_id")
        if not library_id:
            return jsonify({"ok": False, "error": "library_id is required"}), 400
        return _start("duplicates", op_duplicates, library_id)

    @app.post("/api/run/duplicates-resolve")
    def run_duplicates_resolve():
        body = _json_body()
        library_id = body.get("library_id")
        if not library_id:
            return jsonify({"ok": False, "error": "library_id is required"}), 400
        return _start("duplicates-resolve", op_duplicates_resolve,
                      library_id,
                      body.get("policy", "keep_best_quality"),
                      bool(body.get("dry_run", True)),
                      bool(body.get("confirm", False)),
                      body.get("quarantine_dir"))

    @app.post("/api/run/exclusivity")
    def run_exclusivity():
        body = _json_body()
        ids = body.get("library_ids") or None
        return _start("exclusivity", op_exclusivity, ids)

    @app.post("/api/run/resolve-exclusivity")
    def run_resolve():
        body = _json_body()
        policy = body.get("policy", "report_only")
        pref = body.get("preferred_library_id", "")
        target = body.get("move_target_library_id")
        dry = bool(body.get("dry_run", True))
        confirm = bool(body.get("confirm", False))
        ids = body.get("library_ids") or None
        return _start("resolve-exclusivity", op_resolve,
                      policy, pref, target, dry, confirm, library_ids=ids)

    @app.post("/api/run/artist-exclusivity")
    def run_artist_exclusivity():
        body = _json_body()
        ids = body.get("library_ids") or None
        return _start("artist-exclusivity", op_artist_exclusivity, ids)

    @app.post("/api/run/resolve-artist-exclusivity")
    def run_resolve_artist():
        body = _json_body()
        policy = body.get("policy", "report_only")
        pref = body.get("preferred_library_id", "")
        dry = bool(body.get("dry_run", True))
        confirm = bool(body.get("confirm", False))
        ids = body.get("library_ids") or None
        return _start("resolve-artist-exclusivity", op_artist_resolve,
                      policy, pref, dry, confirm, library_ids=ids)

    @app.post("/api/run/library_extract_move")
    def run_extract_move():
        body = _json_body()
        if not body.get("path"):
            return jsonify({"ok": False, "error": "path is required"}), 400
        return _start("library_extract_move", op_extract_move,
                      body.get("name", ""), body.get("path", ""),
                      body.get("filters", {}), body.get("source_library_ids"),
                      bool(body.get("dry_run", True)),
                      bool(body.get("confirm", False)))

    @app.post("/api/run/import-folder")
    def run_import_folder():
        body = _json_body()
        source = body.get("source_path")
        dest_lib = body.get("dest_library_id")
        preserve = bool(body.get("preserve_structure", True))
        move = bool(body.get("move", True))
        if not source or not dest_lib:
            return jsonify({"ok": False, "error": "source_path and dest_library_id are required"}), 400
        if not os.path.isdir(source):
            return jsonify({"ok": False, "error": "Source path does not exist"}), 400
        return _start("import-folder", op_import_folder, source, dest_lib, preserve, move)

    @app.post("/api/run/cleanup")
    def run_cleanup():
        body = _json_body()
        library_id = body.get("library_id")
        kind = body.get("kind")
        if not library_id or not kind:
            return jsonify({"ok": False, "error": "library_id and kind required"}), 400
        return _start("cleanup", op_cleanup, library_id, kind)

    @app.post("/api/run/cleanup-apply")
    def run_cleanup_apply():
        body = _json_body()
        library_id = body.get("library_id")
        kind = body.get("kind")
        paths = body.get("paths", [])
        confirm = bool(body.get("confirm", False))
        return _start("cleanup-apply", op_cleanup_apply,
                      library_id, kind, paths, confirm)

    @app.post("/api/run/covers")
    def run_covers():
        body = _json_body()
        library_id = body.get("library_id")
        if not library_id:
            return jsonify({"ok": False, "error": "library_id required"}), 400
        force = bool(body.get("force", False))
        return _start("covers", op_covers, library_id, force)

    @app.post("/api/run/rebuild-covers")
    def run_rebuild_covers():
        body = _json_body()
        library_id = body.get("library_id")
        if not library_id:
            return jsonify({"ok": False, "error": "library_id required"}), 400
        return _start("rebuild-covers", op_covers, library_id, True)

    @app.post("/api/run/playlists")
    def run_playlists():
        body = _json_body()
        library_id = body.get("library_id")
        if not library_id:
            return jsonify({"ok": False, "error": "library_id required"}), 400
        return _start("playlists", op_playlists, library_id)

    @app.post("/api/run/report")
    def run_report():
        body = _json_body()
        library_id = body.get("library_id")
        return _start("report", op_report, library_id)

    # --- Genre manager (Stage 4 #9) --------------------------------------
    @app.post("/api/genres")
    def genres_list():
        body = _json_body()
        library_id = body.get("library_id")
        if not library_id:
            return jsonify({"ok": False, "error": "library_id is required"}), 400
        try:
            return jsonify(op_genres_list(library_id))
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/run/genres/replace")
    def run_genre_replace():
        body = _json_body()
        library_id = body.get("library_id")
        if not library_id or not body.get("from") or not body.get("to"):
            return jsonify({"ok": False, "error": "library_id, from and to are required"}), 400
        return _start("genres", op_genre_replace, library_id, body["from"], body["to"],
                      library=(store.get_library(library_id) or {}).get("name"))

    @app.post("/api/run/genres/merge")
    def run_genre_merge():
        body = _json_body()
        library_id = body.get("library_id")
        if not library_id or not body.get("from") or not body.get("to"):
            return jsonify({"ok": False, "error": "library_id, from (list) and to are required"}), 400
        return _start("genres", op_genre_merge, library_id, list(body["from"]), body["to"],
                      library=(store.get_library(library_id) or {}).get("name"))

    @app.post("/api/run/genres/delete")
    def run_genre_delete():
        body = _json_body()
        library_id = body.get("library_id")
        if not library_id or not body.get("genre"):
            return jsonify({"ok": False, "error": "library_id and genre are required"}), 400
        return _start("genres", op_genre_delete, library_id, body["genre"],
                      library=(store.get_library(library_id) or {}).get("name"))

    @app.post("/api/run/genres/bulk-set")
    def run_genre_bulk_set():
        body = _json_body()
        library_id = body.get("library_id")
        if not library_id:
            return jsonify({"ok": False, "error": "library_id is required"}), 400
        return _start("genres", op_genre_bulk_set, library_id, body.get("value", ""),
                      library=(store.get_library(library_id) or {}).get("name"))

    # --- Large-scale tag editor pagination (Stage 4 #10) -----------------
    @app.post("/api/tracks")
    def tracks_page():
        body = _json_body()
        library_id = body.get("library_id")
        if not library_id:
            return jsonify({"ok": False, "error": "library_id is required"}), 400
        page = max(1, int(body.get("page", 1) or 1))
        per_page = min(200, max(1, int(body.get("per_page", 50) or 50)))
        try:
            return jsonify(op_tracks_page(
                library_id, page, per_page,
                body.get("sort", "title"), body.get("order", "asc"),
                body.get("query", "")))
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    # --- Tags --------------------------------------------------------
    @app.post("/api/tag-list")
    def tag_list():
        paths = _json_body().get("paths", [])
        return jsonify({"ok": True, "items": tag_editor.list_capable(paths)})

    @app.post("/api/tag-read")
    def tag_read():
        paths = _json_body().get("paths", [])
        return jsonify({"ok": True, "items": tag_editor.read_batch(paths)})

    @app.post("/api/tag-save")
    def tag_save():
        body = _json_body()
        paths = body.get("paths", [])
        field = body.get("field")
        value = body.get("value", "")
        if not field:
            return jsonify({"ok": False, "error": "field required"}), 400
        if not paths:
            return jsonify({"ok": False, "error": "paths required"}), 400
        # Small batches stay synchronous; big ones go through the job
        # supervisor so they get progress/ETA/cancel instead of hanging the
        # HTTP request (and the browser) for minutes.
        if len(paths) <= 50:
            applied, errors = tag_editor.apply(paths, field, value)
            return jsonify({"ok": True, "applied": applied, "errors": errors})
        return _start("tags", op_tag_save, paths, field, value)

    # --- Plex --------------------------------------------------------
    @app.post("/api/plex/status")
    def plex_status():
        s = store.get()["plex"]
        return jsonify(plex_client.get_status(s["url"], s["token"]))

    @app.post("/api/plex/stats")
    def plex_stats():
        s = store.get()["plex"]
        return jsonify(plex_client.get_stats(s["url"], s["token"], s["music_section"]))

    @app.post("/api/plex/library-stats")
    def plex_library_stats():
        s = store.get()["plex"]
        return jsonify(plex_client.get_all_music_stats(s["url"], s["token"]))

    @app.post("/api/plex/search")
    def plex_search():
        body = _json_body()
        s = store.get()["plex"]
        return jsonify(plex_client.search(s["url"], s["token"], body.get("query", "")))

    @app.post("/api/plex/rate")
    def plex_rate():
        body = _json_body()
        s = store.get()["plex"]
        return jsonify(plex_client.rate(s["url"], s["token"],
                                        body.get("query", ""), body.get("rating", 5)))

    @app.post("/api/plex/duplicates")
    def plex_duplicates():
        s = store.get()["plex"]
        return jsonify(plex_client.get_duplicates(s["url"], s["token"], s["music_section"]))

    @app.post("/api/plex/sync-ratings")
    def plex_sync_ratings():
        return _start("plex-rating-sync", op_plex_rating_sync)

    @app.post("/api/plex/test")
    def plex_test():
        url, token, _ = _plex_creds(_json_body())
        return jsonify(plex_client.test_connection(url, token))

    @app.post("/api/plex/sections")
    def plex_sections():
        url, token, _ = _plex_creds(_json_body())
        return jsonify(plex_client.get_sections(url, token))

    @app.post("/api/run/plex-export")
    def plex_export():
        url, token, section = _plex_creds(_json_body())
        return _start("plex-export", op_plex_export, url, token, section)

    @app.get("/api/plex/sync-status")
    def plex_sync_status():
        plex = store.get()["plex"]
        return jsonify({
            "ok": True,
            "enabled": bool(plex.get("rating_sync_enabled", False)),
            "interval_sec": plex.get("rating_sync_interval_sec", 600),
            "overwrite": bool(plex.get("rating_overwrite", False)),
            "last_run": plex.get("last_rating_sync"),
            "last_result": plex.get("last_rating_sync_result"),
        })