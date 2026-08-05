"""Glacier REST API routes.

These routes are registered on the Flask app by ``app.py``. Heavy operations
are dispatched through the job supervisor so the SSE stream and UI stay
responsive and only one filesystem-heavy job runs at a time.

Every destructive operation (organize apply, exclusivity resolution, cleanup
apply) requires an explicit ``confirm`` flag — Glacier never silently changes
files.
"""

import os
import time

from flask import request, jsonify, Response, stream_with_context

from . import config
from . import events
from . import errors as errors_store
from . import operations as operations_store
from .jobs import supervisor
from .settings import store
from . import browser
from .library import scanner, organizer, duplicates as dup_mod, exclusivity, extract
from .tags import editor as tag_editor
from .tags import genres as genre_ops
from .cleanup import cleaner
from .reports import exporter
from .plex import client as plex_client
from .plex import sync as plex_sync


def _libs():
    return store.get()["libraries"]


def _enabled_libs():
    """Libraries that are active (enabled). Disabled libraries are excluded from
    'all-library' scans/operations but keep their files on disk."""
    return [l for l in _libs() if l.get("enabled", True) is not False]


def _settings():
    return store.get()


def _json_body():
    return request.get_json(silent=True) or {}


def _plex_creds(body):
    """Resolve Plex credentials from a request body, falling back to saved
    settings. Lets the client test/export with not-yet-saved credentials."""
    s = store.get().get("plex", {})
    url = (body.get("url") or s.get("url") or "").strip()
    token = (body.get("token") or s.get("token") or "").strip()
    section = (body.get("section") or s.get("music_section") or "").strip()
    return url, token, section


def _volatile(**kw):
    return jsonify(kw)


# --- Operation callbacks (run inside the job supervisor) ----------------

def op_analyze(library_ids=None):
    settings = store.get()
    libs = _libs()
    if library_ids:
        libs = [l for l in libs if l["id"] in library_ids]
    else:
        # Batch analyze: only active (enabled) libraries are scanned.
        libs = _enabled_libs()
    if not libs:
        raise ValueError("No libraries configured")
    per_library = {}
    all_tracks = []
    ext = settings["extensions"]
    excl = settings["excluded_folders"]
    for lib in libs:
        if not os.path.isdir(lib["path"]):
            events.log(f"Skipping missing path: {lib['path']}", "warning")
            per_library[lib["id"]] = {"error": "missing path"}
            continue
        tracks = scanner.scan_library(lib, ext, excl, emit=True, use_cache=False)
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
    totals = scanner.build_library_stats(all_tracks)
    events.log(
        f"Analysis complete: {totals['tracks']} tracks across {len(libs)} libraries",
        "success")
    return {"ok": True, "libraries": per_library, "total": totals}


def op_quick_scan(library_ids=None):
    """Fast change-detection scan for one or more libraries (Stage 4 #5).

    Unlike a full analyze, only files that are new, modified, moved or deleted
    since the last scan are processed — everything else is served from cache.
    """
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
            # A full scan falls back to building full stats; otherwise report
            # the cached track count so the dashboard stays current.
            st = scanner.build_library_stats(
                scanner.load_cache(lib["id"]))
            store.set_scan(lib["id"], {
                "at": time.time(),
                "tracks": st["tracks"],
                "errors": st["errors"],
            })
        except Exception as exc:  # noqa: BLE001
            events.log(f"Quick scan failed for '{lib['name']}': {exc}", "error")
            errors_store.store.report_exception(
                f"Quick scan failed for '{lib['name']}'", module="scanner")
            per_library[lib["id"]] = {"error": str(exc)}
    total_new = sum(1 for r in per_library.values() if isinstance(r, dict)
                    and not r.get("full_scan") for _ in r.get("new", []))
    events.log(
        f"Quick scan complete: {total_new} new file(s) across {len(libs)} libraries",
        "success")
    return {"ok": True, "libraries": per_library}


