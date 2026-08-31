"""Uniform audio metadata reading/writing across formats via mutagen.

Glacier stores an internal canonical tag view so FLAC Vorbis comments, MP3 ID3
frames and Ogg/MP4/ASF tags all present the same keys. Reading goes through
``mutagen.File`` (one code path for every supported format, including
easy-mode MP3 which exposes the same dict interface as Vorbis comments).
Writing transparently maps the canonical keys back onto the underlying format.

Supported extensions: .flac .mp3 .ogg .opus .m4a/.mp4 .wma .wav
"""

import os

from mutagen import File as MutagenFile
from mutagen.flac import FLAC
from mutagen.id3 import ID3, TIT2, TPE1, TPE2, TALB, TRCK, TDRC, TCON, TXXX, POPM
from mutagen.mp3 import MP3

# Canonical key -> per-format native tag map.
_CANONICAL = ["artist", "albumartist", "album", "title", "track", "date",
              "genre", "isrc", "rating"]

# Generic (Vorbis-comment-like) tag names used by FLAC/OGG/Opus and by
# mutagen's easy-MP3/MP4/ASF interfaces.
_GENERIC_MAP = {
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

# MP4 atom names (mutagen MP4Tags uses freeform-ish keys like 'albumartist').
_MP4_MAP = {
    "artist": "\xa9ART",
    "albumartist": "aART",
    "album": "\xa9alb",
    "title": "\xa9nam",
    "track": "trkn",
    "date": "\xa9day",
    "genre": "\xa9gen",
    "isrc": "----:com.apple.iTunes:ISRC",
    "rating": None,  # no standard atom; skipped
}

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

_WMA_MAP = {
    "artist": "Author",
    "albumartist": "AlbumArtist",
    "album": "WM/AlbumTitle",
    "title": "Title",
    "track": "WM/TrackNumber",
    "date": "WM/Year",
    "genre": "WM/Genre",
    "isrc": None,
    "rating": None,
}

_FORMAT_BY_EXT = {
    ".flac": "flac",
    ".mp3": "mp3",
    ".ogg": "ogg",
    ".oga": "ogg",
    ".opus": "opus",
    ".m4a": "m4a",
    ".mp4": "m4a",
    ".wma": "wma",
    ".wav": "wav",
}


def resolve(path):
    """Return (format, ) for a supported file, or (None, )."""
    return _FORMAT_BY_EXT.get(os.path.splitext(path)[1].lower()), None


def _first_str(val):
    """Mutagen values can be str, list, tuple, or numbers; coerce to str."""
    if isinstance(val, (list, tuple)):
        if not val:
            return ""
        val = val[0]
    if val is None:
        return ""
    # MP4 trkn is a (track, total) tuple of numbers.
    if isinstance(val, tuple):
        val = val[0] if val else ""
    return str(val)


def read(path):
    """Return a canonical tag dict + format for one file.

    Never raises for metadata problems; returns best-effort values.
    """
    fmt, _ = resolve(path)
    base = {"path": path, "format": fmt, "tags": {}, "bitrate": None,
            "duration": None, "samplerate": None, "bits": None, "error": None,
            "has_cover": False}
    if fmt is None:
        base["error"] = "unsupported_format"
        return base
    try:
        if fmt == "wav":
            # WAVE's easy mode does not translate ID3 frames -> read raw.
            from mutagen.wave import WAVE
            audio = WAVE(path)
            info = getattr(audio, "info", None)
            if info is not None:
                base["duration"] = float(getattr(info, "length", 0) or 0)
                base["samplerate"] = int(getattr(info, "sample_rate", 0) or 0)
                base["bits"] = int(getattr(info, "bits_per_sample", 0) or 0)
            if audio.tags:
                tags = base["tags"]
                for canon, (fid, _kind) in _MP3_MAP.items():
                    if fid == "POPM":
                        tags[canon] = _popm_rating(audio.tags)
                        continue
                    frame = audio.tags.get(fid)
                    tags[canon] = str(frame) if frame else ""
                tr = tags.get("track") or ""
                if tr:
                    tags["track"] = str(tr).split("/")[0].strip()
                base["has_cover"] = bool(audio.tags.get("APIC"))
            return base

        audio = MutagenFile(path, easy=True)
        if audio is None:
            base["error"] = "unreadable_file"
            return base
        info = getattr(audio, "info", None)
        if info is not None:
            base["duration"] = float(getattr(info, "length", 0) or 0)
            base["bitrate"] = int(getattr(info, "bitrate", 0) or 0)
            base["samplerate"] = int(getattr(info, "sample_rate", 0) or 0)
            base["bits"] = int(getattr(info, "bits_per_sample", 0) or 0)

        tags = base["tags"]
        for canon, native in _GENERIC_MAP.items():
            try:
                val = audio.get(native)
            except Exception:
                val = None
            tags[canon] = _first_str(val)

        # Normalize track to the leading number ("3/12" -> "3").
        tr = tags.get("track") or ""
        if tr:
            tags["track"] = str(tr).split("/")[0].strip()

        # Cover detection without full picture data (cheap).
        base["has_cover"] = _has_cover(path, audio)
    except Exception as exc:  # noqa: BLE001
        base["error"] = str(exc)
    return base


def _popm_rating(tags):
    """Return the numeric rating from any POPM frame (email-scoped key)."""
    for _key, frame in tags.items():
        if isinstance(frame, POPM):
            return str(getattr(frame, "rating", 0))
    return ""


def _has_cover(path, easy_audio):
    """Best-effort embedded-artwork detection (never raises)."""
    try:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".flac":
            return bool(easy_audio and getattr(easy_audio, "pictures", None))
        if ext == ".mp3":
            raw = MP3(path)
            return bool(raw.tags and raw.tags.get("APIC"))
        if ext in (".m4a", ".mp4"):
            raw = MutagenFile(path, easy=False)
            return any(str(k) == "covr" for k in (raw.keys() if raw else []))
        if ext == ".wma":
            raw = MutagenFile(path, easy=False)
            return bool(raw and raw.get("WM/Picture"))
        return False
    except Exception:  # noqa: BLE001
        return False


def write(path, tag_dict):
    """Write canonical tags to a file. Returns a dict with success/errors."""
    fmt, _ = resolve(path)
    if fmt is None:
        return {"ok": False, "error": "unsupported_format", "path": path}
    try:
        if fmt in ("flac", "ogg", "opus"):
            audio = MutagenFile(path, easy=True)
            if audio is None:
                return {"ok": False, "error": "unreadable_file", "path": path}
            for canon, native in _GENERIC_MAP.items():
                if canon in tag_dict:
                    val = str(tag_dict[canon]) if tag_dict[canon] else ""
                    if val:
                        audio.tags[native] = val
                    else:
                        # VComment/EasyID3 pop() takes no default argument.
                        if native in audio.tags:
                            del audio.tags[native]
            audio.save()
            return {"ok": True, "path": path}

        if fmt == "mp3":
            return _write_mp3(path, tag_dict)
        if fmt == "wav":
            # WAV carries ID3 tags; mutagen's easy mode doesn't cover it.
            return _write_wav(path, tag_dict)
        if fmt == "m4a":
            return _write_mp4(path, tag_dict)
        if fmt == "wma":
            return _write_wma(path, tag_dict)
        return {"ok": False, "error": "unsupported_format", "path": path}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "path": path}


