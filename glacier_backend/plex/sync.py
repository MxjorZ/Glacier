"""Plex user ratings -> local FLAC/MP3 tag rating sync.

Matches Plex tracks to local files by normalized artist+album+title (with track
number when present), maps Plex's 0..10 rating (10.0 == 5 stars) to a local tag
`rating = round(plex_rating * 10)` clamped to 0..100, and writes via the shared
metadata writer so it stays consistent with the Tags editor.

By default (``overwrite=False``) a local rating is never lowered: if the local
rating is already >= the mapped tag rating, the write is skipped.
"""

import os
import time

from .. import events
from ..settings import store
from ..library import scanner, metadata
from ..library.exclusivity import normalize
from . import client


def map_rating(plex_rating):
    """Map a Plex rating (0..10, 10.0 = 5 stars) to a tag rating 0..100."""
    tag = round(float(plex_rating) * 10)
    return max(0, min(100, tag))


def _local_key(tags):
    artist = normalize(tags.get("albumartist") or tags.get("artist") or "")
    album = normalize(tags.get("album") or "")
    title = normalize(tags.get("title") or "")
    return artist, album, title


def _plex_key(rec):
    return (normalize(rec.get("artist") or ""),
            normalize(rec.get("album") or ""),
            normalize(rec.get("title") or ""))


def _local_rating(tags):
    try:
        return int(float((tags.get("rating") or 0)))
    except (TypeError, ValueError):
        return 0


def _build_index(extensions, excluded):
    """Map normalized (artist, album, title) -> list of local file records."""
    index = {}
    settings = store.get()
    for lib in settings["libraries"]:
        if not os.path.isdir(lib["path"]):
            continue
        for tr in scanner.get_inventory(lib, extensions, excluded):
            if tr.get("error"):
                continue
            tags = tr.get("tags", {})
            key = _local_key(tags)
            if not key or not key[0] or not key[2]:
                continue
            index.setdefault(key, []).append({
                "path": tr["path"],
                "rating": _local_rating(tags),
            })
    return index


def sync_ratings(url, token, section_name, overwrite):
    """Run one full rating-sync pass. Returns a result dict; never raises on a
    single file's write failure."""
    events.log("Plex rating sync starting", "info")
    settings = store.get()
    ext = settings["extensions"]
    excl = settings["excluded_folders"]

    pulled = client.pull_ratings(url, token, section_name)
    if not pulled.get("ok"):
        raise RuntimeError(pulled.get("error", "Plex rating pull failed"))
    ratings = pulled["ratings"]
    events.log(f"Plex: {len(ratings)} rated track(s) pulled from '{section_name}'", "info")

    index = _build_index(ext, excl)
    written = 0
    matched = 0
    skipped = 0
    missed = 0
    errors = []
    logged = 0

    for rec in ratings:
        tag_rating = map_rating(rec.get("rating") or 0)
        if tag_rating <= 0:
            continue
        key = _plex_key(rec)
        targets = index.get(key, []) if key[0] and key[2] else []
        if not targets:
            missed += 1
            continue
        for tgt in targets:
            matched += 1
            if not overwrite and tgt["rating"] >= tag_rating:
                skipped += 1
                continue
            res = metadata.write(tgt["path"], {"rating": str(tag_rating)})
            if res.get("ok"):
                written += 1
                if logged < 8:
                    events.log(
                        f"Rating -> {tag_rating}: {os.path.basename(tgt['path'])}", "info")
                    logged += 1
            else:
                errors.append({"path": tgt["path"], "error": res.get("error")})

    net = {"ok": True, "section": section_name,
           "pulled": len(ratings), "matched": matched, "written": written,
           "skipped": skipped, "missed": missed, "errors": errors}
    events.log(
        f"Plex rating sync complete: {written} written, {matched} matched, "
        f"{skipped} skipped, {missed} unmatched, {len(errors)} errors", "success")
    return net