def op_startup_scan():
    """Automatic startup change-detection over all enabled libraries (Stage 4 #5)."""
    try:
        return op_quick_scan(None)
    except Exception as exc:  # noqa: BLE001
        events.log(f"Startup scan failed: {exc}", "warning")
        return {"ok": True, "skipped": True, "error": str(exc)}


def _library_tracks(library_id, settings, force=False):
    """Resolve a library and return its inventory tracks.

    ``force=True`` re-reads metadata from disk (accurate but slower); the default
    uses the cached inventory. Returns ``(lib, tracks)``.
    """
    lib = store.get_library(library_id)
    if not lib:
        raise ValueError("Unknown library")
    lib_settings = settings or store.get()
    if force:
        tracks = scanner.scan_library(
            lib, lib_settings["extensions"], lib_settings["excluded_folders"],
            emit=False, use_cache=False)
    else:
        tracks = scanner.get_inventory(
            lib, lib_settings["extensions"], lib_settings["excluded_folders"])
    return lib, tracks


def _refresh_cache(lib):
    """Re-read one library's metadata and persist the updated cache (used after
    tag-writing jobs so lists stay accurate without a manual rescan)."""
    s = store.get()
    try:
        scanner.scan_library(lib, s["extensions"], s["excluded_folders"],
                             emit=False, use_cache=False)
    except Exception:
        pass


def op_genre_replace(library_id, from_genre, to_genre):
    lib, tracks = _library_tracks(library_id, store.get(), force=True)
    paths = [t["path"] for t in tracks]
    applied, skipped, errors = genre_ops.replace(paths, from_genre, to_genre)
    if applied:
        _refresh_cache(lib)
    events.log(f"Genre replace '{from_genre}' -> '{to_genre}' "
               f"in '{lib['name']}': {applied} updated, {skipped} unchanged", "success")
    return {"ok": True, "library": lib["name"], "applied": applied,
            "skipped": skipped, "errors": errors}


def op_genre_merge(library_id, from_genres, to_genre):
    lib, tracks = _library_tracks(library_id, store.get(), force=True)
    paths = [t["path"] for t in tracks]
    applied, skipped, errors = genre_ops.merge(paths, from_genres, to_genre)
    if applied:
        _refresh_cache(lib)
    events.log(f"Genre merge into '{to_genre}' in '{lib['name']}': "
               f"{applied} updated, {skipped} unchanged", "success")
    return {"ok": True, "library": lib["name"], "applied": applied,
            "skipped": skipped, "errors": errors}


def op_genre_delete(library_id, genre):
    lib, tracks = _library_tracks(library_id, store.get(), force=True)
    paths = [t["path"] for t in tracks]
    applied, skipped, errors = genre_ops.delete(paths, genre)
    if applied:
        _refresh_cache(lib)
    events.log(f"Genre remove '{genre}' in '{lib['name']}': "
               f"{applied} updated, {skipped} unchanged", "success")
    return {"ok": True, "library": lib["name"], "applied": applied,
            "skipped": skipped, "errors": errors}


def op_genre_bulk_set(library_id, value):
    lib, tracks = _library_tracks(library_id, store.get(), force=True)
    paths = [t["path"] for t in tracks]
    applied, skipped, errors = genre_ops.bulk_set(paths, value)
    if applied:
        _refresh_cache(lib)
    events.log(f"Genre set '{value}' across '{lib['name']}': "
               f"{applied} updated, {skipped} unchanged", "success")
    return {"ok": True, "library": lib["name"], "applied": applied,
            "skipped": skipped, "errors": errors}


def op_genres_list(library_id):
    """List genres for one library (read via the cached inventory)."""
    lib, tracks = _library_tracks(library_id, store.get())
    genres = genre_ops.collect(tracks)
    return {"ok": True, "library": lib["name"], "library_id": library_id,
            "genres": genres, "count": len(genres)}


def op_tracks_page(library_id, page, per_page, sort="title", order="asc", query=""):
    """Paged track table for the large-scale tag editor (Stage 4 #10).

    Reads the (cached) inventory for one library, optionally filters by a text
    query and sorts, then returns only the requested page.
    """
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




