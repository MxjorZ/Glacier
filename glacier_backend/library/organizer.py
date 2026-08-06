"""Organization engine.

Moves/renames files based on metadata using user-defined folder and filename
templates. Supports dry-run, preview, explicit apply, and an explicit target
library. Glacial never silently moves files: callers must pass dry_run and
obtain confirmation before applying.

Template fields: {artist} {albumartist} {album} {title} {track} {year}
Format specs (e.g. {track:02d}) are supported.
"""

import os
import re
import shutil

from .. import events

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WS = re.compile(r"\s+")


# Canonical fields understood by the template renderer. Anything else in a
# pattern is flagged as an unknown token in the live preview.
KNOWN_FIELDS = {"artist", "albumartist", "album", "title",
                "track", "year", "date", "genre", "isrc"}


def parse_track_num(raw_track):
    """Extract an integer track number from a raw tag value (e.g. '2' from '2/12')."""
    if not raw_track:
        return None
    m = re.search(r"\d+", str(raw_track))
    return int(m.group(0)) if m else None


def parse_year(raw_date):
    """Extract a 4-digit year from a raw date tag value."""
    if not raw_date:
        return None
    m = re.search(r"\d{4}", str(raw_date))
    return m.group(0) if m else None


def unknown_tokens(pattern):
    """Return token names in `pattern` that are not KNOWN_FIELDS."""
    unknown = []
    for m in re.finditer(r"\{([^}]+)\}", pattern or ""):
        field = m.group(1).split(":")[0]
        if field not in KNOWN_FIELDS:
            unknown.append(field)
    return unknown


def preview_path(folder_pattern, naming_pattern, tags, library_root=None,
                 ext=".flac"):
    """Render a live preview of the relative folder + filename for sample tags.

    Returns a dict with folder, filename, relative_path, optional full_path and
    any unknown tokens.
    """
    tags = tags or {}
    track_num = parse_track_num(tags.get("track"))
    year = parse_year(tags.get("date"))
    folder = render(folder_pattern, tags, track_num, year).strip("/\\")
    basename = render(naming_pattern, tags, track_num, year)
    filename = sanitize(basename) + ext
    relative_path = os.path.join(folder, filename) if folder else filename
    full_path = os.path.join(library_root, relative_path) if library_root else None
    return {
        "folder": folder,
        "filename": filename,
        "relative_path": relative_path,
        "full_path": full_path,
        "unknown_tokens": sorted(
            set(unknown_tokens(folder_pattern)) | set(unknown_tokens(naming_pattern))),
    }


def sanitize(name, fallback="Unknown"):
    name = _INVALID_CHARS.sub(" ", name or "")
    name = _WS.sub(" ", name).strip().rstrip(".")
    name = name[:120]  # avoid path-too-long issues
    return name or fallback


def render(pattern, tags, track_num=None, year=None):
    """Render a template string with tag values + format specs."""
    def repl(m):
        spec = m.group(1)
        field = spec.split(":")[0]
        fmt = spec.split(":", 1)[1] if ":" in spec else ""
        value = tags.get(field, "")
        # FALLBACK: if field is albumartist and empty, use artist
        if field == "albumartist" and not value:
            value = tags.get("artist", "")
        if field == "track":
            value = track_num if track_num is not None else tags.get("track", "")
        elif field == "year":
            value = year if year is not None else tags.get("date", "")
        value = sanitize(str(value or ""), "Unknown")
        try:
            if fmt:
                try:
                    return format(int(value), fmt)
                except ValueError:
                    return value
        except Exception:
            pass
        return value
    return re.sub(r"\{([^}]+)\}", repl, pattern)


def plan_library(tracks, root, folder_pattern, naming_pattern):
    """Build a move plan for one library's inventory.

    Returns a list of {source, destination, source_name, new_name, reason}.
    """
    plan = []
    used = set()
    for tr in tracks:
        if tr.get("error"):
            continue
        tags = tr.get("tags", {})
        # track number: prefer numeric portion ("2" from "2/12").
        raw_track = tags.get("track", "")
        track_num = None
        if raw_track:
            m = re.search(r"\d+", str(raw_track))
            if m:
                track_num = int(m.group(0))
        year = None
        raw_year = tags.get("date", "")
        m = re.search(r"\d{4}", str(raw_year))
        if m:
            year = m.group(0)

        rel_folder = render(folder_pattern, tags, track_num, year).strip("/\\")
        rel_name = render(naming_pattern, tags, track_num, year)
        ext = os.path.splitext(tr["path"])[1]
        new_name = rel_name + ext
        dest = os.path.join(root, rel_folder, new_name)
        dest = normalize_path(dest)
        # avoid collisions within the plan
        candidate = dest
        i = 1
        while candidate.lower() in used or (os.path.exists(candidate) and os.path.abspath(candidate) != os.path.abspath(tr["path"])):
            candidate = os.path.join(root, rel_folder, f"{rel_name} ({i}){ext}")
            i += 1
        dest = candidate
        used.add(dest.lower())
        src = tr["path"]
        if os.path.abspath(dest).lower() != os.path.abspath(src).lower():
            plan.append({
                "source": src,
                "destination": dest,
                "source_name": os.path.basename(src),
                "new_name": new_name,
                "reason": "metadata-based organization",
            })
    return plan


def normalize_path(path):
    """Ensure forward-only relative segments are clean and absolute."""
    path = os.path.normpath(path)
    parent = os.path.dirname(path)
    if parent and not os.path.isabs(parent):
        path = os.path.abspath(path)
    return path


def apply_plan(plan, root, backup=False):
    """Execute a move plan (create dirs + move). Returns (ok, moved, errors)."""
    moved = 0
    errors = []
    for i, item in enumerate(plan):
        try:
            src = item["source"]
            dst = item["destination"]
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            # guard against escaping the library root
            if not os.path.abspath(dst).startswith(os.path.abspath(root)):
                raise ValueError("Destination escapes library root")
            if backup:
                bak = src + ".bak"
                if os.path.exists(src):
                    shutil.copy2(src, bak)   # FIX: copy, not rename
            os.replace(src, dst)
            moved += 1
        except Exception as exc:  # noqa: BLE001
            errors.append({"source": item["source"], "error": str(exc)})
        if (i + 1) % 25 == 0:
            events.progress(i + 1, len(plan), "Organizing files")
    if plan:
        events.progress(len(plan), len(plan), "Organizing files")
    return moved, errors