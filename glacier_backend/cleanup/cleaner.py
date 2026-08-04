"""Cleanup tools.

Operations:
  * empty folders         - folders with no audio files
  * duplicate folder shells - empty folders that only hold non-audio files
                              adjacent to a real album folder
  * missing tags          - files missing key identity tags
  * corrupt files         - files that fail to parse

All cleaning is preview-first; deletion only happens on explicit apply.
"""

import os

from .. import events
from ..library import metadata

REQUIRED_TAGS = ["artist", "title"]


def find_empty_folders(root, excluded):
    """Find folders that contain no audio files (recursively)."""
    excluded_lower = {e.lower() for e in excluded if e}
    empty = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d.lower() not in excluded_lower and not d.startswith(".")]
        has_audio = any(
            os.path.splitext(f)[1].lower() in {".flac", ".mp3", ".ogg", ".m4a", ".opus", ".wma"}
            for f in filenames
        )
        if not has_audio and dirpath != root:
            empty.append(dirpath)
    # Only report deepest-empty folders; skip parents that contain an empty child.
    empty = [d for d in empty if not any(
        os.path.commonpath([d, e]) == d and d != e for e in empty)]
    return empty


def apply_remove_dirs(dirs):
    """Remove a list of empty directories (leaves only). Returns (ok, removed, errors)."""
    removed = 0
    errors = []
    for d in sorted(dirs, key=len, reverse=True):
        try:
            if os.path.isdir(d) and not os.listdir(d):
                os.rmdir(d)
                removed += 1
        except OSError as exc:
            errors.append({"path": d, "error": str(exc)})
    return removed, errors


def find_missing_tags(tracks):
    """Find files missing required identity tags."""
    out = []
    for tr in tracks:
        if tr.get("error"):
            continue
        missing = [f for f in REQUIRED_TAGS if not tr.get("tags", {}).get(f)]
        if missing:
            out.append({"path": tr["path"], "missing": missing})
    return out


def find_corrupt(tracks):
    """Find files whose metadata could not be read."""
    return [tr["path"] for tr in tracks if tr.get("error")]


def find_dup_folders(tracks, root):
    """Heuristic: duplicate folder shells = folders whose only content is
    non-audio files while an identically-named album folder with audio exists."""
    from collections import defaultdict
    audio_dirs = set()
    for tr in tracks:
        audio_dirs.add(os.path.dirname(tr["path"]))
    audio_names = defaultdict(list)
    for ad in audio_dirs:
        audio_names[os.path.basename(ad).lower()].append(ad)

    shells = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = []
        audio_here = any(
            os.path.splitext(f)[1].lower() in {".flac", ".mp3", ".ogg", ".m4a", ".opus", ".wma"}
            for f in filenames
        )
        if audio_here:
            continue
        name = os.path.basename(dirpath).lower()
        if name in audio_names and dirpath not in audio_dirs:
            # The folder has no audio but a sibling album folder with the same name exists.
            has_sibling = any(
                d != dirpath and os.path.basename(d).lower() == name for d in audio_dirs)
            if has_sibling:
                shells.append(dirpath)
    return shells
