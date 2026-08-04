"""Filesystem directory browser used by the folder picker."""

import os


def list_dir(path):
    """Return subdirectories and files for a path (or common roots when empty).
    """
    if not path or not path.strip():
        return list_roots()
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(path):
        raise FileNotFoundError(f"Not a directory: {path}")
    try:
        entries = sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError as exc:
        raise PermissionError(f"Permission denied: {path}") from exc

    dirs = [{"name": e.name, "path": e.path, "type": "dir"}
            for e in entries if e.is_dir()]
    files = [{"name": e.name, "path": e.path, "type": "file", "size": e.stat().st_size}
             for e in entries if e.is_file()]
    return {"path": path, "parent": os.path.dirname(path) or None,
            "dirs": dirs[:200], "files": files[:200]}


def list_roots():
    """Return common mount roots for the OS."""
    if os.name == "nt":
        roots = []
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            drive = letter + ":\\"
            if os.path.exists(drive):
                roots.append({"name": drive, "path": drive, "type": "dir"})
        home = os.path.expanduser("~")
        roots.append({"name": "Home", "path": home, "type": "dir"})
        return {"path": None, "parent": None, "dirs": roots, "files": []}
    roots = [{"name": "Home", "path": os.path.expanduser("~"), "type": "dir"},
             *[{"name": p, "path": p, "type": "dir"} for p in ("/mnt", "/media", "/opt")]]
    return {"path": None, "parent": None, "dirs": roots, "files": []}
