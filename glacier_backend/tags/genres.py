"""Bulk genre management (Stage 4 #9).

Loads the distinct genres used across a library (with track/album/artist counts)
and applies bulk genre transforms: replace one genre with another, merge several
genres into one, delete a genre from its tracks, or set every selected track to a
single value. Writes reuse the shared metadata writer so behaviour stays
consistent with the Tags editor.
"""

from .. import events
from ..cancel import is_cancelled, JobCancelled
from ..library import metadata


def collect(tracks):
    """Return sorted [{genre, tracks, albums, artists}] across the given tracks."""
    counts = {}
    for t in tracks:
        tags = t.get("tags", {})
        g = (tags.get("genre") or "").strip()
        if not g:
            continue
        entry = counts.setdefault(g, {"tracks": set(), "albums": set(), "artists": set()})
        entry["tracks"].add(t.get("path"))
        artist = (tags.get("albumartist") or tags.get("artist") or "").strip()
        album = (tags.get("album") or "").strip()
        entry["albums"].add((artist, album))
        if artist:
            entry["artists"].add(artist.lower())
    out = [
        {"genre": g, "tracks": len(e["tracks"]),
         "albums": len(e["albums"]), "artists": len(e["artists"])}
        for g, e in counts.items()
    ]
    return sorted(out, key=lambda x: (-x["tracks"], x["genre"].lower()))


def apply_transform(paths, transform_fn, label):
    """Apply ``transform_fn(curr_genre) -> next_genre (None = keep)`` to paths."""
    applied = skipped = 0
    errors = []
    for i, p in enumerate(paths):
        if is_cancelled():
            raise JobCancelled()
        rec = metadata.read(p)
        if rec.get("error"):
            errors.append({"path": p, "error": rec.get("error")})
            continue
        cur = (rec.get("tags", {}).get("genre") or "").strip()
        new_genre = transform_fn(cur)
        if new_genre is None or new_genre == cur:
            skipped += 1
            continue
        res = metadata.write(p, {"genre": new_genre})
        if res.get("ok"):
            applied += 1
        else:
            errors.append({"path": p, "error": res.get("error")})
        if (i + 1) % 25 == 0 or i + 1 == len(paths):
            events.progress(i + 1, len(paths), label)
    return applied, skipped, errors


def replace(paths, from_genre, to_genre):
    return apply_transform(paths, lambda cur: to_genre if cur == from_genre else None,
                           f"Replacing genre '{from_genre}'")


def merge(paths, from_genres, to_genre):
    targets = {g for g in (from_genres or []) if g}
    return apply_transform(paths, lambda cur: to_genre if cur in targets else None,
                           "Merging genres")


def delete(paths, genre):
    return apply_transform(paths, lambda cur: "" if cur == genre else None,
                           f"Removing genre '{genre}'")


def bulk_set(paths, value):
    return apply_transform(paths, lambda cur: value, "Setting genre")
