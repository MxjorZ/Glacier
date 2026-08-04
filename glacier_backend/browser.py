"""
Filesystem browser backend.

Designed for Linux/Docker environments:
- Browses the actual container filesystem
- Supports arbitrary bind mounts
- Does not hardcode music locations
- Provides audio metadata hints for the picker
"""

import os

from . import config


AUDIO_EXTS = {
    ext.lower()
    for ext in (config.SUPPORTED_EXTENSIONS or [])
}


MAX_DIRS = 5000
MAX_FILES = 100000
TOTAL_CAP = 100000


def _is_audio(filename):
    return os.path.splitext(filename)[1].lower() in AUDIO_EXTS


def _excluded():
    return {
        x.lower()
        for x in (config.DEFAULT_EXCLUDED_FOLDERS or [])
        if x
    }


def _safe_is_dir(path):
    try:
        return os.path.isdir(path)
    except OSError:
        return False


def _safe_is_file(path):
    try:
        return os.path.isfile(path)
    except OSError:
        return False


def _audio_direct(path):
    """
    Count audio files directly inside a folder.
    """

    count = 0

    try:
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    if entry.is_file() and _is_audio(entry.name):
                        count += 1
                except OSError:
                    continue

    except OSError:
        pass

    return count


def count_audio(path):
    """
    Recursive audio count.
    """

    count = 0
    scanned = 0
    excluded = _excluded()

    try:

        for root, dirs, files in os.walk(
            path,
            followlinks=False
        ):

            dirs[:] = [
                d for d in dirs
                if d.lower() not in excluded
                and not d.startswith(".")
            ]

            for file in files:

                scanned += 1

                if _is_audio(file):
                    count += 1

                if scanned >= TOTAL_CAP:
                    return count, True

    except OSError:
        pass

    return count, False


def list_dir(path=None):
    """
    Browse a directory.

    If path is empty:
    return filesystem roots.
    """

    if not path:
        return list_roots()


    path = os.path.abspath(
        os.path.expanduser(path)
    )


    if not _safe_is_dir(path):
        raise FileNotFoundError(
            f"Directory not found: {path}"
        )


    dirs = []
    files = []

    excluded = _excluded()
    audio_here = 0


    try:

        with os.scandir(path) as entries:

            for entry in entries:

                try:

                    name = entry.name


                    if name.startswith("."):
                        continue


                    if entry.is_dir(
                        follow_symlinks=False
                    ):

                        if name.lower() in excluded:
                            continue


                        dirs.append({
                            "name": name,
                            "path": entry.path,
                            "type": "dir",
                            "audio": _audio_direct(entry.path),
                            "audio_estimate": False,
                        })


                    elif entry.is_file():

                        audio = _is_audio(name)

                        if audio:
                            audio_here += 1


                        files.append({
                            "name": name,
                            "path": entry.path,
                            "type": "file",
                            "size": entry.stat().st_size,
                            "audio": audio,
                        })


                except OSError:
                    continue


    except PermissionError as exc:

        raise PermissionError(
            f"Permission denied: {path}"
        ) from exc



    dirs.sort(
        key=lambda x: x["name"].lower()
    )

    files.sort(
        key=lambda x: (
            not x["audio"],
            x["name"].lower()
        )
    )


    audio_total, estimate = count_audio(path)


    return {
        "path": path,

        "parent": (
            os.path.dirname(path)
            if path != "/"
            else None
        ),

        "dirs": dirs[:MAX_DIRS],
        "files": files[:MAX_FILES],

        "audio_here": audio_here,

        "audio_total": audio_total,
        "audio_total_estimate": estimate,

        "dirs_total": len(dirs),
        "files_total": len(files),

        "dirs_truncated": len(dirs) > MAX_DIRS,
        "files_truncated": len(files) > MAX_FILES,
    }


def list_roots():
    """
    Return actual filesystem roots.

    The user can navigate from here.
    """

    if os.name == "nt":

        roots = []

        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":

            drive = f"{letter}:\\"

            if os.path.exists(drive):

                roots.append({
                    "name": drive,
                    "path": drive,
                    "type": "dir",
                    "audio": None,
                    "audio_estimate": False,
                })


    else:

        roots = []

        for path in [
            "/",
            "/home",
            "/mnt",
            "/media",
            "/opt",
            "/srv",
            "/var",
        ]:

            if _safe_is_dir(path):

                roots.append({
                    "name": path,
                    "path": path,
                    "type": "dir",
                    "audio": None,
                    "audio_estimate": False,
                })


    return {
        "path": None,
        "parent": None,
        "dirs": roots,
        "files": [],
        "audio_here": 0,
        "audio_total": None,
        "audio_total_estimate": False,
    }