def op_organize(library_id, dry_run, confirm=False):
    lib = store.get_library(library_id)
    if not lib:
        raise ValueError("Unknown library")
    if not dry_run and not confirm:
        raise ValueError("Apply requires explicit confirmation (confirm=true)")
    settings = store.get()
    tracks = scanner.get_inventory(lib, settings["extensions"], settings["excluded_folders"])
    plan = organizer.plan_library(
        tracks, lib["path"],
        settings["folder_pattern"], settings["naming_pattern"])
    if dry_run:
        events.log(f"Organize dry-run: {len(plan)} files would move", "info")
        return {"ok": True, "dry_run": True, "count": len(plan), "plan": plan}
    moved, errors = organizer.apply_plan(
        plan, lib["path"], settings.get("backup_before_move", False))
    events.log(f"Organized {moved} files in '{lib['name']}'", "success")
    return {"ok": True, "dry_run": False, "moved": moved,
            "errors": errors, "count": len(plan)}


def op_duplicates(library_id):
    lib = store.get_library(library_id)
    if not lib:
        raise ValueError("Unknown library")
    settings = store.get()
    tracks = scanner.get_inventory(lib, settings["extensions"], settings["excluded_folders"])
    groups = dup_mod.detect_inventory(tracks, settings["exclusivity"]["identity"])
    events.log(f"Duplicate scan '{lib['name']}': {len(groups)} groups", "success")
    return {"ok": True, "library_id": library_id, "library": lib["name"],
            "groups": groups, "count": len(groups)}


def op_exclusivity(library_ids=None):
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
    pref = settings["exclusivity"].get("preferred_library_id", "")
    violations = exclusivity.scan_violations(inventories, mode, pref)
    events.log(f"Exclusivity scan: {len(violations)} violations across libraries", "success")
    return {"ok": True, "violations": violations, "count": len(violations)}


def op_artist_exclusivity(library_ids=None):
    """Scan for artists present in more than one library (Stage 2)."""
    settings = store.get()
    libs = _enabled_libs()
    if library_ids:
        libs = [l for l in libs if l["id"] in library_ids]
    inventories = {}
    for lib in libs:
        if os.path.isdir(lib["path"]):
            inventories[lib["id"]] = scanner.get_inventory(
                lib, settings["extensions"], settings["excluded_folders"])
    exceptions = settings.get("artist_exclusivity_exceptions", [])
    groups = exclusivity.scan_artist_violations(inventories, exceptions)
    events.artist_exclusivity_report(len(groups))
    events.log(f"Artist exclusivity scan: {len(groups)} violation(s)", "success")
    return {"ok": True, "groups": groups, "count": len(groups)}


