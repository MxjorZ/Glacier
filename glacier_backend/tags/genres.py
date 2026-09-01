"""Bulk genre management.

Loads the distinct genres used across a library (with track/album/artist
counts) and applies bulk genre transforms: replace one genre with another,
merge several genres into one, delete a genre from its tracks, or set every
selected track to a single value. Writes reuse the shared metadata writer so
behaviour stays consistent with the Tags editor.

Multi-genre tags ("Electronic - Tropical House; Electronic - Dance-pop") are
classified by their LEFTMOST genre ("Electronic" above): a track belongs to
exactly one bucket for counting and transforms, while the raw value stays
visible for reference.
"""

import re

from .. import events
from ..cancel import is_cancelled, JobCancelled
from ..library import metadata

# Separators seen in the wild between multiple genres in one tag value.
_GENRE_SPLIT_RE = re.compile(r"\s*[;/,]\s*|\s*\|\s*")
# Hierarchy marker inside a single genre ("Electronic - Tropical House").
_GENRE_DASH_RE = re.compile(r"\s+-\s+")


def split_genres(raw):
    """Split a raw genre tag into its individual genre strings."""
    if not raw:
        return []
    return [g.strip() for g in _GENRE_SPLIT_RE.split(str(raw)) if g.strip()]


def primary_genre(raw):
    """Leftmost genre of a (possibly multi-genre) tag value.

    "Electronic - Tropical House; Electronic - Dance-pop" -> "Electronic".
    This is the classification key for the genre manager.
    """
    parts = split_genres(raw)
    if not parts:
        return ""
    first = parts[0]
    dash = _GENRE_DASH_RE.split(first)
    return dash[0].strip() if dash else first.strip()


def genre_label(raw):
    """Full first genre incl. sub-style, for display ("Electronic - Deep House")."""
    parts = split_genres(raw)
    return parts[0] if parts else ""


def collect(tracks):
    """Return sorted [{genre, tracks, albums, artists, examples}] across tracks.

    ``genre`` is the primary (leftmost) genre; ``examples`` lists distinct
    raw tag values that mapped to it, so the UI can show what got grouped.
    """
    counts = {}
    for t in tracks:
        tags = t.get("tags", {})
        raw = tags.get("genre") or ""
        key = primary_genre(raw)
        if not key:
            continue
        entry = counts.setdefault(key, {"tracks": set(), "albums": set(),
                                         "artists": set(), "raw": {}})
        entry["tracks"].add(t.get("path"))
        artist = (tags.get("albumartist") or tags.get("artist") or "").strip()
        album = (tags.get("album") or "").strip()
        entry["albums"].add((artist, album))
        if artist:
            entry["artists"].add(artist.lower())
        if raw:
            entry["raw"].setdefault(str(raw), 0)
            entry["raw"][str(raw)] += 1
    out = [
        {"genre": g, "tracks": len(e["tracks"]),
         "albums": len(e["albums"]), "artists": len(e["artists"]),
         "examples": sorted(e["raw"].items(), key=lambda kv: -kv[1])[:5]}
        for g, e in counts.items()
    ]
    return sorted(out, key=lambda x: (-x["tracks"], x["genre"].lower()))


def apply_transform(paths, transform_fn, label):
    """Apply ``transform_fn(raw_genre) -> next_genre (None = keep)`` to paths.

    The transform sees the full raw genre value; ``primary_genre`` decides
    whether a track belongs to the targeted bucket.
    """
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
    """Replace every track whose primary genre is ``from_genre``.

    Multi-genre values are classified by their leftmost genre, so
    replace("Electronic", "EDM") rewrites "Electronic - Deep House; ..."
    entirely to "EDM" (one canonical genre per track).
    """
    return apply_transform(
        paths,
        lambda cur: to_genre if primary_genre(cur) == from_genre else None,
        f"Replacing genre '{from_genre}'")


def merge(paths, from_genres, to_genre):
    """Merge every track whose primary genre is in ``from_genres``."""
    targets = {primary_genre(g) for g in (from_genres or []) if g}
    return apply_transform(
        paths,
        lambda cur: to_genre if primary_genre(cur) in targets else None,
        "Merging genres")


def delete(paths, genre):
    """Remove the genre (empty tag) from tracks whose primary genre matches."""
    return apply_transform(
        paths,
        lambda cur: "" if primary_genre(cur) == genre else None,
        f"Removing genre '{genre}'")


def bulk_set(paths, value):
    return apply_transform(paths, lambda cur: value, "Setting genre")