def _write_mp3(path, tag_dict):
    audio = MP3(path)
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags
    for canon, (fid, _kind) in _MP3_MAP.items():
        if canon not in tag_dict:
            continue
        val = tag_dict[canon]
        frame = _mp3_frame(canon, val)
        if canon == "rating":
            # POPM is keyed by email; drop all existing POPM first.
            for key in [k for k in list(tags.keys()) if k.startswith("POPM:")]:
                del tags[key]
            if frame is not None:
                tags.setall("POPM:glacier", [frame])
        elif frame is not None:
            tags.setall(fid, [frame])
        else:
            tags.delall(fid)
    audio.save()
    return {"ok": True, "path": path}


def _mp3_frame(canon, val):
    """Map a canonical key + string value back to an ID3 frame instance."""
    if not val:
        return None
    text = str(val)
    if canon == "artist":
        return TPE1(encoding=3, text=[text])
    if canon == "albumartist":
        return TPE2(encoding=3, text=[text])
    if canon == "album":
        return TALB(encoding=3, text=[text])
    if canon == "title":
        return TIT2(encoding=3, text=[text])
    if canon == "track":
        return TRCK(encoding=3, text=[text])
    if canon == "date":
        return TDRC(encoding=3, text=[text])
    if canon == "genre":
        return TCON(encoding=3, text=[text])
    if canon == "isrc":
        return TXXX(encoding=3, desc="GLACIER_ISRC", text=[text])
    if canon == "rating":
        try:
            return POPM(email="glacier", rating=int(float(text)))
        except (TypeError, ValueError):
            return None
    return None


def _write_mp4(path, tag_dict):
    audio = MutagenFile(path, easy=False)
    if audio is None:
        return {"ok": False, "error": "unreadable_file", "path": path}
    easy = MutagenFile(path, easy=True)
    for canon, atom in _MP4_MAP.items():
        if canon not in tag_dict or atom is None:
            continue
        val = str(tag_dict[canon]) if tag_dict[canon] else ""
        try:
            if canon == "track":
                if val:
                    m = val.split("/")[0].strip()
                    easy.tags[atom] = [(int(m), 0)]
                else:
                    audio.tags.pop(atom, None)
            elif val:
                easy.tags[atom] = val
            else:
                audio.tags.pop(atom, None)
        except Exception:
            continue
    easy.save()
    return {"ok": True, "path": path}


def _write_wav(path, tag_dict):
    from mutagen.wave import WAVE
    audio = WAVE(path)
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags
    for canon, (fid, _kind) in _MP3_MAP.items():
        if canon not in tag_dict:
            continue
        frame = _mp3_frame(canon, tag_dict[canon])
        if canon == "rating":
            for key in [k for k in list(tags.keys()) if k.startswith("POPM:")]:
                del tags[key]
            if frame is not None:
                tags.setall("POPM:glacier", [frame])
        elif frame is not None:
            tags.setall(fid, [frame])
        else:
            tags.delall(fid)
    audio.save()
    return {"ok": True, "path": path}


def _write_wma(path, tag_dict):
    audio = MutagenFile(path, easy=True)
    if audio is None:
        return {"ok": False, "error": "unreadable_file", "path": path}
    for canon, native in _WMA_MAP.items():
        if canon not in tag_dict or native is None:
            continue
        val = str(tag_dict[canon]) if tag_dict[canon] else ""
        if val:
            audio.tags[native] = val
        else:
            audio.tags.pop(native, None)
    audio.save()
    return {"ok": True, "path": path}


def ensure_id3(path):
    """Attach an empty ID3 frame container to an MP3 if missing."""
    if os.path.splitext(path)[1].lower() == ".mp3":
        try:
            ID3(path)  # creates if missing
        except Exception:
            pass
