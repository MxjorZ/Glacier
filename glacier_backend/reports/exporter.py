"""Reports, covers, and playlists exporters."""

import json
import os
from collections import defaultdict

from .. import events
from ..library import metadata


# --- Covers --------------------------------------------------------------

def group_by_album(tracks):
    """Group tracks into album folders (by containing directory)."""
    albums = defaultdict(list)
    for tr in tracks:
        albums[os.path.dirname(tr["path"])].append(tr)
    return albums


def extract_covers(tracks, force=False, emit=True):
    """Extract embedded artwork to a cover file per album folder.

    Returns (created, errors). When ``force`` is True, existing cover files
    are overwritten (used by rebuild_covers).
    """
    created = 0
    errors = []
    albums = group_by_album(tracks)
    for i, (folder, group) in enumerate(albums.items()):
        existing = [f for f in os.listdir(folder)
                    if f.lower() in ("cover.jpg", "cover.png", "folder.jpg", "folder.png")
                    and os.path.isfile(os.path.join(folder, f))]
        if existing and not force:
            continue
        for tr in group:
            try:
                ext = os.path.splitext(tr["path"])[1].lower()
                if ext == ".flac":
                    from mutagen.flac import FLAC
                    audio = FLAC(tr["path"])
                    if audio.pictures:
                        pic = audio.pictures[0]
                        img_ext = (pic.mime.split("/")[-1] if pic.mime else "jpg")
                        target = os.path.join(folder, f"cover.{img_ext}")
                        with open(target, "wb") as fh:
                            fh.write(pic.data)
                        created += 1
                        if force:
                            # Clear stale cover files of other extensions.
                            for stale in os.listdir(folder):
                                if stale.lower() in (
                                        "cover.jpg", "cover.png",
                                        "folder.jpg", "folder.png") and stale != os.path.basename(target):
                                    try:
                                        os.remove(os.path.join(folder, stale))
                                    except OSError:
                                        pass
                        break
                elif ext == ".mp3":
                    from mutagen.id3 import ID3
                    audio = ID3(tr["path"])
                    apic = audio.get("APIC")
                    if apic:
                        img_ext = (apic.mime.split("/")[-1] if apic.mime else "jpg")
                        target = os.path.join(folder, f"cover.{img_ext}")
                        with open(target, "wb") as fh:
                            fh.write(apic.data)
                        created += 1
                        break
            except Exception as exc:  # noqa: BLE001
                errors.append({"path": tr["path"], "error": str(exc)})
        if emit and (i + 1) % 10 == 0:
            events.progress(i + 1, len(albums), "Extracting covers")
    if emit and albums:
        events.progress(len(albums), len(albums), "Extracting covers")
    return created, errors



# --- Playlists -----------------------------------------------------------

def generate_playlists(tracks, emit=True):
    """Generate an .m3u per album folder sorted by track number.

    Returns (created, errors).
    """
    created = 0
    errors = []
    albums = group_by_album(tracks)
    for i, (folder, group) in enumerate(albums.items()):
        try:
            def track_key(tr):
                raw = tr.get("tags", {}).get("track", "")
                try:
                    return int(str(raw).split("/")[0])
                except Exception:
                    return 0
            group = sorted(group, key=track_key)
            m3u_path = os.path.join(folder, os.path.basename(folder) + ".m3u")
            with open(m3u_path, "w", encoding="utf-8") as fh:
                fh.write("#EXTM3U\n")
                for tr in group:
                    fh.write("#EXTINF:{:.0f},{}\n{}\n".format(
                        tr.get("duration") or 0,
                        tr.get("tags", {}).get("title") or os.path.basename(tr["path"]),
                        os.path.basename(tr["path"])))
            created += 1
        except Exception as exc:  # noqa: BLE001
            errors.append({"path": folder, "error": str(exc)})
        if emit and (i + 1) % 10 == 0:
            events.progress(i + 1, len(albums), "Generating playlists")
    if emit and albums:
        events.progress(len(albums), len(albums), "Generating playlists")
    return created, errors


# --- Reports -------------------------------------------------------------

def to_json(library_payloads):
    return json.dumps(library_payloads, indent=2, ensure_ascii=False)


def to_text(stats_total, per_library, problems):
    lines = []
    lines.append("Glacier Library Report")
    lines.append("=" * 50)
    lines.append(f"Tracks:   {stats_total['tracks']}")
    lines.append(f"Artists:  {stats_total['artists']}")
    lines.append(f"Albums:   {stats_total['albums']}")
    lines.append(f"Size:     {stats_total['size'] / (1024**3):.2f} GB")
    lines.append("")
    for name, st in per_library.items():
        lines.append(f"[{name}]")
        lines.append(f"  tracks: {st['tracks']}  size: {st['size'] / (1024**2):.1f} MB")
    if problems:
        lines.append("")
        lines.append(f"Problems: {len(problems)}")
        for p in problems[:50]:
            lines.append(f"  - {p}")
    return "\n".join(lines)