def op_artist_resolve(policy, preferred_library_id, dry_run, confirm=False, library_ids=None):
    """Build (and optionally execute) artist exclusivity plans."""
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
    exceptions = settings.get("artist_exclusivity_exceptions", [])
    groups = exclusivity.scan_artist_violations(inventories, exceptions)
    plans = exclusivity.resolve_artist_groups(groups, policy, preferred_library_id)
    plans = [p for p in plans if p["remove"]]

    if dry_run:
        total = sum(len(p["remove"]) for p in plans)
        events.log(f"Artist exclusivity dry-run: {len(plans)} artist(s), "
                   f"{total} files to move", "info")
        return {"ok": True, "dry_run": True, "count": len(plans), "plans": plans}

    move_dir = None
    if preferred_library_id:
        tgt = store.get_library(preferred_library_id)
        if tgt:
            move_dir = tgt["path"]
    acted = 0
    skipped = 0
    for plan in plans:
        for tr in plan["remove"]:
            ok, _d = exclusivity.execute_removal(
                tr, "move_to_library", move_dir=move_dir)
            if ok:
                acted += 1
            else:
                skipped += 1
    events.log(f"Artist exclusivity applied: {acted} moved, {skipped} skipped", "success")
    return {"ok": True, "dry_run": False, "acted": acted,
            "skipped": skipped, "count": len(plans)}


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
    plans = [exclusivity.resolve_group(v, policy, preferred_library_id,
                                       move_target_library_id)
             for v in violations]
    plans = [p for p in plans if p["remove"]]

    if dry_run:
        total = sum(len(p["remove"]) for p in plans)
        events.log(f"Exclusivity dry-run: {len(plans)} groups, {total} files to act on", "info")
        return {"ok": True, "dry_run": True, "count": len(plans), "plans": plans}

    quarantine_dir = os.path.join(os.path.expanduser("~"), ".glacier_quarantine")
    move_dir = None
    if policy == "move_to_library" and move_target_library_id:
        tgt = store.get_library(move_target_library_id)
        if tgt:
            move_dir = tgt["path"]
    acted = 0
    skipped = 0
    for p in plans:
        for tr in p["remove"]:
            ok, _detail = exclusivity.execute_removal(
                tr, policy, quarantine_dir=quarantine_dir, move_dir=move_dir)
            if ok:
                acted += 1
            else:
                skipped += 1
    events.log(
        f"Exclusivity applied: {acted} files processed, {skipped} skipped", "success")
    return {"ok": True, "dry_run": False, "acted": acted,
            "skipped": skipped, "count": len(plans)}


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
        removed, errors = cleaner.apply_remove_dirs(paths)
    events.log(f"Cleanup applied ({kind}): {removed} removed", "success")
    return {"ok": True, "removed": removed, "errors": errors}


def op_covers(library_id, force=False):
    lib = store.get_library(library_id)
    if not lib:
        raise ValueError("Unknown library")
    settings = store.get()
    tracks = scanner.get_inventory(lib, settings["extensions"], settings["excluded_folders"])
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
    """Pull Plex ratings and write them into local tags (Stage 2)."""
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
    """Export a Plex music section's full metadata (as a background job so the
    progress streams into the footer and the result is inspectable)."""
    result = plex_client.export_library(url, token, section_name)
    if not result.get("ok"):
        raise RuntimeError(result.get("error", "Plex export failed"))
    return result


def op_extract_move(name, path, filters, source_library_ids, dry_run, confirm=False):
    """Create a new library and move matching files into it (Stage 2)."""
    if not dry_run and not confirm:
        raise ValueError("Apply requires explicit confirmation (confirm=true)")
    name = (name or "").strip() or os.path.basename(path.rstrip("/\\"))
    path = os.path.abspath(path or "")
    if not path:
        raise ValueError("Destination path is required")

    # Gather inventories for the selected source libraries.
    settings = store.get()
    ext = settings["extensions"]
    excl = settings["excluded_folders"]
    libs = _libs()
    if source_library_ids:
        libs = [l for l in libs if l["id"] in source_library_ids]
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

    # Avoid moving from a library that is actually the destination.
    for lib in list(libs):
        if os.path.abspath(lib["path"]).lower() == path.lower():
            raise ValueError("Destination path must differ from source libraries")

    plan = extract.plan_extract(inventories, filters, path)
    if dry_run:
        total_bytes = sum(p["size"] for p in plan)
        events.log(f"Extract dry-run: {len(plan)} file(s), "
                   f"{total_bytes} bytes would move", "info")
        return {"ok": True, "dry_run": True, "count": len(plan),
                "bytes": total_bytes, "samples": plan[:50], "plan": plan}

    # Create the directory, register the library, then move files.
    os.makedirs(path, exist_ok=True)
    lib = store.add_library(name, path)
    moved, errors = extract.execute_extract(plan, path)
    # Refresh the new library index after moving.
    try:
        scanner.scan_library(lib, ext, excl, emit=False, use_cache=False)
    except Exception:
        pass
    events.log(f"Created library '{name}' and moved {moved} file(s)", "success")
    return {"ok": True, "dry_run": False, "library": lib,
            "moved": moved, "errors": errors, "count": len(plan)}


# --- Job dispatch helper -------------------------------------------------

