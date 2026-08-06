"""Create-library-and-move extraction engine (Stage 2).

Given one or more source libraries, a set of combinable filters and a target
path, build a plan of matching files, then (on explicit confirmation) create the
destination library entry, create the folder, and MOVE (not copy) the files.

Filters (all combinable, AND semantics):
  * script       : hebrew | cyrillic | arabic | latin  (character-range heuristic)
  * genre_contains : case-insensitive substring of the genre tag
  * artists      : list of names (normalized) that must match artist/albumartist
  * path_regex   : regular expression matched against the full file path
  * tag_equals   : {"field": "value"}
  * tag_contains : {"field": "value"}
"""

import os
import re
import shutil

from .. import events
from .exclusivity import normalize
from ..cancel import is_cancelled, JobCancelled   # <-- ADDED

HEBREW_RE = re.compile(r"[\u0590-\u05ff\uFB1D-\uFB4F]")
CYRILLIC_RE = re.compile(r"[\u0400-\u04ff]")
ARABIC_RE = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]")
LATIN_RE = re.compile(r"[A-Za-z\u00c0-\u024f]")


def _script_blob(tags):
    parts = [tags.get("artist"), tags.get("albumartist"),
             tags.get("album"), tags.get("title")]
    return " ".join(str(p) for p in parts if p)


def _matches_script(tags, script):
    blob = _script_blob(tags)
    if script == "hebrew":
        return bool(HEBREW_RE.search(blob))
    if script == "cyrillic":
        return bool(CYRILLIC_RE.search(blob))
    if script == "arabic":
        return bool(ARABIC_RE.search(blob))
    if script == "latin":
        return bool(LATIN_RE.search(blob))
    return False


def matches(tags, path, filters):
    """Return True if a track matches all supplied filters (AND)."""
    filters = filters or {}
    if filters.get("script"):
        if not _matches_script(tags, filters["script"]):
            return False
    if filters.get("genre_contains"):
        genre = tags.get("genre") or ""
        if filters["genre_contains"].lower() not in str(genre).lower():
            return False
    if filters.get("artists"):
        wanted = {normalize(a) for a in filters["artists"]}
        artist = normalize(tags.get("artist") or tags.get("albumartist") or "")
        if not wanted or artist not in wanted:
            return False
    if filters.get("path_regex"):
        try:
            if not re.search(filters["path_regex"], path or ""):
                return False
        except re.error:
            return False
    for kind in ("tag_equals", "tag_contains"):
        spec = filters.get(kind)
        if spec:
            for field, value in spec.items():
                if field not in tags:
                    return False
                actual = str(tags.get(field) or "")
                if kind == "tag_equals" and actual != str(value):
                    return False
                if kind == "tag_contains" and str(value) not in actual:
                    return False
    return True


def _unique_basename(dir_path, basename):
    cand = os.path.join(dir_path, basename)
    if not os.path.exists(cand):
        return cand
    base, ext = os.path.splitext(basename)
    i = 1
    while os.path.exists(os.path.join(dir_path, f"{base} ({i}){ext}")):
        i += 1
    return os.path.join(dir_path, f"{base} ({i}){ext}")


def plan_extract(inventories, filters, target_path):
    """Build a move plan of matching files from source inventories.

    ``inventories`` is {library_id: {name, path, tracks:[...]}}. Returns list of
    {source, source_library_id, source_library_name, destination, size}.
    """
    plan = []
    for lib_id, info in inventories.items():
        for tr in info.get("tracks", []):
            if tr.get("error"):
                continue
            if not matches(tr.get("tags", {}), tr.get("path"), filters):
                continue
            dest = _unique_basename(target_path, os.path.basename(tr["path"]))
            plan.append({
                "source": tr["path"],
                "destination": dest,
                "source_library_id": lib_id,
                "source_library_name": info.get("name", ""),
                "size": tr.get("size", 0),
            })
    return plan


def execute_extract(plan, target_path):
    """Move planned files into the target directory (not copy)."""
    os.makedirs(target_path, exist_ok=True)
    moved = 0
    errors = []
    for i, item in enumerate(plan):
        if is_cancelled():
            raise JobCancelled()
        try:
            dest = _unique_basename(target_path, os.path.basename(item["source"]))
            shutil.move(item["source"], dest)
            moved += 1
        except Exception as exc:  # noqa: BLE001
            errors.append({"source": item["source"], "error": str(exc)})
        if (i + 1) % 25 == 0:
            events.progress(i + 1, len(plan), "Moving files into new library")
    if plan:
        events.progress(len(plan), len(plan), "Moving files into new library")
    return moved, errors