"""Uniform audio metadata reading/writing across FLAC and MP3 via mutagen.

Glacier stores an internal canonical tag view so that FLAC Vorbis comments and
MP3 ID3 tags present the same keys. Writing transparently maps the canonical
keys back onto the underlying format's native tags.
"""

import os

from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3, TIT2, TPE1, TPE2, TALB, TRCK, TDRC, TCON, TXXX, POPM
from mutagen.mp3 import MP3

# Canonical key -> per-format native tag map.
_CANONICAL = ["artist", "albumartist", "album", "title", "track", "date", "genre", "isrc", "rating"]

_MP3_MAP = {
    "artist": ("TPE1", "TPE1"),
    "albumartist": ("TPE2", "TPE2"),
    "album": ("TALB", "TALB"),
    "title": ("TIT2", "TIT2"),
    "track": ("TRCK", "TRCK"),
    "date": ("TDRC", "TDRC"),
    "genre": ("TCON", "TCON"),
    "isrc": ("TXXX:GLACIER_ISRC", "TXXX"),
    "rating": ("POPM", "POPM"),  # POPM user rating (0..255; 100 = 5 stars)
}

_FLAC_MAP = {
    "artist": "artist",
    "albumartist": "albumartist",
    "album": "album",
    "title": "title",
    "track": "tracknumber",
    "date": "date",
    "genre": "genre",
    "isrc": "isrc",
    "rating": "rating",
}


def resolve(path):
    """Return (reader_class, format) for a supported file, or (None, None)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".flac":
        return FLAC, "flac"
    if ext == ".mp3":
        return MP3, "mp3"
    return None, None


def read(path):
    """Return a canonical tag dict + format for one file.

    Never raises for metadata problems; returns best-effort values.
    """
    cls, fmt = resolve(path)
    if cls is None:
        return {"path": path, "format": None, "tags": {}, "bitrate": None,
                "duration": None, "error": "unsupported_format"}

    base = {"path": path, "format": fmt, "tags": {}, "error": None}
    try:
        audio = cls(path)
        base["duration"] = float(getattr(audio.info, "length", 0) or 0)
        base["bitrate"] = int(getattr(audio.info, "bitrate", 0) or 0)
        if fmt == "flac":
            base["samplerate"] = int(getattr(audio.info, "sample_rate", 0) or 0)
            base["bits"] = int(getattr(audio.info, "bits_per_sample", 0) or 0)
            _read_flac(audio, base)
        else:
            _read_mp3(audio, base)
    except Exception as exc:  # noqa: BLE001
        base["error"] = str(exc)
    return base


def _first_tag(audio, *keys):
    for key in keys:
        val = audio.get(key)
        if isinstance(val, list) and val:
            return str(val[0])
        if val:
            return str(val)
    return ""


def _read_flac(audio, base):
    tags = base["tags"]
    for canon, native in _FLAC_MAP.items():
        tags[canon] = _first_tag(audio, native)
    cover = audio.pictures[0].data if audio.pictures else None
    base["has_cover"] = bool(cover)


def _read_mp3(audio, base):
    tags = base["tags"]
    if audio.tags is None:
        return
    for canon, (fid, _kind) in _MP3_MAP.items():
        if fid == "POPM":
            tags[canon] = _mp3_popm_rating(audio.tags)
            continue
        frame = audio.tags.get(fid)
        tags[canon] = str(frame) if frame else ""
    base["has_cover"] = bool(audio.tags.get("APIC"))


def _mp3_popm_rating(tags):
    """Return the numeric rating from any POPM frame (email-scoped key)."""
    for _key, frame in tags.items():
        if isinstance(frame, POPM):
            return str(getattr(frame, "rating", 0))
    return ""


def write(path, tag_dict):
    """Write canonical tags to a file. Returns a dict with success/errors."""
    cls, fmt = resolve(path)
    if cls is None:
        return {"ok": False, "error": "unsupported_format", "path": path}
    try:
        audio = cls(path)
        if fmt == "flac":
            for canon, native in _FLAC_MAP.items():
                if canon in tag_dict:
                    audio[native] = [str(tag_dict[canon])] if tag_dict[canon] else []
        else:
            # Ensure ID3 exists before writing to MP3
            ensure_id3(path)
            # Reload audio after ensure_id3 (it may have been created)
            audio = cls(path)
            if audio.tags is None:
                # Fallback: create an empty ID3 container manually
                audio.add_tags()
            for canon, (fid, kind) in _MP3_MAP.items():
                if canon not in tag_dict:
                    continue
                val = tag_dict[canon]
                native = _native_mp3_frame(canon, val)
                # If native is None, skip (e.g., rating conversion failed)
                if native is not None:
                    audio.tags.setall(fid, [native])
                else:
                    # If we want to delete the tag, set empty list
                    audio.tags.setall(fid, [])
        audio.save()
        return {"ok": True, "path": path}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "path": path}


def _native_mp3_frame(canon, val):
    """Map a canonical key + string value back to an ID3 frame instance."""
    if not val:
        return None
    if canon == "artist":
        return TPE1(encoding=3, text=[str(val)])
    if canon == "albumartist":
        return TPE2(encoding=3, text=[str(val)])
    if canon == "album":
        return TALB(encoding=3, text=[str(val)])
    if canon == "title":
        return TIT2(encoding=3, text=[str(val)])
    if canon == "track":
        return TRCK(encoding=3, text=[str(val)])
    if canon == "date":
        return TDRC(encoding=3, text=[str(val)])
    if canon == "genre":
        return TCON(encoding=3, text=[str(val)])
    if canon == "isrc":
        return TXXX(encoding=3, desc="GLACIER_ISRC", text=[str(val)])
    if canon == "rating":
        try:
            return POPM(encoding=3, email="no@email", rating=int(float(val)))
        except (TypeError, ValueError):
            return None
    return None


def ensure_id3(path):
    """Attach an empty ID3 frame container to an MP3 if missing."""
    if os.path.splitext(path)[1].lower() == ".mp3":
        try:
            ID3(path)  # creates if missing
        except Exception:
            pass