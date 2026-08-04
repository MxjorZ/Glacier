"""Filesystem directory browser used by the folder picker.

Audio-aware: alongside folders it also returns the files inside a directory
(flagged as audio vs not) plus song counts, so the UI can show whether a chosen
folder actually contains music before it is added as a library.
"""

import os

from . import config

# Extensions Glacier can read metadata for; used to flag audio files.
AUDIO_EXTS = {e.lower() for e in (config.SUPPORTED_EXTENSIONS or [])}


def _is_audio(name):
    return os.path.splitext(name)[1].lower() in AUDIO_EXTS


def _excluded_lower():
    return {e.lower() for e in (config.DEFAULT_EXCLUDED_FOLDERS or []) if e}


# Safety cap for the single recursive total-count walk of the CURRENT folder
# (only done once per listing, not per subfolder, so huge trees stay fast and
# the result is just marked as an estimate when truncated).
TOTAL_CAP = 100000


def count_audio(root, cap=TOTAL_CAP):
    """Recursive audio-file count in ``root`` (used only for the current folder).

    Returns ``(count, is_estimate)``. ``is_estimate`` is True when the walk hit
    the safety cap before finishing (very large trees). Stops early on most
    errors and never raises.
    """
    count = 0
    visited = 0
    excluded = _excluded_lower()
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames
                if d.lower() not in excluded and not d.startswith(".")
            ]
            for name in filenames:
                visited += 1
                if _is_audio(name):
                    count += 1
                if visited >= cap:
                    return count, True
    except OSError:
        pass
    return count, False


def _audio_direct(root):
    """Audio files DIRECTLY inside ``root`` (no recursion — fast for the
    file-explorer listing where we never want to crawl entire trees)."""
    count = 0
    try:
        with os.scandir(root) as it:
            for e in it:
                if e.is_file() and _is_audio(e.name):
                    count += 1
    except OSError:
        pass
    return count


def list_dir(path):
    """Return subdirectories and files for a path (or common roots when empty).

    Fast / native-like: it never recursively scans subfolders for this listing.
    Each folder entry carries ``audio`` = audio files DIRECTLY inside it (cheap),
    and the response reports the recursive ``audio_total`` for the CURRENT folder
    only (a single bounded walk). Files carry ``audio`` to flag songs.
    """
    if not path or not path.strip():
        return list_roots()
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(path):
        raise FileNotFoundError(f"Not a directory: {path}")
    try:
        entries = sorted(os.scandir(path),
                         key=lambda e: (not e.is_dir(), not _is_audio(e.name) if e.is_file() else False, e.name.lower()))
    except PermissionError as exc:
        raise PermissionError(f"Permission denied: {path}") from exc

    excluded = _excluded_lower()
    dirs = []
    files = []
    audio_here = 0
    for e in entries:
        try:
            if e.is_dir():
                if e.name.lower() in excluded or e.name.startswith("."):
                    continue
                dirs.append({"name": e.name, "path": e.path, "type": "dir",
                             "audio": _audio_direct(e.path), "audio_estimate": False})
            elif e.is_file():
                audio = _is_audio(e.name)
                if audio:
                    audio_here += 1
                files.append({"name": e.name, "path": e.path, "type": "file",
                              "size": e.stat().st_size, "audio": audio})
        except OSError:
            continue

    audio_total, audio_total_est = count_audio(path)

    # File-explorer-like: don't silently hide entries. Use high safety caps only
    # against truly pathological folders and report when anything was cut.
    MAX_DIRS = 5000
    MAX_FILES = 100000
    return {"path": path, "parent": os.path.dirname(path) or None,
            "dirs": dirs[:MAX_DIRS], "files": files[:MAX_FILES],
            "audio_here": audio_here,
            "audio_total": audio_total, "audio_total_estimate": audio_total_est,
            "dirs_total": len(dirs), "files_total": len(files),
            "dirs_truncated": len(dirs) > MAX_DIRS,
            "files_truncated": len(files) > MAX_FILES}


def list_roots():
    """Return common mount roots for the OS."""
    if os.name == "nt":
        roots = []
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            drive = letter + ":\\"
            if os.path.exists(drive):
                roots.append({"name": drive, "path": drive, "type": "dir",
                              "audio": None, "audio_estimate": False})
        home = os.path.expanduser("~")
        roots.append({"name": "Home", "path": home, "type": "dir",
                      "audio": None, "audio_estimate": False})
        return {"path": None, "parent": None, "dirs": roots,
                "files": [], "audio_here": 0, "audio_total": None,
                "audio_total_estimate": False}
    roots = [{"name": "Home", "path": os.path.expanduser("~"), "type": "dir",
              "audio": None, "audio_estimate": False},
             {"name": "Root /", "path": "/", "type": "dir",
              "audio": None, "audio_estimate": False},
             *[{"name": p, "path": p, "type": "dir",
                "audio": None, "audio_estimate": False}
               for p in ("/mnt", "/media", "/opt")]]
    return {"path": None, "parent": None, "dirs": roots,
            "files": [], "audio_here": 0, "audio_total": None,
            "audio_total_estimate": False}
