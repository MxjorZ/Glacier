"""Simple, reliable file mover for Glacier.

Reads metadata, applies user‑defined folder and filename patterns,
and moves files safely with dry‑run, logging, progress and cancellation.

Pattern syntax: ``{field}`` or ``{field:02d}`` (zero-padded, any width).
Supported fields are the canonical tags (artist, albumartist, album, title,
track, date, genre, isrc, rating) plus aliases: ``year`` (first 4 digits of
date), ``album_artist``/``artists`` (see config.PATTERN_FIELD_ALIASES).
Unknown tokens are left untouched so the preview can flag them.
"""

import os
import re
import shutil
from typing import Dict, List, Tuple

from . import events
from .cancel import is_cancelled, JobCancelled
from .config import PATTERN_FIELD_ALIASES

_TOKEN_RE = re.compile(r"\{([^}:]+)(?::(\d+)d)?\}")
_INVALID_FS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


# --- Tag reading ---------------------------------------------------------

def read_tags(path: str) -> Dict[str, str]:
    """Read canonical tags from a supported audio file (any format)."""
    from .library import metadata
    tags = {}
    try:
        rec = metadata.read(path)
        tags = dict(rec.get("tags") or {})
    except Exception as e:
        events.log(f"Failed to read tags from {path}: {e}", "warning")
    return tags


# --- Path rendering ------------------------------------------------------

def sanitize(name: str, fallback: str = "Unknown") -> str:
    """Clean a string for filesystem use."""
    if name is None:
        return fallback
    name = _INVALID_FS_RE.sub("", str(name))
    name = name.strip().rstrip(".").strip()
    return name or fallback


def field_value(field: str, tags: Dict[str, str]) -> str:
    """Resolve a pattern field to its raw string value ('' if unknown)."""
    # Aliases first ({year} -> date, {album_artist} -> albumartist, ...)
    for alias, sources in PATTERN_FIELD_ALIASES.items():
        if field == alias:
            for src in sources:
                val = str(tags.get(src) or "").strip()
                if val:
                    if alias == "year":
                        m = re.match(r"(\d{4})", val)
                        if m:
                            return m.group(1)
                        continue
                    return val
            return ""
    # albumartist falls back to artist
    if field == "albumartist":
        return str(tags.get("albumartist") or tags.get("artist") or "").strip()
    val = str(tags.get(field) or "").strip()
    if field == "track" and "/" in val:
        # "3/12" -> "3" (total belongs in {total_tracks}, not the filename)
        val = val.split("/")[0].strip()
    return val


def render_pattern(pattern: str, tags: Dict[str, str]) -> str:
    """Replace ``{field}`` / ``{field:02d}`` placeholders with tag values."""
    def repl(match):
        field, width = match.group(1), match.group(2)
        val = field_value(field, tags)
        if not val:
            return "Unknown"
        if width:
            try:
                return val.zfill(int(width))
            except ValueError:
                return val
        return sanitize(val)
    return _TOKEN_RE.sub(repl, pattern or "")


def unknown_tokens(pattern: str) -> List[str]:
    """List pattern tokens that no tag/alias can ever fill."""
    known = set(tags_keys_template())
    out = []
    for m in _TOKEN_RE.finditer(pattern or ""):
        f = m.group(1)
        if f not in known:
            out.append("{" + f + "}")
    return sorted(set(out))


def tags_keys_template():
    return ["artist", "albumartist", "album", "title", "track",
            "date", "genre", "isrc", "rating", *PATTERN_FIELD_ALIASES.keys()]


# --- Move planning -------------------------------------------------------

def plan_files(file_paths: List[str], folder_pattern: str, filename_pattern: str,
               library_root: str, skip_already_organized: bool = True,
               emit_progress: bool = False, library_name: str = "") -> List[Dict]:
    """Build a move plan for a list of files."""
    plan = []
    total = len(file_paths)
    if emit_progress:
        events.progress(0, total, f"Planning: {library_name}" if library_name else "Planning")
    for idx, src in enumerate(file_paths):
        if is_cancelled():
            raise JobCancelled()
        if emit_progress and (idx % 100 == 0 or idx == total - 1):
            events.progress(idx + 1, total, "Planning moves")
        if not os.path.isfile(src):
            continue
        tags = read_tags(src)
        folder = render_pattern(folder_pattern, tags)
        base = render_pattern(filename_pattern, tags)
        if not base or base.strip("Unknown").strip() == "":
            base = os.path.splitext(os.path.basename(src))[0]
        ext = os.path.splitext(src)[1]
        dest = os.path.join(library_root, folder, base + ext)
        if skip_already_organized and os.path.abspath(src) == os.path.abspath(dest):
            continue
        if not tags:
            continue
        plan.append({
            'source': src,
            'destination': dest,
            'source_name': os.path.basename(src),
            'folder': folder,
            'base': base,
            'ext': ext,
            'tags': tags,
        })
    if emit_progress:
        events.progress(total, total, "Planning complete")
    return plan


def _unique_path(dest: str) -> str:
    if not os.path.exists(dest):
        return dest
    base, ext = os.path.splitext(dest)
    i = 1
    while os.path.exists(f"{base} ({i}){ext}"):
        i += 1
    return f"{base} ({i}){ext}"


def execute_plan(plan: List[Dict], dry_run: bool = True, backup: bool = False,
                 copy: bool = False, emit_progress: bool = True) -> Tuple[int, List[str]]:
    """Execute a move (or copy) plan. Returns (moved_count, errors)."""
    moved = 0
    errors = []
    total = len(plan)
    action = 'copy' if copy else 'move'
    if emit_progress:
        events.progress(0, total, f"{action.capitalize()}ing files")
    for i, item in enumerate(plan):
        if is_cancelled():
            raise JobCancelled()
        src = item['source']
        dest = item['destination']
        if dry_run:
            events.log(f"[DRY] Would {action}: {src} -> {dest}", "verbose")
            moved += 1
            continue
        try:
            # Safety: prevent moving into itself
            if os.path.abspath(src) == os.path.abspath(dest):
                events.log(f"Skipping: source equals destination {src}", "warning")
                continue
            if not os.path.exists(src):
                events.log(f"Skipping: source no longer exists {src}", "warning")
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            # Never clobber an existing destination — rename beside it.
            dest = _unique_path(dest)
            # Optional backup
            if backup and os.path.exists(src):
                bak = src + ".bak"
                shutil.copy2(src, bak)
            if copy:
                shutil.copy2(src, dest)
            else:
                shutil.move(src, dest)
            moved += 1
            events.log(f"{action.capitalize()}d: {src} -> {dest}", "verbose")
        except Exception as e:
            errors.append(f"{src} -> {dest}: {e}")
            events.log(f"Error {action}ing {src}: {e}", "error")
        if emit_progress and (i % 25 == 0 or i == total - 1):
            events.progress(i + 1, total, f"{action.capitalize()}ing files")
    if emit_progress:
        events.progress(total, total, f"{action.capitalize()} complete")
    return moved, errors


def move_files(file_paths: List[str], folder_pattern: str, filename_pattern: str,
               library_root: str, dry_run: bool = True, backup: bool = False,
               copy: bool = False) -> Tuple[int, List[str]]:
    """High‑level wrapper: plan and execute in one call."""
    plan = plan_files(file_paths, folder_pattern, filename_pattern, library_root)
    return execute_plan(plan, dry_run=dry_run, backup=backup, copy=copy)