def _start(operation, callback, *args, library=None, **kwargs):
    # Concurrency supported: always start a new job (no single-job lock).
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
        """Request termination of a running background job (Stage 4 fix)."""
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
        """Cached aggregate statistics (no re-scan) for the dashboard.

        Reads each enabled library's persisted inventory cache so the stat
        cards populate instantly without starting a scan.
        """
        settings = store.get()
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

    # --- Global Error Center (Stage 4 #2) --------------------------------
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

    # --- Recent operations (Stage 4 #8) ----------------------------------
    @app.get("/api/operations")
    def list_operations():
        limit = request.args.get("limit", default=100, type=int)
        return jsonify({"ok": True, "operations": operations_store.store.list(limit)})


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
        """Enriched library list: includes whether the configured path currently
        exists on disk, plus the enabled/active flag. Lets the UI show clearly
        which libraries are loaded / reachable and which are just configured."""
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
        except Exception as exc:  # noqa: BLE001
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
        if not library_id:
            return jsonify({"ok": False, "error": "library_id is required"}), 400
        return _start("organize", op_organize, library_id, dry_run, confirm)

    # --- Live path/filename preview (Stage 2) -------------------------
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
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/run/genres/replace")
    def run_genre_replace():
        body = _json_body()
        library_id = body.get("library_id")
        if not library_id or not body.get("from") or not body.get("to"):
            return jsonify({"ok": False, "error": "library_id, from and to are required"}), 400
        return _start("genres", op_genre_replace, library_id, body["from"], body["to"],
                      library=store.get_library(library_id)["name"])

    @app.post("/api/run/genres/merge")
    def run_genre_merge():
        body = _json_body()
        library_id = body.get("library_id")
        if not library_id or not body.get("from") or not body.get("to"):
            return jsonify({"ok": False, "error": "library_id, from (list) and to are required"}), 400
        return _start("genres", op_genre_merge, library_id, list(body["from"]), body["to"],
                      library=store.get_library(library_id)["name"])

    @app.post("/api/run/genres/delete")
    def run_genre_delete():
        body = _json_body()
        library_id = body.get("library_id")
        if not library_id or not body.get("genre"):
            return jsonify({"ok": False, "error": "library_id and genre are required"}), 400
        return _start("genres", op_genre_delete, library_id, body["genre"],
                      library=store.get_library(library_id)["name"])

    @app.post("/api/run/genres/bulk-set")
    def run_genre_bulk_set():
        body = _json_body()
        library_id = body.get("library_id")
        if not library_id:
            return jsonify({"ok": False, "error": "library_id is required"}), 400
        return _start("genres", op_genre_bulk_set, library_id, body.get("value", ""),
                      library=store.get_library(library_id)["name"])

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
        except Exception as exc:  # noqa: BLE001
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
        applied, errors = tag_editor.apply(paths, field, value)
        return jsonify({"ok": True, "applied": applied, "errors": errors})

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
        """Per-music-library statistics straight from the Plex server (Stage 4 #13)."""
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
        """Test a Plex connection with the given (possibly not-yet-saved)
        credentials, so the user can validate before applying settings."""
        url, token, _ = _plex_creds(_json_body())
        return jsonify(plex_client.test_connection(url, token))

    @app.post("/api/plex/sections")
    def plex_sections():
        """List Plex library sections + their on-disk folder locations, so the
        user can load Plex folders into Glacier without a manual file browse."""
        url, token, _ = _plex_creds(_json_body())
        return jsonify(plex_client.get_sections(url, token))

    @app.post("/api/run/plex-export")
    def plex_export():
        """Export full metadata for a Plex music section (background job)."""
        url, token, section = _plex_creds(_json_body())
        return _start("plex-export", op_plex_export, url, token, section)

    @app.post("/api/plex/export")
    def plex_export_content():
        """Synchronous Plex export that streams progress over SSE while it pulls,
        then returns the full metadata so the client can download it."""
        url, token, section = _plex_creds(_json_body())
        result = plex_client.export_library(url, token, section)
        if not result.get("ok"):
            return jsonify(result), 400
        return jsonify(result)


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



