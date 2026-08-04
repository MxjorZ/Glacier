#!/usr/bin/env python3
"""
Songanizer Pro
Flask localhost web app — multi-folder music library management,
AI discovery, Plex integration, genre/artist filtering, and comprehensive cleanup tools.

Install:  pip install flask mutagen plexapi
Run:      python rebuild_music.py
URL:      http://localhost:5050  |  http://<your-ip>:5050
"""

import re, json, shutil, time, sys, os, datetime, threading, queue, socket, webbrowser
import urllib.request, urllib.parse, subprocess
from collections import defaultdict
from pathlib import Path

try:
    from flask import Flask, Response, jsonify, request, stream_with_context
except ImportError:
    print("[!] Flask not found.  Run:  pip install flask mutagen"); raise SystemExit(1)

try:
    from mutagen.flac import FLAC
    from mutagen.id3 import ID3, APIC, TIT2, TPE1, TPE2, TALB, TRCK, TDRC, TCON
    from mutagen.mp3 import MP3
    _MUT = True
except ImportError:
    _MUT = False
    print("[!] mutagen not found.  Run:  pip install mutagen")

# ════════════════════════════════════════════════════════════════
#  SETTINGS
# ════════════════════════════════════════════════════════════════
SETTINGS_FILE = Path.home() / ".songanizer_settings.json"
DEFAULT_SETTINGS = {
    "folders":            [],  # Multiple folders support
    "extensions":         [".flac", ".mp3"],
    "excluded_folders":   ["Playlists", "- Playlists"],
    "folder_pattern":     "{albumartist}/{album} ({year})",
    "naming_pattern":     "{artist} - {album} - {track:02d} - {title}",
    "backup_before_move": False,
    "auto_playlist":      False,
    "log_to_file":        False,
    "log_path":           str(Path.home() / "songanizer_log.txt"),
    "dup_priority":       "deluxe",
    "cover_format":       "png",
    "accent1":            "#7c3aed",
    "accent2":            "#06b6d4",
    "glow_opacity":       0.18,
    # AI keys
    "openai_key":   "",
    "gemini_key":   "",
    "claude_key":   "",
    "ai_providers": ["openai"],  # Multiple AI engines support
    # Genre removal
    "genres_to_remove":  [],
    "protected_artists": [],
    "protected_albums":  [],
    "protected_songs":   [],
    # AI Discovery filters
    "ai_genre_filter":   [],
    "ai_artist_filter":   [],
    # Plex settings
    "plex_url":          "http://127.0.0.1:32400",
    "plex_token":        "",
    "plex_music_section": "Music",
    "plex_target_rating": 10.0,
}


def _load():
    try:
        if SETTINGS_FILE.exists():
            s = json.loads(SETTINGS_FILE.read_text("utf-8"))
            m = dict(DEFAULT_SETTINGS); m.update(s); return m
    except Exception: pass
    return dict(DEFAULT_SETTINGS)


def _save(d):
    try: SETTINGS_FILE.write_text(json.dumps(d, indent=2), "utf-8")
    except Exception as e: print(f"[warn] settings save: {e}")


# ════════════════════════════════════════════════════════════════
#  FLASK APP + GLOBAL STATE
# ════════════════════════════════════════════════════════════════
app     = Flask(__name__, static_folder=None)
_events = queue.Queue(maxsize=4000)
_lock   = threading.Lock()
_processing = False


def _emit(t, **kw): _events.put({"type": t, **kw})
def _log(m, lv="info"): _emit("log", message=m, level=lv)
def _progress(cur, tot, lbl=""): _emit("progress", current=cur, total=max(tot,1), label=lbl)
def _done(m): _emit("done", message=m); globals().__setitem__('_processing', False)


# ════════════════════════════════════════════════════════════════
#  AUDIO UTILITIES
# ════════════════════════════════════════════════════════════════
def _clean(n):
    for c in r'<>:"/\|?*': n = n.replace(c, "")
    return re.sub(r"\s+", " ", n).strip()

def _is_hebrew(text):
    """Check if text contains Hebrew characters."""
    if not text:
        return False
    return bool(re.search(r'[\u0590-\u05FF]', text))

def _normalize_hebrew_artist(tags):
    """
    If artist has both Hebrew and English names, keep only Hebrew.
    If only English exists, keep it.
    """
    artist = tags.get("artist", "")
    albumartist = tags.get("albumartist", "")
    
    # Check albumartist first, then artist
    primary = albumartist or artist
    
    # If primary contains Hebrew, prefer that
    if _is_hebrew(primary):
        return _clean(primary)
    
    # Otherwise return the primary as-is
    return _clean(primary) if primary else "Unknown Artist"

def _main_artist(tags):
    raw = tags.get("albumartist") or tags.get("artist") or "Unknown Artist"
    p = re.split(r";|,|feat\.|featuring|ft\.|&", str(raw), flags=re.IGNORECASE)
    # Apply Hebrew normalization
    cleaned = _clean((p[0].strip() if p else raw) or "Unknown Artist")
    return _normalize_hebrew_artist({"artist": cleaned, "albumartist": cleaned})

def _get_files(folder, settings):
    exts = settings.get("extensions", [".flac", ".mp3"])
    excl = settings.get("excluded_folders", [])
    out  = []
    for ext in exts:
        for f in Path(folder).rglob(f"*{ext}"):
            if not any(ex in str(f) for ex in excl if ex):
                out.append(f)
    return out

def _get_all_files(settings):
    """Get files from all loaded folders."""
    all_files = []
    folders = settings.get("folders", [])
    for folder in folders:
        if folder and Path(folder).exists():
            all_files.extend(_get_files(folder, settings))
    return all_files

def _read_tags(fp):
    if not _MUT: return None
    try:
        s = fp.suffix.lower()
        if s == ".flac":
            a = FLAC(fp)
            return {
                "artist":      a.get("artist",      ["Unknown Artist"])[0],
                "albumartist": a.get("albumartist",  a.get("artist", ["Unknown Artist"]))[0],
                "title":       a.get("title",        ["Unknown Title"])[0],
                "album":       a.get("album",        ["Unknown Album"])[0],
                "tracknumber": a.get("tracknumber",  ["0"])[0].split("/")[0].zfill(2),
                "date":        a.get("date",         ["Unknown Year"])[0][:4],
                "genre":       a.get("genre",        [""])[0],
                "bitrate":     "FLAC",
            }
        elif s == ".mp3":
            a = MP3(fp)
            return {
                "artist":      str(a.get("TPE1", "Unknown Artist")),
                "albumartist": str(a.get("TPE2", a.get("TPE1", "Unknown Artist"))),
                "title":       str(a.get("TIT2", "Unknown Title")),
                "album":       str(a.get("TALB", "Unknown Album")),
                "tracknumber": str(a.get("TRCK", "0")).split("/")[0].zfill(2),
                "date":        str(a.get("TDRC", "Unknown Year"))[:4],
                "genre":       str(a.get("TCON", "")),
                "bitrate":     f"{a.info.bitrate // 1000} kbps",
            }
    except Exception: return None

def _duration(fp):
    if not _MUT: return 0
    try:
        s = fp.suffix.lower()
        if s == ".flac": return int(FLAC(fp).info.length)
        if s == ".mp3":  return int(MP3(fp).info.length)
    except Exception: return 0

def _fmt_size(b):
    for u in ("B","KB","MB","GB","TB"):
        if b < 1024: return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} PB"

def _album_folders(folder, settings):
    result = set()
    exts = settings.get("extensions", [".flac", ".mp3"])
    for d in Path(folder).rglob("*"):
        if d.is_dir() and re.search(r"\(\d{4}\)|Unknown Year", d.name):
            if any(list(d.glob(f"*{e}"))[:1] for e in exts): result.add(d)
    return result

def _extract_cover(fp, out):
    if not _MUT: return False
    try:
        if fp.suffix.lower() == ".flac":
            for pic in FLAC(fp).pictures:
                if pic.type == 3: out.write_bytes(pic.data); return True
        elif fp.suffix.lower() == ".mp3":
            for tag in ID3(fp).values():
                if isinstance(tag, APIC): out.write_bytes(tag.data); return True
    except Exception: pass
    return False

def _build_dest(folder, tags, fp, settings):
    fp  = fp if isinstance(fp, Path) else Path(fp)
    fol = settings.get("folder_pattern", "{albumartist}/{album} ({year})")
    nam = settings.get("naming_pattern", "{artist} - {album} - {track:02d} - {title}")
    try: tr = int(tags["tracknumber"])
    except Exception: tr = 0
    # Apply Hebrew normalization to artist names
    normalized_artist = _normalize_hebrew_artist(tags)
    tv = {"artist":      _clean(tags["artist"]),
          "albumartist": _clean(tags.get("albumartist") or _main_artist(tags)),
          "album":       _clean(tags["album"]),
          "year":        tags["date"] if tags["date"] != "Unknown Year" else "Unknown Year",
          "track":       tr, "title":  _clean(tags["title"])}
    # Override with normalized artist if Hebrew
    if _is_hebrew(tags.get("albumartist", "")) or _is_hebrew(tags.get("artist", "")):
        tv["albumartist"] = normalized_artist
        tv["artist"] = normalized_artist
    try:     folder_rel = fol.format(**tv)
    except:  folder_rel = f"{tv['albumartist']}/{tv['album']} ({tv['year']})"
    try:     base = nam.format(**tv)
    except:  base = f"{tv['artist']} - {tv['album']} - {tr:02d} - {tv['title']}"
    dest_dir = Path(folder)
    for part in folder_rel.replace("\\", "/").split("/"):
        dest_dir = dest_dir / _clean(part)
    return dest_dir, dest_dir / (_clean(base) + fp.suffix)


# ════════════════════════════════════════════════════════════════
#  OPERATIONS
# ════════════════════════════════════════════════════════════════
def _op_analyze(settings):
    _log("📊 Analyzing library…")
    files = _get_all_files(settings)
    total = len(files)
    _progress(0, total or 1, "Analyzing…")
    ext_c = defaultdict(int); arts = set(); albs = set(); sz = 0; mp3br = defaultdict(int); folder_counts = defaultdict(int)
    
    folders = settings.get("folders", [])
    for f in files:
        # Track which folder the file belongs to
        for folder in folders:
            if str(f).startswith(str(Path(folder))):
                folder_counts[folder] += 1
                break
        s = f.suffix.lower(); ext_c[s] += 1; sz += f.stat().st_size
        if s == ".mp3":
            try: mp3br[MP3(f).info.bitrate//1000] += 1
            except: pass
        t = _read_tags(f)
        if t: 
            a = _main_artist(t)
            arts.add(a)
            albs.add(f"{a}/{t['album']}")
        _progress(len([x for x in files if x <= f]), total or 1)
    
    _log(f"  Total Files : {total:,}", "success")
    for ext, cnt in sorted(ext_c.items()): _log(f"  {ext.upper():7}: {cnt:,}")
    _log(f"  Artists     : {len(arts):,}"); _log(f"  Albums      : {len(albs):,}")
    _log(f"  Library Size: {_fmt_size(sz)}")
    if folder_counts:
        _log(f"  Folders:")
        for folder, count in sorted(folder_counts.items(), key=lambda x: -x[1]):
            _log(f"    {Path(folder).name}: {count:,} files")
    if mp3br:
        _log("  MP3 Bitrates:")
        for br in sorted(mp3br): _log(f"    {br} kbps : {mp3br[br]:,}")
    _emit("stats", total=total, artists=len(arts), albums=len(albs),
          size=_fmt_size(sz), ext_counts={k: v for k, v in ext_c.items()},
          folder_counts={Path(k).name: v for k, v in folder_counts.items()})
    _done(f"Analysis — {total:,} files, {len(arts):,} artists")

def _op_organize(folder, settings):
    _log("📁 Organizing files…")
    files = _get_files(folder, settings); total = len(files)
    _progress(0, total or 1, "Organizing…"); proc = err = 0
    for i, f in enumerate(files, 1):
        t = _read_tags(f)
        if not t: err += 1; _log(f"  ✗ No tags: {f.name}", "error"); _progress(i, total); continue
        dest_dir, dest = _build_dest(folder, t, f, settings)
        if f != dest:
            try:
                if settings.get("backup_before_move"): shutil.copy2(f, str(f)+".bak")
                dest_dir.mkdir(parents=True, exist_ok=True); f.rename(dest); proc += 1
            except Exception as e: err += 1; _log(f"  ✗ {f.name}: {e}", "error")
        _progress(i, total)
    _log(f"✓ Organized {proc} files — {err} error(s)", "success"); _done(f"Organized {proc} files")
    if settings.get("auto_playlist"): _op_playlists(folder, settings)

def _op_various(folder, settings):
    _log("👥 Handling Various Artists…")
    va = [f for f in _get_files(folder, settings) if "various artists" in str(f).lower()]
    if not va: _log("  No VA tracks found.", "warning"); _done("Nothing to do"); return
    _progress(0, len(va), "Re-homing…"); moved = 0
    for i, f in enumerate(va, 1):
        t = _read_tags(f)
        if t:
            dest_dir, dest = _build_dest(folder, t, f, settings)
            try: dest_dir.mkdir(parents=True, exist_ok=True); f.rename(dest); moved += 1
            except Exception as e: _log(f"  ✗ {f.name}: {e}", "error")
        _progress(i, len(va))
    _log(f"✓ Moved {moved} VA tracks", "success"); _done(f"Moved {moved}")

def _op_dupes(folder, settings):
    _log("🗑️  Scanning duplicates…")
    files = _get_files(folder, settings); total = len(files)
    _progress(0, total or 1, "Scanning…"); sd = defaultdict(list)
    for i, f in enumerate(files, 1):
        t = _read_tags(f)
        if t: sd[(_main_artist(t).lower(), t["title"].lower(), t["album"].lower())].append(
            {"path": f, "size": f.stat().st_size, "deluxe": "deluxe" in str(f).lower(), "ext": f.suffix.lower()})
        _progress(i, total)
    pri = settings.get("dup_priority", "deluxe")
    def _k(x):
        if pri=="deluxe": return (not x["deluxe"], x["ext"]!=".flac", -x["size"])
        elif pri=="flac": return (x["ext"]!=".flac", not x["deluxe"], -x["size"])
        else:             return (-x["size"], not x["deluxe"], x["ext"]!=".flac")
    to_del = []
    for _, fs in sd.items():
        if len(fs) > 1: fs.sort(key=_k); to_del.extend(x["path"] for x in fs[1:])
    if not to_del: _log("✓ No duplicates found!", "success"); _done("No duplicates"); return
    _progress(0, len(to_del), f"Deleting {len(to_del)}…"); deleted = 0
    for i, fp in enumerate(to_del, 1):
        try: fp.unlink(); deleted += 1
        except Exception as e: _log(f"  ✗ {fp.name}: {e}", "error")
        _progress(i, len(to_del))
    _log(f"✓ Deleted {deleted} duplicates", "success"); _done(f"Removed {deleted}")

def _op_covers(folder, settings, force=False):
    fmt = settings.get("cover_format", "png")
    _log(f"🖼️  {'Rebuilding' if force else 'Generating'} covers ({fmt.upper()})…")
    dirs = list(_album_folders(folder, settings)); exts = settings.get("extensions", [".flac", ".mp3"])
    _progress(0, len(dirs) or 1); gen = 0
    for i, d in enumerate(dirs, 1):
        cov = d / f"cover.{fmt}"
        if cov.exists() and not force: _progress(i, len(dirs)); continue
        for ext in exts:
            for af in d.glob(f"*{ext}"):
                if _extract_cover(af, cov): gen += 1; break
            else: continue
            break
        _progress(i, len(dirs))
    _log(f"✓ {'Rebuilt' if force else 'Generated'} {gen} covers", "success"); _done(f"{gen} covers")

def _op_playlists(folder, settings):
    _log("📝 Generating playlists…"); dirs = list(_album_folders(folder, settings))
    exts = settings.get("extensions", [".flac", ".mp3"]); gen = 0
    _progress(0, len(dirs) or 1)
    for i, d in enumerate(dirs, 1):
        if list(d.glob("*.m3u")): _progress(i, len(dirs)); continue
        tracks = []
        for ext in exts:
            for f in d.glob(f"*{ext}"):
                t = _read_tags(f)
                if t:
                    try: n = int(t["tracknumber"])
                    except: n = 0
                    tracks.append((n, f, t))
        if not tracks: _progress(i, len(dirs)); continue
        tracks.sort(key=lambda x: x[0]); ft = tracks[0][2]
        m3u = d / f"{_clean(ft['artist'])} - {_clean(ft['album'])}.m3u"
        try:
            with open(m3u, "w", encoding="utf-8") as mf:
                mf.write("#EXTM3U\n")
                for _, f, t in tracks:
                    mf.write(f"#EXTINF:{_duration(f)},{t['artist']} - {t['title']} [{t['bitrate']}]\n{f.name}\n")
            gen += 1
        except Exception as e: _log(f"  ✗ {m3u.name}: {e}", "error")
        _progress(i, len(dirs))
    _log(f"✓ Generated {gen} playlists", "success"); _done(f"{gen} playlists")

def _op_clean_dup_fold(folder, settings):
    _log("🧹 Cleaning duplicate folders…")
    adirs = [d for d in Path(folder).iterdir() if d.is_dir() and not d.name.startswith((".","-"))]
    exts = settings.get("extensions", [".flac", ".mp3"]); cleaned = 0
    _progress(0, len(adirs) or 1)
    for i, ad in enumerate(adirs, 1):
        groups = defaultdict(list)
        for sub in ad.iterdir():
            if not sub.is_dir(): continue
            m = re.search(r"\((\d{4})\)$", sub.name)
            if m: groups[sub.name.replace(f" ({m.group(1)})", "").strip()].append(("y", sub))
            else: groups[sub.name].append(("n", sub))
        for _, fs in groups.items():
            wy = [f for t,f in fs if t=="y"]; ny = [f for t,f in fs if t=="n"]
            if wy and ny:
                for fp in ny:
                    if not any(bool(list(fp.glob(f"*{e}"))[:1]) for e in exts):
                        try: shutil.rmtree(fp); cleaned += 1
                        except Exception as e: _log(f"  ✗ {fp.name}: {e}", "error")
        _progress(i, len(adirs))
    _log(f"✓ Cleaned {cleaned} duplicate folders", "success"); _done(f"Cleaned {cleaned}")

def _op_clean_empty(folder, settings):
    _log("🗂️  Removing empty folders…")
    dirs = sorted(Path(folder).rglob("*"), reverse=True); cleaned = 0
    _progress(0, len(dirs) or 1)
    for i, d in enumerate(dirs, 1):
        if d.is_dir() and not any(d.iterdir()):
            try: d.rmdir(); cleaned += 1
            except: pass
        _progress(i, len(dirs) or 1)
    _log(f"✓ Removed {cleaned} empty folders", "success"); _done(f"{cleaned} empty folders")

def _op_missing_tags(folder, settings):
    _log("🔍 Scanning for missing tags…")
    files = _get_files(folder, settings); total = len(files)
    _progress(0, total or 1); missing = []
    for i, f in enumerate(files, 1):
        t = _read_tags(f)
        if not t: missing.append((f.name, "unreadable"))
        else:
            issues = [k for k in ("artist","album","title") if not t.get(k) or "unknown" in t[k].lower()]
            if issues: missing.append((f.name, ", ".join(issues)))
        _progress(i, total or 1)
    if missing:
        _log(f"⚠  {len(missing)} files with tag issues:", "warning")
        for name, reason in missing[:80]: _log(f"  {name}  [{reason}]", "warning")
        if len(missing)>80: _log(f"  … and {len(missing)-80} more.")
    else: _log("✓ All files have complete tags!", "success")
    _done(f"{len(missing)} tag issues")

def _op_corrupt(folder, settings):
    _log("💔 Scanning for corrupt files…")
    files = _get_files(folder, settings); total = len(files)
    _progress(0, total or 1); corrupt = []
    for i, f in enumerate(files, 1):
        try:
            s = f.suffix.lower()
            if s == ".flac": FLAC(f)
            elif s == ".mp3": MP3(f)
        except Exception as e: corrupt.append((f.name, str(e)))
        _progress(i, total or 1)
    if corrupt:
        _log(f"⚠  {len(corrupt)} corrupt files:", "error")
        for name, err in corrupt: _log(f"  {name}: {err}", "error")
    else: _log("✓ No corrupt files!", "success")
    _done(f"{len(corrupt)} corrupt files")

def _op_report(folders, settings, output):
    _log("📈 Building library report…")
    files = _get_all_files(settings); total = len(files)
    _progress(0, total or 1)
    ext_c=defaultdict(int); sz=0; arts=set(); albs=set(); mp3br=defaultdict(int)
    for i, f in enumerate(files, 1):
        s=f.suffix.lower(); ext_c[s]+=1; sz+=f.stat().st_size
        if s==".mp3":
            try: mp3br[MP3(f).info.bitrate//1000]+=1
            except: pass
        t=_read_tags(f)
        if t: a=_main_artist(t); arts.add(a); albs.add(f"{a}/{t['album']}")
        _progress(i, total or 1)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"Songanizer Pro — Library Report", f"Generated : {now}",
             f"Library   : {', '.join(folders)}", "="*62,
             f"Total Files   : {total:,}", f"Artists       : {len(arts):,}",
             f"Albums        : {len(albs):,}", f"Library Size  : {_fmt_size(sz)}", "", "Formats:"]
    for ext, cnt in sorted(ext_c.items()): lines.append(f"  {ext.upper():7}: {cnt:,}")
    if mp3br: lines+=["","MP3 Bitrates:"]+[f"  {br} kbps : {mp3br[br]:,}" for br in sorted(mp3br)]
    lines+=["","Artists:"]+[f"  {a}" for a in sorted(arts)]
    Path(output).write_text("\n".join(lines), "utf-8")
    _log(f"✓ Report saved: {output}", "success"); _done("Report exported")

def _op_get_genres(settings):
    """Return all unique genre tags found in all loaded libraries."""
    files = _get_all_files(settings)
    genres = set()
    for f in files:
        t = _read_tags(f)
        if t and t.get("genre"):
            for g in re.split(r"[;,/|]", t["genre"]):
                g = g.strip()
                if g: genres.add(g)
    return sorted(genres, key=str.lower)

def _op_get_artists(settings):
    """Return all unique artists found in all loaded libraries."""
    files = _get_all_files(settings)
    artists = set()
    for f in files:
        t = _read_tags(f)
        if t:
            artists.add(_main_artist(t))
    return sorted(artists, key=str.lower)

def _op_remove_genres(folder, settings, genres_to_remove, protected_artists, protected_albums, protected_songs):
    """Delete all files matching the given genres, unless protected."""
    if not genres_to_remove: _log("  No genres specified.", "warning"); _done("Nothing to do"); return
    genres_lower = {g.lower() for g in genres_to_remove}
    pa = {a.lower() for a in protected_artists}
    pb = {a.lower() for a in protected_albums}
    ps = {a.lower() for a in protected_songs}
    files = _get_files(folder, settings); total = len(files)
    _progress(0, total or 1, "Scanning genres…"); to_del = []
    for i, f in enumerate(files, 1):
        t = _read_tags(f)
        if t:
            file_genres = {g.strip().lower() for g in re.split(r"[;,/|]", t.get("genre","")) if g.strip()}
            if file_genres & genres_lower:
                # check blacklist
                if t["artist"].lower() in pa or t.get("albumartist","").lower() in pa: _progress(i,total); continue
                if t["album"].lower() in pb: _progress(i,total); continue
                if t["title"].lower() in ps: _progress(i,total); continue
                to_del.append(f)
        _progress(i, total)
    _log(f"  Found {len(to_del)} files matching genres to remove.", "warning")
    _emit("genre_preview", count=len(to_del), files=[str(f) for f in to_del[:30]])
    if not to_del: _done("No matching files"); return


_genre_candidates: list = []

def _op_confirm_remove_genres(files_to_delete: list):
    """Actually delete the confirmed genre removal candidates."""
    deleted = 0
    _progress(0, len(files_to_delete) or 1, "Removing…")
    for i, fp in enumerate(files_to_delete, 1):
        try: Path(fp).unlink(); deleted += 1
        except Exception as e: _log(f"  ✗ {Path(fp).name}: {e}", "error")
        _progress(i, len(files_to_delete))
    _log(f"✓ Removed {deleted} files by genre", "success"); _done(f"Removed {deleted} files")


# ════════════════════════════════════════════════════════════════
#  CROSS-FOLDER DUPLICATE CHECKING
# ════════════════════════════════════════════════════════════════
def _op_find_cross_duplicates(settings, check_type="all"):
    """
    Find duplicates across all loaded folders.
    check_type: 'filename', 'tags', 'metadata', or 'all'
    """
    _log(f"🔍 Scanning for cross-folder duplicates ({check_type})…")
    files = _get_all_files(settings)
    total = len(files)
    _progress(0, total or 1, "Scanning…")
    
    duplicates = defaultdict(list)
    
    for i, f in enumerate(files, 1):
        t = _read_tags(f) if check_type in ("tags", "metadata", "all") else None
        folder_name = ""
        for folder in settings.get("folders", []):
            if str(f).startswith(str(Path(folder))):
                folder_name = Path(folder).name
                break
        
        if check_type == "filename":
            key = f.name.lower()
        elif check_type == "tags":
            key = (t["artist"].lower(), t["title"].lower()) if t else f.name.lower()
        elif check_type == "metadata":
            key = (t["artist"].lower(), t["album"].lower(), t["title"].lower()) if t else f.name.lower()
        else:  # all
            key = (t["artist"].lower(), t["title"].lower(), t["album"].lower()) if t else f.name.lower()
        
        duplicates[key].append({
            "path": str(f),
            "name": f.name,
            "folder": folder_name,
            "size": f.stat().st_size,
            "ext": f.suffix.lower()
        })
        _progress(i, total)
    
    # Filter to only actual duplicates
    dup_list = []
    for key, items in duplicates.items():
        if len(items) > 1:
            dup_list.append({
                "key": key,
                "items": items,
                "count": len(items)
            })
    
    _emit("cross_duplicates", duplicates=dup_list, check_type=check_type)
    _log(f"✓ Found {len(dup_list)} duplicate groups", "success")
    _done(f"Found {len(dup_list)} duplicate groups")


def _op_move_duplicates(moves_list):
    """
    Move selected files from one folder to another.
    moves_list: [{"from": "/path/to/file.mp3", "to": "/destination/folder/"}]
    """
    _log("📦 Moving selected files…")
    total = len(moves_list)
    _progress(0, total or 1, "Moving…")
    moved = 0
    errors = 0
    
    for i, move in enumerate(moves_list, 1):
        try:
            src = Path(move["from"])
            dest_dir = Path(move["to"])
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / src.name
            
            # Handle name collision
            if dest.exists():
                stem = dest.stem
                ext = dest.suffix
                counter = 1
                while dest.exists():
                    dest = dest_dir / f"{stem}_{counter}{ext}"
                    counter += 1
            
            shutil.move(str(src), str(dest))
            moved += 1
            _log(f"  ✓ Moved: {src.name}")
        except Exception as e:
            errors += 1
            _log(f"  ✗ Error moving {Path(move['from']).name}: {e}", "error")
        
        _progress(i, total)
    
    _log(f"✓ Moved {moved} files, {errors} errors", "success" if errors == 0 else "warning")
    _done(f"Moved {moved} files")


# ════════════════════════════════════════════════════════════════
#  AI DISCOVERY
# ════════════════════════════════════════════════════════════════
def _call_openai(key, prompt):
    data = json.dumps({"model":"gpt-4o","messages":[{"role":"user","content":prompt}],"max_tokens":1200}).encode()
    req  = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=data,
                                   headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read())["choices"][0]["message"]["content"]

def _call_gemini(key, prompt):
    url  = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
    data = json.dumps({"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"maxOutputTokens":1200}}).encode()
    req  = urllib.request.Request(url, data=data, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read())["candidates"][0]["content"]["parts"][0]["text"]

def _call_claude(key, prompt):
    data = json.dumps({"model":"claude-3-haiku-20240307","max_tokens":1200,
                       "messages":[{"role":"user","content":prompt}]}).encode()
    req  = urllib.request.Request("https://api.anthropic.com/v1/messages", data=data,
                                   headers={"x-api-key":key,"anthropic-version":"2023-06-01","Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read())["content"][0]["text"]

def _discover(settings, extra=None):
    providers = settings.get("ai_providers", ["openai"])
    key_map  = {"openai":"openai_key","gemini":"gemini_key","claude":"claude_key"}
    
    # Get filters from extra (frontend) or settings
    filters = extra.get("filters", {}) if extra else {}
    
    # Priority: use filters from frontend, fall back to settings
    genre_filter = set(g.lower() for g in filters.get("genres", []))
    artist_filter = set(a.lower() for a in filters.get("artists", []))
    
    # If no filters from frontend, use settings
    if not genre_filter:
        genre_filter = set(g.lower() for g in settings.get("ai_genre_filter", []))
    if not artist_filter:
        artist_filter = set(a.lower() for a in settings.get("ai_artist_filter", []))
    
    _log(f"Using filters - genres: {len(genre_filter)}, artists: {len(artist_filter)}", "info")
    
    files = _get_all_files(settings); artists = set()
    _progress(0, len(files) or 1, "Scanning library for artists…")
    
    for i, f in enumerate(files, 1):
        t = _read_tags(f)
        if t:
            # Apply genre filter
            if genre_filter:
                file_genres = {g.strip().lower() for g in re.split(r"[;,/|]", t.get("genre","")) if g.strip()}
                if not (file_genres & genre_filter):
                    continue
            
            artist_name = _main_artist(t)
            
            # Apply artist filter
            if artist_filter and artist_name.lower() not in artist_filter:
                continue
                
            artists.add(artist_name)
        _progress(i, len(files) or 1)
    
    # Get available providers with keys
    available_providers = []
    for provider in providers:
        key = settings.get(key_map.get(provider, ""), "")
        if key:
            available_providers.append((provider, key))
    
    if not available_providers:
        _log("⚠  No API keys set for selected AI providers", "warning"); _done("Set API keys in Settings"); return
    
    # Use first available provider
    provider, key = available_providers[0]
    
    # Limit to 10 artists to avoid overloading AI
    sample = sorted(artists)[:10]
    if not sample:
        _log("⚠  No artists found matching your filters", "warning"); _done("No matching artists"); return
    
    _log(f"  Processing {len(sample)} artists: {', '.join(sample[:3])}{'...' if len(sample) > 3 else ''}", "info")
    
    prompt = (
        "I have the following artists in my music library:\n" +
        "\n".join(f"- {a}" for a in sample) +
        "\n\nBased on my taste, suggest exactly 15 artists or albums I might love that are NOT "
        "already in this list. For each suggestion, give: artist name and a one-sentence reason.\n"
        "Format each entry as:  ARTIST: Reason"
    )
    _log(f"  Sending {len(sample)} artists to {provider}…", "info")
    try:
        if provider=="openai":   text = _call_openai(key, prompt)
        elif provider=="gemini": text = _call_gemini(key, prompt)
        elif provider=="claude": text = _call_claude(key, prompt)
        else: text = _call_openai(key, prompt)
    except Exception as e:
        _log(f"  ✗ AI request failed: {e}", "error"); _done("Discovery error"); return

    suggestions = []
    for line in text.strip().split("\n"):
        m = re.match(r"^[\-\*\d\.\s]*([^:]+):\s*(.+)", line.strip())
        if m:
            name    = m.group(1).strip()
            reason  = m.group(2).strip()
            tidal   = "https://tidal.squid.wtf/search?q=" + urllib.parse.quote_plus(name)
            qobuz   = "https://qobuz.squid.wtf/search?q=" + urllib.parse.quote_plus(name)
            mono    = "https://monochrome.samidy.com/search?q=" + urllib.parse.quote_plus(name)
            suggestions.append({"artist":name,"reason":reason,"tidal":tidal,"qobuz":qobuz,"mono":mono})

    _emit("discover_results", suggestions=suggestions, provider=provider)
    _log(f"✓ {len(suggestions)} music suggestions generated!", "success")
    _done(f"Discovery complete — {len(suggestions)} suggestions")


# ════════════════════════════════════════════════════════════════
#  PLEX INTEGRATION
# ════════════════════════════════════════════════════════════════
def _plex_connect(settings):
    """Connect to Plex server."""
    try:
        from plexapi.server import PlexServer
        plex_url = settings.get("plex_url", "http://127.0.0.1:32400")
        plex_token = settings.get("plex_token", "")
        if not plex_token:
            return None, "No Plex token configured"
        return PlexServer(plex_url, plex_token, timeout=60), None
    except ImportError:
        return None, "plexapi not installed. Run: pip install plexapi"
    except Exception as e:
        return None, str(e)

def _op_plex_rate_all(settings, target_rating=10.0):
    """Rate all tracks in Plex music library."""
    _log("🎬 Connecting to Plex…")
    plex, error = _plex_connect(settings)
    if error:
        _log(f"✗ Plex connection failed: {error}", "error")
        _done("Plex error")
        return
    
    try:
        music_section = settings.get("plex_music_section", "Music")
        music_lib = plex.library.section(music_section)
    except Exception as e:
        _log(f"✗ Music section '{music_section}' not found: {e}", "error")
        _done("Plex error")
        return
    
    _log(f"📊 Scanning Plex library: {music_section}…")
    
    # Get all artists
    artists = music_lib.searchArtists()
    total_artists = len(artists)
    
    if total_artists == 0:
        _log("⚠ No artists found in Plex library", "warning")
        _done("No artists found")
        return
    
    _progress(0, total_artists, "Processing artists…")
    
    total_albums = 0
    total_tracks = 0
    
    for i, artist in enumerate(artists, 1):
        try:
            albums = artist.albums()
            for album in albums:
                total_albums += 1
                # Rate album
                try:
                    album.editField('userRating', target_rating)
                except:
                    pass
                
                # Rate tracks
                for track in album.tracks():
                    total_tracks += 1
                    try:
                        track.editField('userRating', target_rating)
                    except Exception as e:
                        pass
        except Exception as e:
            _log(f"  ⚠ Error processing {artist.title}: {e}", "warning")
        
        _progress(i, total_artists)
    
    _log(f"✓ Plex rating update complete!", "success")
    _log(f"   Processed {total_artists} artists, {total_albums} albums, {total_tracks} tracks", "success")
    _done(f"Rated {total_tracks} tracks in Plex")

def _op_plex_search_and_rate(settings, artist_query, target_rating=10.0):
    """Search for artist in Plex and rate their tracks."""
    _log(f"🔍 Searching Plex for: {artist_query}…")
    
    plex, error = _plex_connect(settings)
    if error:
        _log(f"✗ Plex connection failed: {error}", "error")
        _done("Plex error")
        return
    
    try:
        music_section = settings.get("plex_music_section", "Music")
        music_lib = plex.library.section(music_section)
    except Exception as e:
        _log(f"✗ Music section '{music_section}' not found: {e}", "error")
        _done("Plex error")
        return
    
    artists = music_lib.searchArtists(title=artist_query)
    
    if not artists:
        _log(f"⚠ No artists found matching '{artist_query}'", "warning")
        _done("No matches")
        return
    
    _log(f"Found {len(artists)} matching artists:", "info")
    for i, artist in enumerate(artists, 1):
        album_count = len(artist.albums())
        track_count = sum(len(album.tracks()) for album in artist.albums())
        _log(f"  {i}. {artist.title} (albums: {album_count}, tracks: ~{track_count})")
    
    # Only emit results if not rating (if target_rating is provided, we rate)
    if target_rating is None or target_rating == 0:
        _emit("plex_search_results", artists=[{"title": a.title, "albums": len(a.albums())} for a in artists])
        _done(f"Found {len(artists)} artists")
        return
    
    # Rate first match
    artist = artists[0]
    _log(f"🎬 Rating all tracks by {artist.title} to {target_rating}…")
    
    total_albums = 0
    total_tracks = 0
    
    for album in artist.albums():
        total_albums += 1
        try:
            album.editField('userRating', target_rating)
        except:
            pass
        
        for track in album.tracks():
            total_tracks += 1
            try:
                track.editField('userRating', target_rating)
            except:
                pass
    
    _log(f"✓ Rated {total_tracks} tracks by {artist.title}", "success")
    _done(f"Rated {total_tracks} tracks")


def _op_plex_dedup(settings):
    """Find and remove duplicate tracks in Plex library."""
    _log("🔍 Scanning Plex library for duplicates…")
    
    plex, error = _plex_connect(settings)
    if error:
        _log(f"✗ Plex connection failed: {error}", "error")
        _done("Plex error")
        return
    
    try:
        music_section = settings.get("plex_music_section", "Music")
        music_lib = plex.library.section(music_section)
    except Exception as e:
        _log(f"✗ Music section '{music_section}' not found: {e}", "error")
        _done("Plex error")
        return
    
    # Get all tracks and find duplicates by title + artist
    all_tracks = []
    track_map = defaultdict(list)
    
    total_artists = len(music_lib.searchArtists())
    _progress(0, total_artists or 1, "Scanning artists…")
    
    artists = music_lib.searchArtists()
    for i, artist in enumerate(artists, 1):
        for album in artist.albums():
            for track in album.tracks():
                # Create a key from title and artist
                key = (track.title.lower() if track.title else "", 
                       artist.title.lower() if artist.title else "")
                track_map[key].append({
                    "title": track.title,
                    "artist": artist.title,
                    "album": album.title,
                    "ratingKey": track.ratingKey,
                    "addedAt": track.addedAt if hasattr(track, 'addedAt') else None
                })
                all_tracks.append(track)
        _progress(i, total_artists)
    
    # Find duplicates
    duplicates = []
    for key, tracks in track_map.items():
        if len(tracks) > 1:
            # Sort by addedAt to keep the oldest
            tracks.sort(key=lambda x: x.get('addedAt') or datetime.datetime.min)
            duplicates.append({
                "title": tracks[0]["title"],
                "artist": tracks[0]["artist"],
                "count": len(tracks),
                "tracks": tracks
            })
    
    _log(f"✓ Found {len(duplicates)} duplicate groups", "success")
    _emit("plex_duplicates", duplicates=duplicates)
    _done(f"Found {len(duplicates)} duplicate groups")


def _op_plex_stats(settings):
    """Get Plex library statistics."""
    _log("📊 Getting Plex library statistics…")
    
    plex, error = _plex_connect(settings)
    if error:
        _log(f"✗ Plex connection failed: {error}", "error")
        _done("Plex error")
        return
    
    try:
        music_section = settings.get("plex_music_section", "Music")
        music_lib = plex.library.section(music_section)
    except Exception as e:
        _log(f"✗ Music section '{music_section}' not found: {e}", "error")
        _done("Plex error")
        return
    
    artists = music_lib.searchArtists()
    total_albums = 0
    total_tracks = 0
    
    for artist in artists:
        albums = artist.albums()
        total_albums += len(albums)
        for album in albums:
            total_tracks += len(album.tracks())
    
    _log(f"📊 Plex Library Stats:")
    _log(f"   Artists:  {len(artists)}")
    _log(f"   Albums:   {total_albums}")
    _log(f"   Tracks:   {total_tracks}")
    _done(f"Library: {len(artists)} artists, {total_albums} albums, {total_tracks} tracks")


# ════════════════════════════════════════════════════════════════
#  WINDOWS STARTUP SERVICE
# ════════════════════════════════════════════════════════════════
_REG_PATH = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
_SVC_NAME = "Songanizer"

def _startup_install():
    try:
        import winreg
        cmd = f'"{sys.executable}" "{os.path.abspath(__file__)}"'
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, _SVC_NAME, 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(key)
        return True, "Startup entry created. App will auto-launch on login."
    except ImportError:
        return False, "winreg not available (non-Windows system)."
    except Exception as e:
        return False, str(e)

def _startup_remove():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, _SVC_NAME)
        winreg.CloseKey(key); return True, "Startup entry removed."
    except ImportError: return False, "winreg not available."
    except Exception as e: return False, str(e)

def _startup_status():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, _SVC_NAME); winreg.CloseKey(key); return True
    except Exception: return False


def _dispatch(op_id, settings, extra=None):
    global _processing
    with _lock:
        if _processing: _log("⚠  Another operation is already running.", "warning"); return
        _processing = True
    def _t():
        global _processing
        try:
            ops = {
                "analyze":        lambda: _op_analyze(settings),
                "organize":       lambda: _op_organize(settings.get("folders", [None])[0] or "", settings),
                "various":        lambda: _op_various(settings.get("folders", [None])[0] or "", settings),
                "duplicates":     lambda: _op_dupes(settings.get("folders", [None])[0] or "", settings),
                "covers":         lambda: _op_covers(settings.get("folders", [None])[0] or "", settings, False),
                "rebuild_covers": lambda: _op_covers(settings.get("folders", [None])[0] or "", settings, True),
                "playlists":      lambda: _op_playlists(settings.get("folders", [None])[0] or "", settings),
                "clean_dup_fold": lambda: _op_clean_dup_fold(settings.get("folders", [None])[0] or "", settings),
                "clean_empty":    lambda: _op_clean_empty(settings.get("folders", [None])[0] or "", settings),
                "missing_tags":   lambda: _op_missing_tags(settings.get("folders", [None])[0] or "", settings),
                "corrupt":        lambda: _op_corrupt(settings.get("folders", [None])[0] or "", settings),
                "discover":       lambda: _discover(settings, extra),
                "cross_dupes":    lambda: _op_find_cross_duplicates(settings, extra.get("check_type", "all") if extra else "all"),
                "plex_rate_all":  lambda: _op_plex_rate_all(settings, settings.get("plex_target_rating", 10.0)),
                "plex_search":    lambda: _op_plex_search_and_rate(settings, extra.get("query", "") if extra else "", settings.get("plex_target_rating", 10.0)),
                "plex_dedup":     lambda: _op_plex_dedup(settings),
                "plex_stats":     lambda: _op_plex_stats(settings),
            }
            fn = ops.get(op_id)
            if fn: fn()
            else: _log(f"Unknown op: {op_id}", "error"); _done("Error")
        except Exception as e: _log(f"✗ Error: {e}", "error"); _done("Error")
        finally: _processing = False
    threading.Thread(target=_t, daemon=True).start()


# ════════════════════════════════════════════════════════════════
#  FLASK ROUTES
# ════════════════════════════════════════════════════════════════
@app.route("/")
def index(): return HTML, 200, {"Content-Type":"text/html;charset=utf-8"}

@app.route("/api/events")
def events():
    def _gen():
        yield 'data: {"type":"connected"}\n\n'
        while True:
            try: yield f"data: {json.dumps(_events.get(timeout=25))}\n\n"
            except queue.Empty: yield 'data: {"type":"ping"}\n\n'
    return Response(stream_with_context(_gen()), mimetype="text/event-stream",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@app.route("/api/settings", methods=["GET"])
def get_settings(): return jsonify(_load())

@app.route("/api/settings", methods=["POST"])
def post_settings():
    cur = _load(); cur.update(request.get_json(force=True, silent=True) or {}); _save(cur)
    return jsonify({"ok":True})

@app.route("/api/settings/export", methods=["GET"])
def export_settings():
    """Export settings as downloadable JSON file"""
    s = _load()
    # Don't export sensitive data
    export_data = {
        "folders": s.get("folders", []),
        "extensions": s.get("extensions", []),
        "excluded_folders": s.get("excluded_folders", []),
        "folder_pattern": s.get("folder_pattern", ""),
        "naming_pattern": s.get("naming_pattern", ""),
        "backup_before_move": s.get("backup_before_move", False),
        "auto_playlist": s.get("auto_playlist", False),
        "log_to_file": s.get("log_to_file", False),
        "dup_priority": s.get("dup_priority", "deluxe"),
        "cover_format": s.get("cover_format", "png"),
        "accent1": s.get("accent1", "#7c3aed"),
        "accent2": s.get("accent2", "#06b6d4"),
        "glow_opacity": s.get("glow_opacity", 0.18),
        "ai_providers": s.get("ai_providers", ["openai"]),
        "genres_to_remove": s.get("genres_to_remove", []),
        "protected_artists": s.get("protected_artists", []),
        "protected_albums": s.get("protected_albums", []),
        "protected_songs": s.get("protected_songs", []),
        "ai_genre_filter": s.get("ai_genre_filter", []),
        "ai_artist_filter": s.get("ai_artist_filter", []),
        "plex_url": s.get("plex_url", "http://127.0.0.1:32400"),
        "plex_music_section": s.get("plex_music_section", "Music"),
        "plex_target_rating": s.get("plex_target_rating", 10.0),
    }
    return Response(
        json.dumps(export_data, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment;filename=songanizer_settings.json"}
    )

@app.route("/api/settings/import", methods=["POST"])
def import_settings():
    """Import settings from JSON file"""
    try:
        data = request.get_json(force=True, silent=True) or {}
        cur = _load()
        # Merge imported settings (but keep sensitive data like tokens/keys)
        for key in ["folders", "extensions", "excluded_folders", "folder_pattern", 
                    "naming_pattern", "backup_before_move", "auto_playlist", 
                    "log_to_file", "dup_priority", "cover_format", "accent1", 
                    "accent2", "glow_opacity", "ai_providers", "genres_to_remove",
                    "protected_artists", "protected_albums", "protected_songs",
                    "ai_genre_filter", "ai_artist_filter", "plex_url", 
                    "plex_music_section", "plex_target_rating"]:
            if key in data:
                cur[key] = data[key]
        _save(cur)
        return jsonify({"ok": True, "message": "Settings imported successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/folders", methods=["GET"])
def get_folders():
    s = _load()
    return jsonify({"folders": s.get("folders", [])})

@app.route("/api/folders", methods=["POST"])
def add_folder():
    data = request.get_json(force=True, silent=True) or {}
    folder = data.get("folder", "").strip()
    if not folder:
        return jsonify({"error": "No folder path"}), 400
    if not Path(folder).exists():
        return jsonify({"error": "Folder does not exist"}), 400
    
    s = _load()
    folders = s.get("folders", [])
    if folder not in folders:
        folders.append(folder)
        s["folders"] = folders
        _save(s)
    
    return jsonify({"ok": True, "folders": folders})

@app.route("/api/folders/<int:index>", methods=["DELETE"])
def remove_folder(index):
    s = _load()
    folders = s.get("folders", [])
    if 0 <= index < len(folders):
        folders.pop(index)
        s["folders"] = folders
        _save(s)
    return jsonify({"ok": True, "folders": folders})

@app.route("/api/files/export", methods=["GET"])
def export_file_list():
    """Export list of all files in loaded folders for fast loading"""
    s = _load()
    folders = s.get("folders", [])
    if not folders:
        return jsonify({"error": "No folders loaded"}), 400
    
    all_files = []
    for folder in folders:
        folder_path = Path(folder)
        if folder_path.exists():
            for ext in s.get("extensions", [".flac", ".mp3"]):
                for f in folder_path.rglob(f"*{ext}"):
                    all_files.append({
                        "path": str(f),
                        "name": f.name,
                        "size": f.stat().st_size,
                        "folder": folder
                    })
    
    return Response(
        json.dumps({"folders": folders, "files": all_files, "count": len(all_files)}, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment;filename=songanizer_filelist.json"}
    )

@app.route("/api/files/import", methods=["POST"])
def import_file_list():
    """Import file list and optionally add folders"""
    try:
        data = request.get_json(force=True, silent=True) or {}
        folders = data.get("folders", [])
        files = data.get("files", [])
        
        s = _load()
        current_folders = s.get("folders", [])
        
        # Add any new folders
        for folder in folders:
            if folder not in current_folders and Path(folder).exists():
                current_folders.append(folder)
        
        s["folders"] = current_folders
        _save(s)
        
        return jsonify({
            "ok": True, 
            "folders": current_folders, 
            "fileCount": len(files),
            "message": f"Added {len(folders)} folders with {len(files)} files"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/list-dir", methods=["POST"])
def list_dir():
    data = request.get_json(force=True, silent=True) or {}
    path = data.get("path","").strip()
    try:
        if not path:
            if sys.platform == "win32":
                drives = [f"{chr(d)}:\\" for d in range(65, 91) if Path(f"{chr(d)}:\\").exists()]
                return jsonify({"path":"", "dirs":drives, "parent":"", "is_root":True})
            else:
                items = sorted([str(p) for p in Path("/").iterdir() if p.is_dir()], key=str.lower)
                return jsonify({"path":"/","dirs":items,"parent":"","is_root":True})
        p = Path(path)
        if not p.exists() or not p.is_dir():
            return jsonify({"error":"Path not found"}), 400
        dirs   = sorted([str(d) for d in p.iterdir() if d.is_dir()], key=lambda x: x.lower())
        parent = "" if p.parent == p else str(p.parent)
        return jsonify({"path":str(p), "dirs":dirs, "parent":parent, "is_root":False})
    except PermissionError:
        parent = "" if not path else str(Path(path).parent)
        return jsonify({"path":path,"dirs":[],"parent":parent,"is_root":False,"error":"Permission denied"})
    except Exception as e:
        return jsonify({"error":str(e)}), 400

@app.route("/api/run/<op_id>", methods=["POST"])
def run_op(op_id):
    data     = request.get_json(force=True, silent=True) or {}
    settings = _load(); settings.update(data.get("settings",{}))
    folders  = settings.get("folders", [])
    
    if op_id == "report":
        out = data.get("output", str(Path.home() / f"library_report_{datetime.date.today()}.txt"))
        threading.Thread(target=lambda: _op_report(folders, settings, out), daemon=True).start()
        return jsonify({"ok":True})
    
    if op_id == "cross_dupes":
        check_type = data.get("check_type", "all")
        threading.Thread(target=lambda: _dispatch("cross_dupes", settings, {"check_type": check_type}), daemon=True).start()
        return jsonify({"ok":True})
    
    if op_id == "plex_search":
        query = data.get("query", "")
        threading.Thread(target=lambda: _dispatch("plex_search", settings, {"query": query}), daemon=True).start()
        return jsonify({"ok":True})
    
    if op_id == "move_duplicates":
        moves = data.get("moves", [])
        threading.Thread(target=lambda: _op_move_duplicates(moves), daemon=True).start()
        return jsonify({"ok":True})
    
    if not folders:
        return jsonify({"error":"No folders loaded. Add folders first."}), 400
    
    _dispatch(op_id, settings)
    return jsonify({"ok":True})

@app.route("/api/genres", methods=["POST"])
def genres():
    s = _load()
    g = _op_get_genres(s)
    return jsonify({"genres": g})

@app.route("/api/artists", methods=["POST"])
def artists():
    s = _load()
    a = _op_get_artists(s)
    return jsonify({"artists": a})

@app.route("/api/remove-genres", methods=["POST"])
def remove_genres():
    global _genre_candidates
    data    = request.get_json(force=True, silent=True) or {}
    s       = _load(); folders = s.get("folders", [])
    genres  = data.get("genres",[])
    pa      = s.get("protected_artists",[]); pb = s.get("protected_albums",[]); ps = s.get("protected_songs",[])
    if not folders or not genres:
        return jsonify({"error":"No folder or genres"}), 400

    genres_lower = {g.lower() for g in genres}
    pa_l = {a.lower() for a in pa}; pb_l = {a.lower() for a in pb}; ps_l = {a.lower() for a in ps}
    
    candidates = []
    for folder in folders:
        files = _get_files(folder, s)
        for f in files:
            t = _read_tags(f)
            if t:
                fg = {g.strip().lower() for g in re.split(r"[;,/|]", t.get("genre","")) if g.strip()}
                if fg & genres_lower:
                    if t["artist"].lower() in pa_l or t.get("albumartist","").lower() in pa_l: continue
                    if t["album"].lower() in pb_l: continue
                    if t["title"].lower() in ps_l: continue
                    candidates.append(str(f))
    _genre_candidates = candidates
    return jsonify({"count":len(candidates), "files":candidates[:40]})

@app.route("/api/confirm-genre-remove", methods=["POST"])
def confirm_genre_remove():
    global _genre_candidates
    if not _genre_candidates:
        return jsonify({"error":"Nothing staged"}), 400
    files = list(_genre_candidates); _genre_candidates = []
    threading.Thread(target=lambda: _op_confirm_remove_genres(files), daemon=True).start()
    return jsonify({"ok":True})

@app.route("/api/tag-list", methods=["POST"])
def tag_list():
    data = request.get_json(force=True, silent=True) or {}
    s = _load(); folders = s.get("folders", [])
    folder = data.get("folder", folders[0] if folders else "")
    try:
        files = _get_files(Path(folder), s)
        return jsonify({"files": [{"name":f.name,"path":str(f)} for f in sorted(files, key=lambda x:x.name.lower())]})
    except Exception as e: return jsonify({"error":str(e)}), 400

@app.route("/api/tag-read", methods=["POST"])
def tag_read():
    data = request.get_json(force=True, silent=True) or {}
    t = _read_tags(Path(data.get("path","")))
    return jsonify(t or {})

@app.route("/api/tag-save", methods=["POST"])
def tag_save():
    if not _MUT: return jsonify({"error":"mutagen not installed"}), 500
    data = request.get_json(force=True, silent=True) or {}
    path = Path(data.get("path",""))
    try:
        if path.suffix.lower() == ".flac":
            a = FLAC(path)
            for k in ("title","artist","albumartist","album","tracknumber","date","genre"):
                if k in data: a[k] = data[k]
            a.save()
        elif path.suffix.lower() == ".mp3":
            try: a = ID3(path)
            except:
                from mutagen.id3 import ID3NoHeaderError
                a = ID3(); a.save(path); a = ID3(path)
            m = {"title":TIT2,"artist":TPE1,"albumartist":TPE2,"album":TALB,"tracknumber":TRCK,"date":TDRC,"genre":TCON}
            for k, cls in m.items():
                if k in data: a.delall(cls.__name__); a.add(cls(encoding=3, text=data[k]))
            a.save(path)
        return jsonify({"ok":True})
    except Exception as e: return jsonify({"error":str(e)}), 500

@app.route("/api/network-info")
def network_info():
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(("8.8.8.8",80)); ip=s.getsockname()[0]; s.close()
    except: ip="127.0.0.1"
    return jsonify({"ip":ip,"port":5050,"url":f"http://{ip}:5050","startup":_startup_status()})

@app.route("/api/startup-install", methods=["POST"])
def startup_install():
    ok, msg = _startup_install()
    return jsonify({"ok":ok,"message":msg})

@app.route("/api/startup-remove", methods=["POST"])
def startup_remove():
    ok, msg = _startup_remove()
    return jsonify({"ok":ok,"message":msg})


# ════════════════════════════════════════════════════════════════
#  HTML UI
# ════════════════════════════════════════════════════════════════
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Songanizer Pro</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --a1:#7c3aed;--a2:#06b6d4;
  --glow:rgba(124,58,237,.22);--glow2:rgba(6,182,212,.18);
  --bg:#000;--surf:rgba(255,255,255,.038);--surf2:rgba(255,255,255,.07);
  --border:rgba(255,255,255,.09);--border2:rgba(255,255,255,.18);
  --text:#fff;--text2:rgba(255,255,255,.62);--text3:rgba(255,255,255,.35);
  --green:#10b981;--amber:#f59e0b;--red:#ef4444;
  --r:16px;--rs:10px;--rl:22px;--font:'Inter',-apple-system,sans-serif;--tr:.21s cubic-bezier(.4,0,.2,1);
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;background:var(--bg);color:var(--text);font-family:var(--font);overflow:hidden}
::-webkit-scrollbar{width:5px;height:5px}::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:rgba(255,255,255,.12);border-radius:99px}
#ambient{position:fixed;inset:0;pointer-events:none;z-index:0}
.app{position:relative;z-index:1;display:flex;flex-direction:column;height:100vh;overflow:hidden}

/* topbar */
.topbar{display:flex;align-items:center;padding:0 16px;height:56px;background:rgba(0,0,0,.78);
  backdrop-filter:blur(28px);border-bottom:1px solid var(--border);flex-shrink:0;gap:8px;z-index:50}
.logo{display:flex;align-items:center;gap:9px;text-decoration:none;flex-shrink:0}
.logo-icon{width:32px;height:32px;border-radius:9px;background:linear-gradient(135deg,var(--a1),var(--a2));
  display:flex;align-items:center;justify-content:center;font-size:16px;box-shadow:0 0 14px var(--glow)}
.logo-label{font-size:13px;font-weight:700;background:linear-gradient(90deg,#fff,rgba(255,255,255,.65));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.logo-ver{font-size:9px;color:var(--text3);letter-spacing:.3px}
.topbar-mid{flex:1;display:flex;align-items:center;gap:6px;max-width:600px}
.folder-input{flex:1;background:var(--surf);border:1px solid var(--border);border-radius:var(--rs);
  padding:6px 11px;color:var(--text2);font:13px var(--font);outline:none;transition:all var(--tr)}
.folder-input:focus{border-color:var(--a1);color:var(--text)}
.topbar-right{margin-left:auto;display:flex;align-items:center;gap:6px}

/* buttons */
.btn{display:inline-flex;align-items:center;gap:5px;padding:6px 13px;border-radius:var(--rs);
  border:1px solid var(--border);background:var(--surf);color:var(--text);font:500 12px var(--font);
  cursor:pointer;transition:all var(--tr);position:relative;overflow:hidden;white-space:nowrap;user-select:none}
.btn:hover{background:var(--surf2);border-color:var(--border2);transform:translateY(-1px)}
.btn:active{transform:translateY(0)}
.btn-grad{background:linear-gradient(135deg,var(--a1),var(--a2));border-color:transparent;color:#fff;font-weight:600}
.btn-grad:hover{opacity:.88;box-shadow:0 4px 18px var(--glow)}
.btn-sm{padding:5px 11px;font-size:11px}
.btn-icon{width:32px;height:32px;padding:0;border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:15px}
.btn-danger{background:rgba(239,68,68,.18);border-color:rgba(239,68,68,.36);color:#f87171}
.btn-danger:hover{background:rgba(239,68,68,.28);border-color:#f87171}
.ripple{position:absolute;border-radius:50%;background:rgba(255,255,255,.26);animation:rip .5s ease-out;pointer-events:none;transform:scale(0)}
@keyframes rip{to{transform:scale(5);opacity:0}}

/* layout */
.body{display:flex;flex:1;overflow:hidden}
.sidebar{width:200px;flex-shrink:0;background:rgba(0,0,0,.4);border-right:1px solid var(--border);
  display:flex;flex-direction:column;padding:10px 0;overflow-y:auto}
.sb-grp{padding:5px 12px 3px;font-size:9px;font-weight:700;letter-spacing:.7px;color:var(--text3);text-transform:uppercase;margin-top:5px}
.nav-item{display:flex;align-items:center;gap:9px;padding:8px 14px;cursor:pointer;
  transition:all var(--tr);position:relative;color:var(--text2);font-size:12px;font-weight:500;user-select:none}
.nav-item:hover{background:var(--surf);color:var(--text)}
.nav-item.active{background:linear-gradient(90deg,rgba(124,58,237,.16),transparent);color:var(--text)}
.nav-item.active::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;
  background:linear-gradient(var(--a1),var(--a2));border-radius:0 3px 3px 0}
.nav-icon{font-size:15px;width:20px;text-align:center}
.main{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:18px}

/* section header */
.sh{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.sh h2{font-size:17px;font-weight:700;letter-spacing:-.3px}
.sh .tag{font-size:9px;padding:3px 8px;border-radius:99px;
  background:linear-gradient(135deg,rgba(124,58,237,.2),rgba(6,182,212,.12));
  border:1px solid rgba(124,58,237,.33);color:var(--a2);font-weight:600;letter-spacing:.3px}

/* glass card */
.card{background:var(--surf);border:1px solid var(--border);border-radius:var(--rl);
  backdrop-filter:blur(14px);transition:all var(--tr)}
.card:hover{background:var(--surf2);border-color:var(--border2);box-shadow:0 8px 32px rgba(0,0,0,.5)}
.cb{padding:16px 18px}

/* op grid */
.ops-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.op-card{background:var(--surf);border:1px solid var(--border);border-radius:var(--rl);padding:16px;
  display:flex;flex-direction:column;gap:7px;transition:all var(--tr);position:relative;overflow:hidden}
.op-card::before{content:'';position:absolute;inset:0;border-radius:inherit;
  background:linear-gradient(135deg,var(--a1),var(--a2));opacity:0;transition:opacity var(--tr)}
.op-card:hover{border-color:rgba(124,58,237,.38);transform:translateY(-2px);box-shadow:0 10px 38px rgba(0,0,0,.5)}
.op-card:hover::before{opacity:.04}
.op-icon{width:38px;height:38px;border-radius:11px;background:linear-gradient(135deg,var(--a1),var(--a2));
  display:flex;align-items:center;justify-content:center;font-size:19px;
  box-shadow:0 4px 12px var(--glow);transition:all var(--tr)}
.op-card:hover .op-icon{box-shadow:0 6px 22px var(--glow);transform:scale(1.07)}
.op-title{font-size:13px;font-weight:600}
.op-desc{font-size:11px;color:var(--text3);line-height:1.5;flex:1}
.op-footer{display:flex;align-items:center;justify-content:flex-end;margin-top:4px}

/* stat cards */
.stats-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
@media(max-width:800px){.stats-grid{grid-template-columns:repeat(2,1fr)}}
.stat-card{background:var(--surf);border:1px solid var(--border);border-radius:var(--r);padding:14px;transition:all var(--tr)}
.stat-card:hover{background:var(--surf2);transform:translateY(-2px)}
.stat-lbl{font-size:10px;font-weight:600;color:var(--text3);text-transform:uppercase;letter-spacing:.5px}
.stat-val{font-size:24px;font-weight:700;letter-spacing:-.8px;
  background:linear-gradient(90deg,var(--a1),var(--a2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}

/* progress */
.prog-wrap{background:var(--surf);border:1px solid var(--border);border-radius:var(--r);padding:14px 18px}
.prog-track{height:5px;background:rgba(255,255,255,.06);border-radius:99px;overflow:hidden;margin:8px 0 4px}
.prog-fill{height:100%;border-radius:99px;background:linear-gradient(90deg,var(--a1),var(--a2));
  transition:width .18s ease;width:0%;box-shadow:0 0 8px var(--glow)}
.prog-row{display:flex;justify-content:space-between;font-size:11px}

/* log */
.log-card{background:rgba(0,0,0,.5);border:1px solid var(--border);border-radius:var(--r);overflow:hidden;
  flex:1;display:flex;flex-direction:column;min-height:100px}
.log-hdr{display:flex;align-items:center;padding:9px 14px;background:rgba(255,255,255,.03);border-bottom:1px solid var(--border)}
.log-body{flex:1;overflow-y:auto;font:12px/1.7 'Consolas','Menlo',monospace;padding:8px 14px}
.log-line{padding:1px 0;white-space:pre-wrap;word-break:break-all}
.log-ts{color:var(--text3);margin-right:7px}
.log-info{color:rgba(255,255,255,.65)}.log-success{color:#34d399}.log-warning{color:#fbbf24}.log-error{color:#f87171}

/* chips */
.chip-field{display:flex;flex-wrap:wrap;gap:5px;align-items:center;
  background:var(--surf);border:1px solid var(--border);border-radius:var(--rs);padding:7px 9px;
  transition:border-color var(--tr);cursor:text}
.chip-field:focus-within{border-color:var(--a1)}
.chip{display:inline-flex;align-items:center;gap:4px;padding:3px 9px;border-radius:99px;
  background:linear-gradient(135deg,rgba(124,58,237,.2),rgba(6,182,212,.12));
  border:1px solid rgba(124,58,237,.36);font-size:11px;font-weight:500;color:var(--text2);transition:all var(--tr)}
.chip:hover{color:var(--text);border-color:rgba(124,58,237,.6)}
.chip-x{cursor:pointer;opacity:.6;font-size:10px;transition:opacity var(--tr)}
.chip-x:hover{opacity:1;color:var(--red)}
.chip-input{background:transparent;border:none;outline:none;color:var(--text);font:400 12px var(--font);min-width:70px;flex:1}

/* pills */
.pills{display:flex;gap:5px;flex-wrap:wrap}
.pill{padding:4px 11px;border-radius:99px;background:var(--surf);border:1px solid var(--border);
  font-size:11px;font-weight:500;color:var(--text2);cursor:pointer;transition:all var(--tr);user-select:none}
.pill:hover{border-color:var(--border2);color:var(--text)}
.pill.active{background:linear-gradient(135deg,rgba(124,58,237,.28),rgba(6,182,212,.18));
  border-color:var(--a1);color:var(--text);box-shadow:0 0 10px var(--glow)}

/* drawer */
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.52);z-index:200;
  opacity:0;pointer-events:none;transition:opacity var(--tr);backdrop-filter:blur(4px)}
.overlay.open{opacity:1;pointer-events:all}
.drawer{position:fixed;top:0;right:0;bottom:0;width:380px;background:rgba(8,8,20,.97);
  border-left:1px solid var(--border);z-index:201;transform:translateX(100%);
  transition:transform .3s cubic-bezier(.4,0,.2,1);display:flex;flex-direction:column}
.drawer.open{transform:none}
.drawer-hdr{display:flex;align-items:center;padding:14px 18px;border-bottom:1px solid var(--border);flex-shrink:0}
.drawer-hdr h3{flex:1;font-size:14px;font-weight:600}
.drawer-body{flex:1;overflow-y:auto;padding:18px}
.sg{margin-bottom:20px}
.sl{font-size:10px;font-weight:700;color:var(--text3);letter-spacing:.5px;text-transform:uppercase;margin-bottom:7px}
.si{width:100%;background:var(--surf);border:1px solid var(--border);border-radius:var(--rs);
  padding:8px 11px;color:var(--text);font:12px var(--font);outline:none;transition:border-color var(--tr)}
.si:focus{border-color:var(--a1)}
.si-hint{font-size:9px;color:var(--text3);margin-top:3px}
.tog-row{display:flex;align-items:center;justify-content:space-between;padding:5px 0}
.tog-row span{font-size:12px;color:var(--text2)}
.tog{width:36px;height:20px;border-radius:99px;background:rgba(255,255,255,.1);border:1px solid var(--border);
  cursor:pointer;position:relative;transition:all var(--tr);flex-shrink:0}
.tog.on{background:linear-gradient(135deg,var(--a1),var(--a2));border-color:transparent}
.tog::after{content:'';position:absolute;top:2px;left:2px;width:14px;height:14px;border-radius:50%;
  background:#fff;transition:left var(--tr)}
.tog.on::after{left:18px}
.c-row{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.c-row label{font-size:12px;color:var(--text2);flex:1}
.c-row input[type=color]{width:38px;height:26px;border:1px solid var(--border);border-radius:8px;
  background:transparent;cursor:pointer;padding:2px}
.sp{height:1px;background:var(--border);margin:14px 0}

/* modal */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.72);z-index:250;
  display:flex;align-items:center;justify-content:center;
  opacity:0;pointer-events:none;transition:opacity var(--tr);backdrop-filter:blur(6px)}
.modal-overlay.open{opacity:1;pointer-events:all}
.modal{background:rgba(8,8,22,.98);border:1px solid var(--border);border-radius:var(--rl);
  display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,.8)}
.modal-hdr{padding:14px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px}
.modal-hdr h3{flex:1;font-size:14px;font-weight:600}
.modal-body{flex:1;overflow-y:auto}
.modal-foot{padding:12px 18px;border-top:1px solid var(--border);display:flex;gap:7px;justify-content:flex-end}
.browser-item{padding:9px 16px;display:flex;align-items:center;gap:9px;cursor:pointer;
  font-size:12px;color:var(--text2);transition:background var(--tr)}
.browser-item:hover{background:var(--surf2);color:var(--text)}

/* folder list */
.folder-list{max-height:120px;overflow-y:auto;margin-bottom:8px}
.folder-item{display:flex;align-items:center;gap:8px;padding:6px 10px;background:var(--surf);
  border:1px solid var(--border);border-radius:var(--rs);margin-bottom:4px;font-size:11px}
.folder-item-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.folder-item-remove{color:var(--text3);cursor:pointer;font-size:12px}
.folder-item-remove:hover{color:var(--red)}

/* duplicate checker */
.dup-grid{display:flex;gap:12px;flex-wrap:wrap;margin:10px 0}
.dup-card{background:var(--surf);border:1px solid var(--border);border-radius:var(--r);padding:12px;min-width:200px;flex:1}
.dup-card-header{font-size:11px;font-weight:600;color:var(--text2);margin-bottom:8px;display:flex;justify-content:space-between}
.dup-item{padding:6px 8px;margin:3px 0;background:rgba(0,0,0,.3);border-radius:6px;font-size:10px;
  display:flex;align-items:center;gap:6px;cursor:pointer}
.dup-item:hover{background:rgba(124,58,237,.15)}
.dup-item.selected{background:rgba(124,58,237,.25);border:1px solid var(--a1)}
.dup-checkbox{width:14px;height:14px}

/* ctx menu */
.ctx{position:fixed;background:rgba(10,10,22,.97);border:1px solid var(--border);border-radius:var(--rs);
  z-index:300;min-width:160px;box-shadow:0 8px 30px rgba(0,0,0,.6);
  opacity:0;pointer-events:none;transform:scale(.95);transition:all .14s ease;transform-origin:top left}
.ctx.open{opacity:1;pointer-events:all;transform:scale(1)}
.ctx-item{padding:8px 12px;font-size:12px;cursor:pointer;display:flex;align-items:center;gap:7px;
  color:var(--text2);transition:all var(--tr)}
.ctx-item:hover{background:var(--surf);color:var(--text)}
.ctx-sep{height:1px;background:var(--border);margin:2px 0}

/* toast */
#toasts{position:fixed;bottom:20px;right:20px;z-index:400;display:flex;flex-direction:column;gap:7px;align-items:flex-end}
.toast{display:flex;align-items:center;gap:9px;padding:10px 14px;border-radius:var(--rs);
  background:rgba(12,12,26,.97);border:1px solid var(--border);font-size:12px;
  backdrop-filter:blur(12px);animation:toastIn .28s ease;box-shadow:0 4px 18px rgba(0,0,0,.5);max-width:320px}
@keyframes toastIn{from{opacity:0;transform:translateX(28px)}to{opacity:1;transform:none}}
.toast.out{animation:toastOut .28s ease forwards}
@keyframes toastOut{to{opacity:0;transform:translateX(28px)}}
.toast-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}

/* discover */
.discover-card{background:var(--surf);border:1px solid var(--border);border-radius:var(--r);
  padding:14px 16px;display:flex;gap:12px;transition:all var(--tr)}
.discover-card:hover{background:var(--surf2);transform:translateY(-1px)}
.discover-links a{display:inline-flex;align-items:center;gap:4px;padding:4px 9px;border-radius:99px;
  font-size:10px;font-weight:600;text-decoration:none;border:1px solid var(--border);color:var(--text2);
  transition:all var(--tr);margin-right:5px;margin-top:4px}
.discover-links a:hover{border-color:var(--a1);color:var(--a2)}

/* genre manager */
.genre-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px;margin:10px 0}
.genre-pill{padding:7px 12px;border-radius:99px;background:var(--surf);border:1px solid var(--border);
  font-size:12px;cursor:pointer;transition:all var(--tr);user-select:none;display:flex;align-items:center;gap:6px}
.genre-pill:hover{border-color:var(--border2)}
.genre-pill.selected{background:rgba(239,68,68,.18);border-color:rgba(239,68,68,.5);color:#f87171}

/* tag editor */
.tag-panel{display:grid;grid-template-columns:240px 1fr;gap:14px}
.tag-list{background:var(--surf);border:1px solid var(--border);border-radius:var(--r);overflow-y:auto;max-height:320px}
.tag-file{padding:8px 12px;font-size:11px;cursor:pointer;border-bottom:1px solid rgba(255,255,255,.04);
  transition:background var(--tr);color:var(--text2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tag-file:hover{background:var(--surf2);color:var(--text)}
.tag-file.sel{background:rgba(124,58,237,.2);color:var(--text);border-left:3px solid var(--a1)}

/* pairing card */
.pair-card{background:var(--surf);border:1px solid var(--border);border-radius:var(--r);padding:20px;text-align:center}
.pair-url{font:700 20px 'Consolas','Menlo',monospace;color:var(--a2);margin:12px 0;word-break:break-all}
.pair-ip{font-size:11px;color:var(--text3);margin-top:4px}

/* credits panel */
.credits-panel{background:rgba(0,0,0,.4);border:1px solid var(--border);border-radius:var(--r);padding:14px;margin-top:20px}
.credits-title{font-size:11px;font-weight:600;color:var(--text2);margin-bottom:8px}
.credits-text{font-size:10px;color:var(--text3);line-height:1.6}
</style>
</head>
<body>
<canvas id="ambient"></canvas>
<div class="app">

<!-- TOPBAR -->
<header class="topbar">
  <a class="logo" href="#">
    <div class="logo-icon">⚡</div>
    <div><div class="logo-label">Songanizer Pro</div><div class="logo-ver">localhost:5050</div></div>
  </a>
  <div class="topbar-mid">
    <input id="folderInput" class="folder-input" placeholder="Add music folder…" spellcheck="false">
    <button class="btn btn-grad btn-sm" onclick="openBrowser()" title="Browse">📂</button>
    <button class="btn btn-grad btn-sm" onclick="addFolder()">+ Add</button>
    <button class="btn btn-sm" onclick="exportFileList()" title="Export file list for fast loading">📤</button>
    <button class="btn btn-sm" onclick="importFileList()" title="Import file list">📥</button>
  </div>
  <div class="topbar-right">
    <button class="btn btn-icon btn-sm" onclick="showSection('dashboard')" title="Dashboard">🏠</button>
    <button class="btn btn-grad btn-icon btn-sm" onclick="openDrawer()" title="Settings">⚙️</button>
  </div>
</header>

<!-- BODY -->
<div class="body">
<nav class="sidebar">
  <div class="sb-grp">Library</div>
  <div class="nav-item active" data-s="dashboard" onclick="showSection('dashboard')"><span class="nav-icon">🏠</span>Dashboard</div>
  <div class="nav-item" data-s="library" onclick="showSection('library')"><span class="nav-icon">📊</span>Analyze</div>
  <div class="nav-item" data-s="tagger" onclick="showSection('tagger')"><span class="nav-icon">🏷️</span>Tag Editor</div>
  <div class="sb-grp">Operations</div>
  <div class="nav-item" data-s="organize" onclick="showSection('organize')"><span class="nav-icon">📁</span>Organization</div>
  <div class="nav-item" data-s="cleanup" onclick="showSection('cleanup')"><span class="nav-icon">🧹</span>Cleanup</div>
  <div class="nav-item" data-s="media" onclick="showSection('media')"><span class="nav-icon">🖼️</span>Media</div>
  <div class="nav-item" data-s="diagnostics" onclick="showSection('diagnostics')"><span class="nav-icon">🔍</span>Diagnostics</div>
  <div class="sb-grp">Discovery</div>
  <div class="nav-item" data-s="discover" onclick="showSection('discover')"><span class="nav-icon">🎵</span>Music Discovery</div>
  <div class="nav-item" data-s="genres" onclick="showSection('genres')"><span class="nav-icon">🎭</span>Genre Manager</div>
  <div class="sb-grp">Plex</div>
  <div class="nav-item" data-s="plex" onclick="showSection('plex')"><span class="nav-icon">📺</span>Plex Integration</div>
  <div class="sb-grp">Access</div>
  <div class="nav-item" data-s="pairing" onclick="showSection('pairing')"><span class="nav-icon">📲</span>Device Pairing</div>
</nav>

<main class="main" id="mainContent">

<!-- DASHBOARD -->
<section id="section-dashboard">
  <div class="sh"><h2>Dashboard</h2><span class="tag">Overview</span>
    <button class="btn btn-grad btn-sm" style="margin-left:auto" onclick="runOp('analyze','Run full library analysis?')">🔄 Refresh</button></div>
  
  <div class="card cb" style="margin-bottom:14px">
    <div style="font-size:11px;color:var(--text3);margin-bottom:8px">LOADED FOLDERS</div>
    <div id="folderList" class="folder-list">
      <div style="color:var(--text3);font-size:12px">No folders loaded. Add folders above.</div>
    </div>
  </div>

  <div class="stats-grid">
    <div class="stat-card"><div class="stat-lbl">Total Files</div><div class="stat-val" id="st-total">—</div></div>
    <div class="stat-card"><div class="stat-lbl">Artists</div><div class="stat-val" id="st-artists">—</div></div>
    <div class="stat-card"><div class="stat-lbl">Albums</div><div class="stat-val" id="st-albums">—</div></div>
    <div class="stat-card"><div class="stat-lbl">FLAC</div><div class="stat-val" id="st-flac">—</div></div>
    <div class="stat-card"><div class="stat-lbl">MP3</div><div class="stat-val" id="st-mp3">—</div></div>
    <div class="stat-card"><div class="stat-lbl">Library Size</div><div class="stat-val" id="st-size">—</div></div>
  </div>
  <div class="prog-wrap" style="margin-bottom:14px">
    <div class="prog-row"><span id="progLabel" style="color:var(--text2);font-size:12px">Ready</span><span id="progPct" style="color:var(--a2);font-size:12px;font-weight:600"></span></div>
    <div class="prog-track"><div class="prog-fill" id="progFill"></div></div>
    <div style="font-size:10px;color:var(--text3);text-align:right" id="progEta"></div>
  </div>
  <div class="log-card">
    <div class="log-hdr">
      <span style="font-size:11px;font-weight:600;color:var(--text2);flex:1">Activity Log</span>
      <button class="btn btn-sm" onclick="exportLog()">Export</button>
      <button class="btn btn-sm" style="margin-left:5px" onclick="clearLog()">Clear</button>
    </div>
    <div class="log-body" id="logBody"></div>
  </div>
</section>

<!-- LIBRARY ANALYZE -->
<section id="section-library" style="display:none">
  <div class="sh"><h2>Analyze Library</h2><span class="tag">Library</span></div>
  <div class="ops-grid">
    <div class="op-card" oncontextmenu="ctx(event,[['📊 Run',()=>runOp('analyze','Analyze library?')]])">
      <div class="op-icon">📊</div><div class="op-title">Analyze Library</div>
      <div class="op-desc">Scan all audio files across all loaded folders — count formats, bitrates, artists, albums, total size.</div>
      <div class="op-footer"><button class="btn btn-grad btn-sm" onclick="runOp('analyze','Run full library analysis?')">Run ▶</button></div>
    </div>
    <div class="op-card">
      <div class="op-icon">📈</div><div class="op-title">Export Library Report</div>
      <div class="op-desc">Save a complete statistics report (formats, bitrates, all artists) as a .txt file.</div>
      <div class="op-footer"><button class="btn btn-grad btn-sm" onclick="runReport()">Export ▶</button></div>
    </div>
  </div>
</section>

<!-- ORGANIZE -->
<section id="section-organize" style="display:none">
  <div class="sh"><h2>Organization</h2><span class="tag">Files</span></div>
  <div class="ops-grid">
    <div class="op-card" oncontextmenu="ctx(event,[['📁 Run',()=>runOp('organize','Organize files?')],['⚙️ Settings',openDrawer]])">
      <div class="op-icon">📁</div><div class="op-title">Organize Files</div>
      <div class="op-desc" id="desc-organize">Move & rename files using your folder and naming patterns set in Settings.</div>
      <div class="op-footer"><button class="btn btn-grad btn-sm" onclick="runOp('organize','Organize files? This will move and rename audio files based on your patterns.')">Run ▶</button></div>
    </div>
    <div class="op-card">
      <div class="op-icon">👥</div><div class="op-title">Handle Various Artists</div>
      <div class="op-desc">Move tracks under "Various Artists" into each track's primary artist folder.</div>
      <div class="op-footer"><button class="btn btn-grad btn-sm" onclick="runOp('various','Move Various Artists tracks to their primary artist folders?')">Run ▶</button></div>
    </div>
  </div>
</section>

<!-- CLEANUP -->
<section id="section-cleanup" style="display:none">
  <div class="sh"><h2>Cleanup</h2><span class="tag">Files & Folders</span></div>
  <div class="ops-grid">
    <div class="op-card" oncontextmenu="ctx(event,[['🗑️ Run',()=>runOp('duplicates','⚠️ Delete duplicates?')]])">
      <div class="op-icon">🗑️</div><div class="op-title">Remove Duplicates (Single Folder)</div>
      <div class="op-desc" id="desc-dupes">Detect and delete duplicate tracks within the first loaded folder.</div>
      <div class="op-footer"><button class="btn btn-danger btn-sm" onclick="runOp('duplicates','⚠️ Permanently DELETE duplicate files?\n\nThis CANNOT be undone!')">Run ▶</button></div>
    </div>
    <div class="op-card" style="opacity:0.6">
      <div class="op-icon">🔄</div><div class="op-title">Cross-Folder Duplicate Check</div>
      <div class="op-desc">Find and manage duplicates across ALL loaded folders with manual selection. <span style="color:var(--warning)">(Deprecated)</span></div>
      <div class="op-footer"><button class="btn btn-sm" onclick="toast('Cross-folder duplicates deprecated','warning')" disabled>Deprecated</button></div>
    </div>
    <div class="op-card">
      <div class="op-icon">🧹</div><div class="op-title">Clean Duplicate Folders</div>
      <div class="op-desc">Remove album folders without year info when a dated counterpart exists.</div>
      <div class="op-footer"><button class="btn btn-grad btn-sm" onclick="runOp('clean_dup_fold','Remove duplicate (no-year) album folders?')">Run ▶</button></div>
    </div>
    <div class="op-card">
      <div class="op-icon">🗂️</div><div class="op-title">Clean Empty Folders</div>
      <div class="op-desc">Recursively find and delete every empty directory in the library.</div>
      <div class="op-footer"><button class="btn btn-grad btn-sm" onclick="runOp('clean_empty','Delete ALL empty directories?')">Run ▶</button></div>
    </div>
  </div>
  
  <!-- Cross-folder duplicates panel -->
  <div id="crossDupesPanel" class="card cb" style="margin-top:20px;display:none">
    <div class="sh"><h2>Cross-Folder Duplicates</h2></div>
    <div style="margin-bottom:14px">
      <div class="pills">
        <div class="pill active" data-val="all" onclick="setDupCheck(this,'all')">All</div>
        <div class="pill" data-val="filename" onclick="setDupCheck(this,'filename')">Filename</div>
        <div class="pill" data-val="tags" onclick="setDupCheck(this,'tags')">Tags (Artist+Title)</div>
        <div class="pill" data-val="metadata" onclick="setDupCheck(this,'metadata')">Full Metadata</div>
      </div>
    </div>
    <div style="display:flex;gap:8px;margin-bottom:14px">
      <button class="btn btn-grad btn-sm" onclick="runCrossDupes()">🔍 Scan for Duplicates</button>
      <button class="btn btn-danger btn-sm" id="moveDupesBtn" style="display:none" onclick="moveSelectedDupes()">📦 Move Selected</button>
    </div>
    <div id="dupResults" class="dup-grid"></div>
  </div>
</section>

<!-- MEDIA -->
<section id="section-media" style="display:none">
  <div class="sh"><h2>Media</h2><span class="tag">Covers & Playlists</span></div>
  <div class="ops-grid">
    <div class="op-card">
      <div class="op-icon">🖼️</div><div class="op-title">Generate Covers</div>
      <div class="op-desc" id="desc-covers">Extract embedded album artwork and save cover.png (or jpg) per album folder.</div>
      <div class="op-footer"><button class="btn btn-grad btn-sm" onclick="runOp('covers','Extract and save album cover art?')">Run ▶</button></div>
    </div>
    <div class="op-card">
      <div class="op-icon">🔄</div><div class="op-title">Rebuild All Covers</div>
      <div class="op-desc">Force-regenerate ALL cover images, overwriting any existing ones.</div>
      <div class="op-footer"><button class="btn btn-grad btn-sm" onclick="runOp('rebuild_covers','Overwrite ALL existing cover images?')">Run ▶</button></div>
    </div>
    <div class="op-card">
      <div class="op-icon">📝</div><div class="op-title">Generate Playlists</div>
      <div class="op-desc">Create .m3u playlist files inside every album folder, sorted by track number.</div>
      <div class="op-footer"><button class="btn btn-grad btn-sm" onclick="runOp('playlists','Generate M3U playlists for every album?')">Run ▶</button></div>
    </div>
  </div>
</section>

<!-- DIAGNOSTICS -->
<section id="section-diagnostics" style="display:none">
  <div class="sh"><h2>Diagnostics</h2><span class="tag">Quality</span></div>
  <div class="ops-grid">
    <div class="op-card">
      <div class="op-icon">🔍</div><div class="op-title">Find Missing Tags</div>
      <div class="op-desc">List all audio files that are missing artist, album, or title tags.</div>
      <div class="op-footer"><button class="btn btn-grad btn-sm" onclick="runOp('missing_tags','Scan library for files with missing tags?')">Run ▶</button></div>
    </div>
    <div class="op-card">
      <div class="op-icon">💔</div><div class="op-title">Scan Corrupt Files</div>
      <div class="op-desc">Attempt to open every audio file and report any that cannot be read.</div>
      <div class="op-footer"><button class="btn btn-danger btn-sm" onclick="runOp('corrupt','Scan entire library for corrupt files?')">Run ▶</button></div>
    </div>
  </div>
</section>

<!-- MUSIC DISCOVERY -->
<section id="section-discover" style="display:none">
  <div class="sh"><h2>Music Discovery</h2><span class="tag">AI Powered</span>
    <button class="btn btn-grad btn-sm" style="margin-left:auto" onclick="runDiscover()">🤖 Discover Now</button>
  </div>
  
  <div class="card cb" style="margin-bottom:14px">
    <p style="font-size:12px;color:var(--text2);line-height:1.7">
      AI will analyze your library's artists and suggest similar music you might love.<br>
      Each suggestion links to <strong>Tidal</strong>, <strong>Qobuz</strong>, and <strong>Monochrome</strong> for easy downloading.<br>
      Set your API key in ⚙️ Settings → AI Provider.
    </p>
  </div>
  
  <div class="card cb" style="margin-bottom:14px">
    <div style="font-size:11px;color:var(--text3);margin-bottom:8px">FILTER AI DISCOVERY (reduce load)</div>
    <p style="font-size:10px;color:var(--text3);margin-bottom:10px">Select genres or artists to limit AI analysis to specific items.</p>
    <div style="display:flex;gap:8px;margin-bottom:8px">
      <button class="btn btn-sm" onclick="loadFilterGenres()">🎭 Load Genres</button>
      <button class="btn btn-sm" onclick="loadFilterArtists()">👤 Load Artists</button>
    </div>
    <div id="filterGenres" class="genre-grid" style="max-height:150px;overflow-y:auto"></div>
    <div id="filterArtists" class="genre-grid" style="max-height:150px;overflow-y:auto;display:none"></div>
  </div>
  
  <div id="discoverResults" style="display:flex;flex-direction:column;gap:10px"></div>
  
  <!-- Spotiflac-like Find More Music -->
  <div class="card cb" style="margin-top:16px">
    <div class="sh"><h3>🔎 Find More Music</h3></div>
    <p style="font-size:12px;color:var(--text2);line-height:1.7;margin-bottom:12px">
      Search for artists to find additional tracks and albums. Select sources to download from.
    </p>
    <div style="display:flex;gap:8px;margin-bottom:12px">
      <input id="findMusicSearch" class="si" type="text" placeholder="Search for artist or song..." style="flex:1" onkeydown="if(event.key==='Enter')findMoreMusic()">
      <button class="btn btn-grad btn-sm" onclick="findMoreMusic()">Search</button>
    </div>
    <div id="findMusicResults" style="display:flex;flex-direction:column;gap:8px"></div>
  </div>
</section>

<!-- GENRE MANAGER -->
<section id="section-genres" style="display:none">
  <div class="sh"><h2>Genre Manager</h2><span class="tag">Bulk Removal</span>
    <button class="btn btn-sm" style="margin-left:auto" onclick="loadGenres()">🔍 Scan Genres</button>
  </div>
  <div class="card cb" style="margin-bottom:14px">
    <p style="font-size:12px;color:var(--text2);line-height:1.7;margin-bottom:10px">
      Select genres to <strong style="color:var(--red)">remove</strong> from your library.<br>
      Protected artists, albums, and songs (set in ⚙️ Settings) will never be deleted.
    </p>
    <div id="genreGrid" class="genre-grid"><span style="color:var(--text3);font-size:12px">Click "Scan Genres" to load genres from your library.</span></div>
    <div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap">
      <button class="btn btn-sm" onclick="previewGenreRemoval()">👁️ Preview Removal</button>
      <button class="btn btn-danger btn-sm" id="genreRemoveBtn" style="display:none" onclick="confirmGenreRemoval()">🗑️ Remove Marked Files</button>
    </div>
    <div id="genrePreview" style="margin-top:12px;font-size:11px;color:var(--text3);display:none">
      <span id="genreCount"></span>
      <div id="genreSample" style="margin-top:6px;max-height:120px;overflow-y:auto;font-family:'Consolas',monospace"></div>
    </div>
  </div>
</section>

<!-- PLEX INTEGRATION (DEPRECATED) -->
<section id="section-plex" style="display:none">
  <div class="sh"><h2>Plex Integration</h2><span class="tag" style="background:rgba(239,68,68,.18);border-color:rgba(239,68,68,.36);color:#f87171">Deprecated</span></div>
  <div class="card cb" style="margin-bottom:14px">
    <p style="font-size:12px;color:var(--text2);line-height:1.7">
      ⚠️ Plex integration has been deprecated and is no longer available.<br>
      Your music library management features remain fully functional.
    </p>
  </div>
</section>

<!-- TAG EDITOR -->
<section id="section-tagger" style="display:none">
  <div class="sh"><h2>Tag Editor</h2><span class="tag">Metadata</span>
    <button class="btn btn-grad btn-sm" style="margin-left:auto" onclick="loadTagFiles()">Load Files</button>
  </div>
  <div class="tag-panel">
    <div>
      <div style="font-size:10px;color:var(--text3);font-weight:700;letter-spacing:.5px;text-transform:uppercase;margin-bottom:6px">Files</div>
      <div class="tag-list" id="tagFileList"><div style="padding:16px;color:var(--text3);font-size:12px">Load files to begin.</div></div>
    </div>
    <div>
      <div style="font-size:10px;color:var(--text3);font-weight:700;letter-spacing:.5px;text-transform:uppercase;margin-bottom:10px">Edit Tags</div>
      <div id="tagForm" style="display:none">
        <div style="margin-bottom:9px"><label style="font-size:10px;color:var(--text3);display:block;margin-bottom:3px;text-transform:uppercase;letter-spacing:.4px">Title</label><input class="si" id="t-title"></div>
        <div style="margin-bottom:9px"><label style="font-size:10px;color:var(--text3);display:block;margin-bottom:3px;text-transform:uppercase;letter-spacing:.4px">Artist</label><input class="si" id="t-artist"></div>
        <div style="margin-bottom:9px"><label style="font-size:10px;color:var(--text3);display:block;margin-bottom:3px;text-transform:uppercase;letter-spacing:.4px">Album Artist</label><input class="si" id="t-albumartist"></div>
        <div style="margin-bottom:9px"><label style="font-size:10px;color:var(--text3);display:block;margin-bottom:3px;text-transform:uppercase;letter-spacing:.4px">Album</label><input class="si" id="t-album"></div>
        <div style="margin-bottom:9px"><label style="font-size:10px;color:var(--text3);display:block;margin-bottom:3px;text-transform:uppercase;letter-spacing:.4px">Track #</label><input class="si" id="t-tracknumber"></div>
        <div style="margin-bottom:9px"><label style="font-size:10px;color:var(--text3);display:block;margin-bottom:3px;text-transform:uppercase;letter-spacing:.4px">Year</label><input class="si" id="t-date"></div>
        <div style="margin-bottom:12px"><label style="font-size:10px;color:var(--text3);display:block;margin-bottom:3px;text-transform:uppercase;letter-spacing:.4px">Genre</label><input class="si" id="t-genre"></div>
        <div style="font-size:10px;color:var(--text3);margin-bottom:8px;word-break:break-all" id="tagFilePath"></div>
        <button class="btn btn-grad btn-sm" onclick="saveTags()">💾 Save Tags</button>
      </div>
      <div id="tagPlaceholder" style="color:var(--text3);font-size:12px;padding-top:12px">Select a file to edit its tags.</div>
    </div>
  </div>
</section>

<!-- DEVICE PAIRING -->
<section id="section-pairing" style="display:none">
  <div class="sh"><h2>Device Pairing</h2><span class="tag">Network Access</span></div>
  <div class="pair-card card" style="max-width:480px">
    <div style="font-size:13px;color:var(--text2);margin-bottom:6px">Access this app from any device on your network:</div>
    <div class="pair-url" id="pairUrl">Loading…</div>
    <div class="pair-ip" id="pairIp"></div>
    <div style="display:flex;gap:8px;justify-content:center;margin-top:14px;flex-wrap:wrap">
      <button class="btn btn-grad btn-sm" onclick="copyPairUrl()">📋 Copy URL</button>
      <button class="btn btn-sm" id="startupBtn" onclick="toggleStartup()">⟳ Enable Auto-Start</button>
    </div>
    <div style="margin-top:14px;padding:12px;background:rgba(0,0,0,.3);border-radius:10px;font-size:11px;color:var(--text3);line-height:1.7">
      <strong style="color:var(--text2)">How to connect from another device:</strong><br>
      1. Make sure both devices are on the same WiFi / LAN network.<br>
      2. Open a browser on the other device and paste the URL above.<br>
      3. Bookmark it — the server stays on as long as this PC is running.<br>
      4. Enable <em>Auto-Start</em> to launch automatically on system boot.
    </div>
  </div>
</section>

</main>
</div>
</div>

<!-- SETTINGS DRAWER -->
<div class="overlay" id="drawerOverlay" onclick="closeDrawer()"></div>
<div class="drawer" id="drawer">
  <div class="drawer-hdr"><h3>⚙️  Settings</h3><button class="btn btn-sm" onclick="closeDrawer()">✕</button></div>
  <div class="drawer-body">
    <div class="sg">
      <div class="sl">Theme Accent Colors</div>
      <div class="c-row"><label>Accent 1</label><input type="color" id="c-a1" value="#7c3aed" oninput="applyColors()"></div>
      <div class="c-row"><label>Accent 2</label><input type="color" id="c-a2" value="#06b6d4" oninput="applyColors()"></div>
      <div class="sl" style="margin-top:8px">Glow Intensity</div>
      <input type="range" min="0" max="45" value="22" id="c-glow" oninput="applyColors()" style="width:100%;accent-color:var(--a1)">
    </div>
    <div class="sp"></div>
    <div class="sg">
      <div class="sl">Audio Extensions</div>
      <div class="chip-field" id="extField" onclick="document.getElementById('extInput').focus()">
        <input id="extInput" class="chip-input" placeholder=".ogg .aac .wav…" onkeydown="addChip(event,'ext')">
      </div>
    </div>
    <div class="sg">
      <div class="sl">Excluded Folders</div>
      <div class="chip-field" id="exclField" onclick="document.getElementById('exclInput').focus()">
        <input id="exclInput" class="chip-input" placeholder="Playlists…" onkeydown="addChip(event,'excl')">
      </div>
    </div>
    <div class="sp"></div>
    <div class="sg">
      <div class="sl">Folder Structure</div>
      <input class="si" id="folderPattern" oninput="updatePreview()">
      <div class="si-hint">Vars: {albumartist}  {album}  {year}  {artist}</div>
    </div>
    <div class="sg">
      <div class="sl">File Naming Pattern</div>
      <input class="si" id="namingPattern" oninput="updatePreview()">
      <div class="si-hint">Vars: {artist}  {album}  {track:02d}  {title}  {year}</div>
    </div>
    <div class="sg">
      <div class="sl">Live Preview</div>
      <div style="background:rgba(0,0,0,.4);border:1px solid var(--border);border-radius:9px;padding:10px;font:11px/1.8 'Consolas',monospace;color:var(--a2)" id="livePreview"></div>
    </div>
    <div class="sp"></div>
    <div class="sg">
      <div class="sl">Duplicate Priority</div>
      <div class="pills" id="dupPills">
        <div class="pill active" data-val="deluxe" onclick="setPill('dup',this)">Deluxe first</div>
        <div class="pill" data-val="flac" onclick="setPill('dup',this)">FLAC first</div>
        <div class="pill" data-val="largest" onclick="setPill('dup',this)">Largest</div>
      </div>
    </div>
    <div class="sg">
      <div class="sl">Cover Format</div>
      <div class="pills" id="coverPills">
        <div class="pill active" data-val="png" onclick="setPill('cover',this)">PNG</div>
        <div class="pill" data-val="jpg" onclick="setPill('cover',this)">JPG</div>
      </div>
    </div>
    <div class="sp"></div>
    <div class="sg">
      <div class="sl">Options</div>
      <div class="tog-row"><span>Backup before moving files</span><div class="tog" id="tog-backup" onclick="this.classList.toggle('on')"></div></div>
      <div class="tog-row"><span>Auto-generate playlists after organizing</span><div class="tog" id="tog-playlist" onclick="this.classList.toggle('on')"></div></div>
      <div class="tog-row"><span>Write activity log to file</span><div class="tog" id="tog-logfile" onclick="this.classList.toggle('on')"></div></div>
    </div>
    <div class="sp"></div>
    <div class="sg">
      <div class="sl">AI Music Discovery (Multi-Engine)</div>
      <div class="pills" id="aiPills" style="margin-bottom:8px">
        <div class="pill" data-val="openai" onclick="toggleAiPill(this)">GPT / OpenAI</div>
        <div class="pill" data-val="gemini" onclick="toggleAiPill(this)">Gemini</div>
        <div class="pill" data-val="claude" onclick="toggleAiPill(this)">Claude</div>
      </div>
      <input class="si" id="openaiKey" placeholder="OpenAI API Key…" type="password" style="margin-bottom:5px">
      <input class="si" id="geminiKey" placeholder="Google Gemini API Key…" type="password" style="margin-bottom:5px">
      <input class="si" id="claudeKey" placeholder="Anthropic Claude API Key…" type="password">
    </div>
    <div class="sp"></div>
    <div class="sg">
      <div class="sl">Plex Configuration</div>
      <input class="si" id="plexUrl" placeholder="Plex URL (e.g. http://127.0.0.1:32400)" style="margin-bottom:5px">
      <input class="si" id="plexToken" placeholder="Plex Token" type="password" style="margin-bottom:5px">
      <input class="si" id="plexSection" placeholder="Music Library Section Name" style="margin-bottom:5px">
      <div class="si-hint">Get your token from: plex.tv/link</div>
    </div>
    <div class="sp"></div>
    <div class="sg">
      <div class="sl">Genre Protection — Protected Artists</div>
      <div class="chip-field" id="paField" onclick="document.getElementById('paInput').focus()">
        <input id="paInput" class="chip-input" placeholder="Artist name…" onkeydown="addChip(event,'pa')">
      </div>
    </div>
    <div class="sg">
      <div class="sl">Protected Albums</div>
      <div class="chip-field" id="pbField" onclick="document.getElementById('pbInput').focus()">
        <input id="pbInput" class="chip-input" placeholder="Album name…" onkeydown="addChip(event,'pb')">
      </div>
    </div>
    <div class="sg">
      <div class="sl">Protected Songs</div>
      <div class="chip-field" id="psField" onclick="document.getElementById('psInput').focus()">
        <input id="psInput" class="chip-input" placeholder="Song title…" onkeydown="addChip(event,'ps')">
      </div>
    </div>
    <div class="sp"></div>
    
    <!-- Credits Panel (Hidden Version) -->
    <div class="credits-panel">
      <div class="credits-title">ABOUT</div>
      <div class="credits-text">
        <strong>Songanizer Pro</strong><br>
        Version 0.07 (hidden)<br><br>
        Developed by: <strong>0pxxL</strong><br><br>
        A powerful multi-folder music library manager with AI discovery, Plex integration, and advanced cleanup tools.
      </div>
    </div>
    
    <div class="sp"></div>
    <div style="display:flex;gap:8px">
      <button class="btn btn-grad" style="flex:1;justify-content:center;padding:10px;font-size:13px" onclick="saveSettings()">💾  Save</button>
      <button class="btn" style="flex:1;justify-content:center;padding:10px;font-size:13px" onclick="exportSettings()">📤 Export</button>
      <button class="btn" style="flex:1;justify-content:center;padding:10px;font-size:13px" onclick="importSettings()">📥 Import</button>
    </div>
  </div>
</div>

<!-- FOLDER BROWSER MODAL -->
<div class="modal-overlay" id="browserOverlay">
  <div class="modal" style="width:500px;max-height:60vh">
    <div class="modal-hdr"><h3>📂  Browse Folders</h3><button class="btn btn-sm" onclick="closeBrowser()">✕</button></div>
    <div style="padding:8px 14px;font-size:11px;color:var(--text3);word-break:break-all" id="browserPath">Select a drive or paste a path below</div>
    <div class="modal-body" id="browserList" style="max-height:340px"></div>
    <div class="modal-foot">
      <button class="btn btn-sm" onclick="closeBrowser()">Cancel</button>
      <button class="btn btn-grad btn-sm" onclick="selectBrowserPath()">✓ Select This Folder</button>
    </div>
  </div>
</div>

<!-- CONFIRM MODAL -->
<div class="modal-overlay" id="confirmOverlay">
  <div class="modal" style="width:400px">
    <div class="modal-hdr" style="flex-direction:column;text-align:center;gap:6px;padding:22px">
      <div style="font-size:28px">⚠️</div>
      <h3 id="confirmMsg" style="font-size:13px;font-weight:400;line-height:1.55;color:var(--text2)"></h3>
    </div>
    <div class="modal-foot">
      <button class="btn btn-sm" onclick="confResolve(false)" style="flex:1;justify-content:center">Cancel</button>
      <button class="btn btn-grad btn-sm" onclick="confResolve(true)" style="flex:1;justify-content:center">Proceed</button>
    </div>
  </div>
</div>

<div class="ctx" id="ctxMenu"></div>
<div id="toasts"></div>

<script>
// ── AMBIENT ──────────────────────────────────────────────────
const cvs=document.getElementById('ambient'),ctx2=cvs.getContext('2d');
let mx=innerWidth/2,my=innerHeight/2,cx=-9999,cy=-9999,ct=0,a1rgb=[124,58,237];
document.addEventListener('mousemove',e=>{mx=e.clientX;my=e.clientY});
document.addEventListener('click',e=>{
  cx=e.clientX;cy=e.clientY;ct=Date.now();
  const el=e.target.closest('.btn,.op-card,.nav-item,.pill,.genre-pill');
  if(el)ripple(el,e);
});
window.addEventListener('resize',()=>{cvs.width=innerWidth;cvs.height=innerHeight});
function h2r(h){return[parseInt(h.slice(1,3),16),parseInt(h.slice(3,5),16),parseInt(h.slice(5,7),16)]}
function drawAmbient(){
  cvs.width=innerWidth;cvs.height=innerHeight;ctx2.clearRect(0,0,cvs.width,cvs.height);
  const g=ctx2.createRadialGradient(mx,my,0,mx,my,300);
  g.addColorStop(0,`rgba(${a1rgb.join(',')},0.09)`);g.addColorStop(1,'rgba(0,0,0,0)');
  ctx2.fillStyle=g;ctx2.fillRect(0,0,cvs.width,cvs.height);
  const e2=Date.now()-ct;
  if(e2<900){const r=e2*.55,a=.4*(1-e2/900);
    const cg=ctx2.createRadialGradient(cx,cy,r*.1,cx,cy,r);
    cg.addColorStop(0,`rgba(${a1rgb.join(',')},${a})`);cg.addColorStop(1,'rgba(0,0,0,0)');
    ctx2.fillStyle=cg;ctx2.fillRect(0,0,cvs.width,cvs.height);}
  requestAnimationFrame(drawAmbient);
}
drawAmbient();
function ripple(el,e){
  const rect=el.getBoundingClientRect(),d=Math.max(rect.width,rect.height)*2;
  const r=document.createElement('span');r.className='ripple';
  r.style.cssText=`width:${d}px;height:${d}px;left:${e.clientX-rect.left-d/2}px;top:${e.clientY-rect.top-d/2}px`;
  el.appendChild(r);setTimeout(()=>r.remove(),520);
}

// ── COLORS ───────────────────────────────────────────────────
function applyColors(){
  const a1=document.getElementById('c-a1').value,a2=document.getElementById('c-a2').value;
  const gv=parseFloat(document.getElementById('c-glow').value)/100;
  document.documentElement.style.setProperty('--a1',a1);
  document.documentElement.style.setProperty('--a2',a2);
  document.documentElement.style.setProperty('--glow',`rgba(${h2r(a1).join(',')},${gv})`);
  document.documentElement.style.setProperty('--glow2',`rgba(${h2r(a2).join(',')},${gv*.8})`);
  a1rgb=h2r(a1);
}

// ── SECTIONS ─────────────────────────────────────────────────
function showSection(id){
  document.querySelectorAll('.main > section').forEach(s=>s.style.display='none');
  const el=document.getElementById('section-'+id);if(el)el.style.display='';
  document.querySelectorAll('.nav-item').forEach(n=>n.classList.toggle('active',n.dataset.s===id));
  if(id==='pairing')loadPairingInfo();
}

// ── FOLDERS ─────────────────────────────────────────────────
let _folders=[];
async function loadFolders(){
  const d=await fetch('/api/folders').then(r=>r.json());
  _folders=d.folders||[];
  renderFolderList();
}
function renderFolderList(){
  const el=document.getElementById('folderList');
  if(!_folders.length){
    el.innerHTML='<div style="color:var(--text3);font-size:12px">No folders loaded. Add folders above.</div>';
    return;
  }
  el.innerHTML=_folders.map((f,i)=>`
    <div class="folder-item">
      <span class="folder-item-name" title="${esc(f)}">📁 ${f.split('\\').pop().split('/').pop()}</span>
      <span class="folder-item-remove" onclick="removeFolder(${i})">✕</span>
    </div>
  `).join('');
}
async function addFolder(){
  const p=document.getElementById('folderInput').value.trim();
  if(!p){toast('Enter or browse to a folder first.','warning');return;}
  await fetch('/api/folders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder:p})});
  document.getElementById('folderInput').value='';
  await loadFolders();
  toast('Folder added!','success');
}
async function removeFolder(index){
  await fetch(`/api/folders/${index}`,{method:'DELETE'});
  await loadFolders();
  toast('Folder removed.','info');
}

// ── SETTINGS ─────────────────────────────────────────────────
const _chips={ext:[],excl:[],pa:[],pb:[],ps:[]};
let _aiProviders=new Set(['openai']);
async function openDrawer(){
  const s=await fetch('/api/settings').then(r=>r.json());
  document.getElementById('folderPattern').value=s.folder_pattern||'';
  document.getElementById('namingPattern').value=s.naming_pattern||'';
  document.getElementById('c-a1').value=s.accent1||'#7c3aed';
  document.getElementById('c-a2').value=s.accent2||'#06b6d4';
  document.getElementById('openaiKey').value=s.openai_key||'';
  document.getElementById('geminiKey').value=s.gemini_key||'';
  document.getElementById('claudeKey').value=s.claude_key||'';
  document.getElementById('plexUrl').value=s.plex_url||'http://127.0.0.1:32400';
  document.getElementById('plexToken').value=s.plex_token||'';
  document.getElementById('plexSection').value=s.plex_music_section||'Music';
  setTog('tog-backup',s.backup_before_move);setTog('tog-playlist',s.auto_playlist);setTog('tog-logfile',s.log_to_file);
  setPillByVal('dup',s.dup_priority||'deluxe');setPillByVal('cover',s.cover_format||'png');
  _aiProviders=new Set(s.ai_providers||['openai']);
  updateAiPills();
  renderChips('ext',s.extensions||['.flac','.mp3']);renderChips('excl',s.excluded_folders||[]);
  renderChips('pa',s.protected_artists||[]);renderChips('pb',s.protected_albums||[]);renderChips('ps',s.protected_songs||[]);
  applyColors();updatePreview();
  document.getElementById('drawerOverlay').classList.add('open');
  document.getElementById('drawer').classList.add('open');
}
function closeDrawer(){
  document.getElementById('drawerOverlay').classList.remove('open');
  document.getElementById('drawer').classList.remove('open');
}
function saveSettings(){
  const d={
    folder_pattern:    document.getElementById('folderPattern').value,
    naming_pattern:    document.getElementById('namingPattern').value,
    accent1:           document.getElementById('c-a1').value,
    accent2:           document.getElementById('c-a2').value,
    glow_opacity:      parseFloat(document.getElementById('c-glow').value)/100,
    extensions:        chipVals('ext'),excluded_folders:chipVals('excl'),
    backup_before_move:isTog('tog-backup'),auto_playlist:isTog('tog-playlist'),log_to_file:isTog('tog-logfile'),
    dup_priority:  activePill('#dupPills')||'deluxe',
    cover_format:  activePill('#coverPills')||'png',
    ai_providers:  [..._aiProviders],
    openai_key:    document.getElementById('openaiKey').value,
    gemini_key:    document.getElementById('geminiKey').value,
    claude_key:    document.getElementById('claudeKey').value,
    plex_url:      document.getElementById('plexUrl').value,
    plex_token:    document.getElementById('plexToken').value,
    plex_music_section: document.getElementById('plexSection').value,
    protected_artists:chipVals('pa'),protected_albums:chipVals('pb'),protected_songs:chipVals('ps'),
  };
  fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)})
    .then(()=>{toast('Settings saved!','success');updateOrganizeDesc();closeDrawer();});
}
function exportSettings(){
  window.location.href='/api/settings/export';
}
function importSettings(){
  const input=document.createElement('input');
  input.type='file';
  input.accept='.json';
  input.onchange=async(e)=>{
    const file=e.target.files[0];
    if(!file)return;
    const text=await file.text();
    try{
      const data=JSON.parse(text);
      const res=await fetch('/api/settings/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
      const j=await res.json();
      if(j.ok){toast('Settings imported!','success');loadSettings();}
      else{toast(j.error||'Import failed','error');}
    }catch(err){toast('Invalid JSON file','error');}
  };
  input.click();
}
function exportFileList(){
  if(!_folders.length){toast('Add folders first.','warning');return;}
  toast('Generating file list...','info');
  window.location.href='/api/files/export';
}
function importFileList(){
  const input=document.createElement('input');
  input.type='file';
  input.accept='.json';
  input.onchange=async(e)=>{
    const file=e.target.files[0];
    if(!file)return;
    toast('Importing file list...','info');
    const text=await file.text();
    try{
      const data=JSON.parse(text);
      const res=await fetch('/api/files/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
      const j=await res.json();
      if(j.ok){
        toast(j.message,'success');
        loadFolders();
      }else{
        toast(j.error||'Import failed','error');
      }
    }catch(err){toast('Invalid JSON file','error');}
  };
  input.click();
}
function toggleAiPill(el){
  const val=el.dataset.val;
  if(_aiProviders.has(val)){_aiProviders.delete(val);el.classList.remove('active');}
  else{_aiProviders.add(val);el.classList.add('active');}
}
function updateAiPills(){
  document.querySelectorAll('#aiPills .pill').forEach(p=>{
    p.classList.toggle('active',_aiProviders.has(p.dataset.val));
  });
}
function setPill(g,el){
  const sel={'dup':'#dupPills','cover':'#coverPills'}[g];
  document.querySelectorAll(sel+' .pill').forEach(x=>x.classList.remove('active'));
  el.classList.add('active');
}
function setPillByVal(g,v){
  const sel={'dup':'#dupPills','cover':'#coverPills'}[g];
  document.querySelectorAll(sel+' .pill').forEach(x=>x.classList.toggle('active',x.dataset.val===v));
}
function activePill(sel){return document.querySelector(sel+' .pill.active')?.dataset.val}
function setTog(id,v){document.getElementById(id)?.classList.toggle('on',!!v)}
function isTog(id){return!!document.getElementById(id)?.classList.contains('on')}
const chipFields={ext:'extField',excl:'exclField',pa:'paField',pb:'pbField',ps:'psField'};
function renderChips(g,tags){
  _chips[g]=[...tags];
  const field=document.getElementById(chipFields[g]),input=document.getElementById(g+'Input');
  if(!field)return;
  field.querySelectorAll('.chip').forEach(c=>c.remove());
  tags.forEach(t=>{
    const c=document.createElement('div');c.className='chip';
    c.innerHTML=`<span>${esc(t)}</span><span class="chip-x" onclick="removeChip('${g}','${t.replace(/'/g,"\\'")}')">✕</span>`;
    field.insertBefore(c,input);
  });
}
function addChip(e,g){
  if(e.key!=='Enter'&&e.key!==',')return;e.preventDefault();
  const inp=document.getElementById(g+'Input'),v=inp.value.trim();
  if(v&&!_chips[g].includes(v)){_chips[g].push(v);renderChips(g,_chips[g]);}
  inp.value='';
}
function removeChip(g,v){_chips[g]=_chips[g].filter(x=>x!==v);renderChips(g,_chips[g])}
function chipVals(g){return[..._chips[g]]}
function updatePreview(){
  const fp=document.getElementById('folderPattern')?.value||'',np=document.getElementById('namingPattern')?.value||'';
  const s={albumartist:'Boards of Canada',artist:'Boards of Canada',album:'Geogaddi',year:'2002',track:1,title:'Music Is Math',ext:'.flac'};
  let prev='';
  try{
    const folder=fp.replace(/\{(\w+)(?::([^}]+))?\}/g,(_,k,f)=>k==='track'?String(s[k]).padStart(2,'0'):s[k]||'?');
    const file=np.replace(/\{(\w+)(?::([^}]+))?\}/g,(_,k,f)=>k==='track'?String(s[k]).padStart(2,'0'):s[k]||'?')+s.ext;
    let i='';prev=folder.replace(/\\/g,'/').split('/').map(p=>{const l=i+'📁 '+p+'/';i+='  ';return l}).join('\n')+'\n'+i+'🎵 '+file;
  }catch(e){prev='⚠ '+e.message;}
  const el=document.getElementById('livePreview');if(el)el.textContent=prev;
  updateOrganizeDesc();
}
function updateOrganizeDesc(){
  const fp=document.getElementById('folderPattern')?.value||'',np=document.getElementById('namingPattern')?.value||'';
  const el=document.getElementById('desc-organize');
  if(el)el.textContent=`Move & rename files to: ${fp}/${np}.ext  (based on audio tag metadata)`;
}

// ── FOLDER BROWSER ───────────────────────────────────────────
let _selPath='';
function openBrowser(){browserNav('');document.getElementById('browserOverlay').classList.add('open')}
function closeBrowser(){document.getElementById('browserOverlay').classList.remove('open')}
function selectBrowserPath(){if(_selPath)document.getElementById('folderInput').value=_selPath;closeBrowser();}
function browserNav(path){
  fetch('/api/list-dir',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path})})
  .then(r=>r.json()).then(d=>{
    _selPath=d.path||path;
    document.getElementById('browserPath').textContent=_selPath||'Select a drive:';
    const list=document.getElementById('browserList');list.innerHTML='';
    if(d.parent!==undefined&&d.parent!==_selPath&&!d.is_root){
      const up=document.createElement('div');up.className='browser-item';
      up.innerHTML='⬆️ &nbsp;..';up.onclick=()=>browserNav(d.parent);list.appendChild(up);
    }
    (d.dirs||[]).forEach(dir=>{
      const it=document.createElement('div');it.className='browser-item';
      it.innerHTML='📁 &nbsp;'+dir.split('\\').pop().split('/').pop();
      it.onclick=()=>browserNav(dir);list.appendChild(it);
    });
    if((d.dirs||[]).length===0){list.innerHTML='<div style="padding:16px;color:var(--text3);font-size:12px">No subfolders (or permission denied)</div>';}
  });
}

// ── CONFIRM DIALOG ───────────────────────────────────────────
let _confRes=null;
function conf(msg){return new Promise(r=>{_confRes=r;document.getElementById('confirmMsg').textContent=msg;document.getElementById('confirmOverlay').classList.add('open');})}
function confResolve(v){document.getElementById('confirmOverlay').classList.remove('open');if(_confRes){_confRes(v);_confRes=null;}}

// ── OPERATIONS ───────────────────────────────────────────────
async function runOp(opId,msg){
  if(!await conf(msg))return;
  const s=await fetch('/api/settings').then(r=>r.json());
  if(!_folders.length){toast('Add folders first.','warning');return;}
  resetProg();showSection('dashboard');
  fetch(`/api/run/${opId}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({settings:s})});
}
async function runDiscover(){
  if(!_folders.length){toast('Add folders first.','warning');return;}
  if(!await conf('Use AI to find music similar to your selected artists/genres?'))return;
  const s=await fetch('/api/settings').then(r=>r.json());
  resetProg();showSection('dashboard');
  // Send only selected artists and genres
  const selectedGenres = [..._filterGenres];
  const selectedArtists = [..._filterArtists];
  fetch('/api/run/discover',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({
      settings:s,
      filters: {
        genres: selectedGenres,
        artists: selectedArtists
      }
    })
  });
  toast('Running AI discovery with '+selectedArtists.length+' artists and '+selectedGenres.length+' genres','info');
}
async function runReport(){
  if(!await conf('Generate and save a full library statistics report?'))return;
  const s=await fetch('/api/settings').then(r=>r.json());
  const out=prompt('Save path:',s.log_path?.replace('songanizer_log','library_report')||'C:/library_report.txt');
  if(!out)return;
  fetch('/api/run/report',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({output:out,settings:s})});
  showSection('dashboard');
}

// ── CROSS-FOLDER DUPLICATES ─────────────────────────────────
let _dupCheckType='all';
let _dupResults=[];
function setDupCheck(el,val){
  document.querySelectorAll('#crossDupesPanel .pill').forEach(p=>p.classList.remove('active'));
  el.classList.add('active');
  _dupCheckType=val;
}
function showCrossDupes(){
  document.getElementById('crossDupesPanel').style.display='';
  showSection('cleanup');
}
async function runCrossDupes(){
  const s=await fetch('/api/settings').then(r=>r.json());
  fetch('/api/run/cross_dupes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({check_type:_dupCheckType,settings:s})});
}
async function moveSelectedDupes(){
  const moves=[];
  document.querySelectorAll('.dup-item.selected').forEach(el=>{
    const from=el.dataset.path;
    const to=el.dataset.tofolder;
    if(from&&to)moves.push({from,to});
  });
  if(!moves.length){toast('Select files to move.','warning');return;}
  if(!await conf(`Move ${moves.length} files to selected destination?`))return;
  fetch('/api/run/move_duplicates',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({moves})});
}

// ── PLEX ─────────────────────────────────────────────────────
async function searchPlexArtist(){
  const q=document.getElementById('plexArtistSearch').value.trim();
  if(!q){toast('Enter artist name.','warning');return;}
  const s=await fetch('/api/settings').then(r=>r.json());
  document.getElementById('plexArtistResults').innerHTML='<div style="padding:20px;text-align:center;color:var(--text3)">🔍 Searching Plex for "'+esc(q)+'"...</div>';
  fetch('/api/run/plex_search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q,settings:s})});
}
function renderPlexArtistResults(d){
  const container=document.getElementById('plexArtistResults');
  if(!d.artists||!d.artists.length){
    container.innerHTML='<div style="padding:20px;text-align:center;color:var(--text3)">⚠️ No artists found matching your search.</div>';
    return;
  }
  let html='<div style="display:flex;flex-direction:column;gap:8px">';
  html+='<div style="font-size:12px;color:var(--text3);margin-bottom:8px">Found '+d.artists.length+' matching artist(s):</div>';
  d.artists.forEach((a,i)=>{
    html+='<div class="card cb" style="padding:12px;cursor:pointer" onclick="selectPlexArtist(\''+esc(a.title.replace(/'/g,"\\'"))+'\')">';
    html+='<div style="font-weight:600">'+esc(a.title)+'</div>';
    html+='<div style="font-size:11px;color:var(--text3)">'+a.albums+' albums</div>';
    html+='</div>';
  });
  html+='</div>';
  container.innerHTML=html;
}
function selectPlexArtist(artistTitle){
  if(!confirm('Rate all tracks by "'+artistTitle+'" in Plex?'))return;
  const s={plex_target_rating:10.0};
  fetch('/api/run/plex_search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:artistTitle,settings:s})});
  document.getElementById('plexArtistResults').innerHTML='<div style="padding:20px;text-align:center;color:var(--success)">✅ Rating tracks by "'+esc(artistTitle)+'"...</div>';
}

// ── FILTER GENRES/ARTISTS ────────────────────────────────────
let _filterGenres=new Set();
let _filterArtists=new Set();
async function loadFilterGenres(){
  const d=await fetch('/api/genres',{method:'POST'}).then(r=>r.json());
  const grid=document.getElementById('filterGenres');
  grid.innerHTML='';grid.style.display='';
  document.getElementById('filterArtists').style.display='none';
  (d.genres||[]).forEach(g=>{
    const p=document.createElement('div');p.className='genre-pill';
    p.innerHTML=`<span>🎭</span><span>${esc(g)}</span>`;
    p.onclick=()=>{p.classList.toggle('selected');if(p.classList.contains('selected'))_filterGenres.add(g);else _filterGenres.delete(g);};
    grid.appendChild(p);
  });
}
let _allArtists=[];
async function loadFilterArtists(){
  const d=await fetch('/api/artists',{method:'POST'}).then(r=>r.json());
  const grid=document.getElementById('filterArtists');
  grid.innerHTML='';grid.style.display='';
  document.getElementById('filterGenres').style.display='none';
  // Store all artists and show with search
  _allArtists = (d.artists||[]).sort((a,b)=>a.localeCompare(b));
  if(_allArtists.length>500){
    grid.innerHTML='<div style="padding:8px;font-size:11px;color:var(--text3);margin-bottom:8px">'
      +'Search: <input type="text" id="artistSearch" class="si" placeholder="Filter artists..." style="width:200px;margin-left:5px" oninput="filterArtistsList()">'
      +'<br>Showing first 500 of '+_allArtists.length+' artists</div>';
  }
  renderArtistsGrid(_allArtists.slice(0,500));
}
function renderArtistsGrid(artists){
  const grid=document.getElementById('filterArtists');
  // Keep search box if exists
  const searchBox = document.getElementById('artistSearch');
  if(searchBox){
    const wrapper = searchBox.parentElement;
    grid.innerHTML = '';
    grid.appendChild(wrapper);
  }
  artists.forEach(a=>{
    const p=document.createElement('div');p.className='genre-pill';
    p.innerHTML=`<span>👤</span><span>${esc(a)}</span>`;
    p.onclick=()=>{p.classList.toggle('selected');if(p.classList.contains('selected'))_filterArtists.add(a);else _filterArtists.delete(a);};
    grid.appendChild(p);
  });
}
let _artistSearchTimeout = null;
function filterArtistsList(){
  // Debounce to prevent re-rendering on each keystroke
  if(_artistSearchTimeout) clearTimeout(_artistSearchTimeout);
  _artistSearchTimeout = setTimeout(()=>{
    const search = document.getElementById('artistSearch').value.toLowerCase();
    const filtered = _allArtists.filter(a=>a.toLowerCase().includes(search)).slice(0,200);
    renderArtistsGrid(filtered);
  }, 300);
}

// ── SSE ──────────────────────────────────────────────────────
let _pt=1,_ps=Date.now();
const es=new EventSource('/api/events');
es.onmessage=e=>{
  const d=JSON.parse(e.data);
  if(d.type==='log')logLine(d.message,d.level);
  else if(d.type==='progress'){_pt=d.total;updateProg(d.current,d.total,d.label);}
  else if(d.type==='done'){fillProg(d.message);toast(d.message,'success');_ps=Date.now();}
  else if(d.type==='stats')updateStats(d);
  else if(d.type==='discover_results')renderDiscovery(d.suggestions,d.provider);
  else if(d.type==='cross_duplicates')renderDupResults(d.duplicates);
  else if(d.type==='plex_search_results')renderPlexArtistResults(d);
};

// ── PROGRESS ─────────────────────────────────────────────────
function resetProg(){updateProg(0,1,'Starting…');_ps=Date.now();}
function updateProg(c,t,lbl){
  const p=t?Math.min(100,Math.round(c/t*100)):0;
  document.getElementById('progFill').style.width=p+'%';
  document.getElementById('progPct').textContent=p?p+'%':'';
  if(lbl)document.getElementById('progLabel').textContent=lbl;
  if(p>2){const el=(Date.now()-_ps)/1000,e2=el/(p/100)-el;document.getElementById('progEta').textContent='ETA: '+Math.round(e2)+'s';}
}
function fillProg(m){
  document.getElementById('progFill').style.width='100%';document.getElementById('progPct').textContent='100%';
  document.getElementById('progLabel').textContent=m;document.getElementById('progEta').textContent='';
}

// ── LOG ──────────────────────────────────────────────────────
const _ll=[];
function logLine(m,lv='info'){
  _ll.push({m,lv});const b=document.getElementById('logBody');
  const ts=new Date().toTimeString().slice(0,8);
  const d=document.createElement('div');d.className='log-line';
  d.innerHTML=`<span class="log-ts">[${ts}]</span><span class="log-${lv}">${esc(m)}</span>`;
  b.appendChild(d);b.scrollTop=b.scrollHeight;
}
function clearLog(){document.getElementById('logBody').innerHTML='';_ll.length=0;}
function exportLog(){
  const a=document.createElement('a');a.href='data:text/plain;charset=utf-8,'+encodeURIComponent(_ll.map(l=>`[${l.lv}] ${l.m}`).join('\n'));a.download='songanizer_log.txt';a.click();
}
function updateStats(d){
  document.getElementById('st-total').textContent=d.total?.toLocaleString()||'—';
  document.getElementById('st-artists').textContent=d.artists?.toLocaleString()||'—';
  document.getElementById('st-albums').textContent=d.albums?.toLocaleString()||'—';
  document.getElementById('st-flac').textContent=(d.ext_counts?.['.flac']||0).toLocaleString();
  document.getElementById('st-mp3').textContent=(d.ext_counts?.['.mp3']||0).toLocaleString();
  document.getElementById('st-size').textContent=d.size||'—';
}

// ── TOAST ────────────────────────────────────────────────────
const _tc={success:'#34d399',info:'#67e8f9',warning:'#fbbf24',error:'#f87171'};
function toast(m,lv='info'){
  const t=document.createElement('div');t.className='toast';
  t.innerHTML=`<span class="toast-dot" style="background:${_tc[lv]||'#67e8f9'}"></span><span>${esc(m)}</span>`;
  document.getElementById('toasts').appendChild(t);
  setTimeout(()=>{t.classList.add('out');setTimeout(()=>t.remove(),300);},3500);
}

// ── CONTEXT MENU ─────────────────────────────────────────────
document.addEventListener('click',()=>document.getElementById('ctxMenu').classList.remove('open'));
function ctx(e,items){
  e.preventDefault();const m=document.getElementById('ctxMenu');m.innerHTML='';
  items.forEach(([lbl,fn])=>{
    if(!lbl){const s=document.createElement('div');s.className='ctx-sep';m.appendChild(s);return;}
    const i=document.createElement('div');i.className='ctx-item';i.textContent=lbl;
    if(typeof fn==='function')i.onclick=()=>{fn();m.classList.remove('open');};
    m.appendChild(i);
  });
  m.style.left=Math.min(e.clientX,innerWidth-180)+'px';m.style.top=Math.min(e.clientY,innerHeight-120)+'px';
  m.classList.add('open');
}

// ── TAG EDITOR ───────────────────────────────────────────────
let _tagFiles=[],_tagPath='';
async function loadTagFiles(){
  if(!_folders.length){toast('Add folders first.','warning');return;}
  const d=await fetch('/api/tag-list',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder:_folders[0]})}).then(r=>r.json());
  _tagFiles=d.files||[];
  const list=document.getElementById('tagFileList');
  list.innerHTML=_tagFiles.map((f,i)=>`<div class="tag-file" onclick="selTag(${i})" title="${esc(f.path)}">${esc(f.name)}</div>`).join('');
  toast(`Loaded ${_tagFiles.length} files.`,'info');
}
async function selTag(i){
  document.querySelectorAll('.tag-file').forEach((el,j)=>el.classList.toggle('sel',j===i));
  const f=_tagFiles[i];_tagPath=f.path;
  const t=await fetch('/api/tag-read',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:f.path})}).then(r=>r.json());
  ['title','artist','albumartist','album','tracknumber','date','genre'].forEach(k=>{const el=document.getElementById('t-'+k);if(el)el.value=t[k]||'';});
  document.getElementById('tagFilePath').textContent=f.path;
  document.getElementById('tagForm').style.display='';document.getElementById('tagPlaceholder').style.display='none';
}
async function saveTags(){
  if(!_tagPath){toast('Select a file first.','warning');return;}
  const data={path:_tagPath};
  ['title','artist','albumartist','album','tracknumber','date','genre'].forEach(k=>{const el=document.getElementById('t-'+k);if(el)data[k]=el.value;});
  const r=await fetch('/api/tag-save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}).then(r=>r.json());
  r.ok?toast('Tags saved!','success'):toast('Error: '+r.error,'error');
}

// ── DISCOVER ─────────────────────────────────────────────────
function renderDiscovery(suggestions,provider){
  const wrap=document.getElementById('discoverResults');wrap.innerHTML='';
  if(!suggestions||!suggestions.length){wrap.innerHTML='<div style="color:var(--text3);font-size:12px">No suggestions returned.</div>';return;}
  wrap.innerHTML='<div style="font-size:11px;color:var(--text3);margin-bottom:8px">'+suggestions.length+' suggestions from '+provider+':</div>';
  suggestions.forEach(s=>{
    const d=document.createElement('div');d.className='discover-card';
    d.innerHTML=`
      <div style="flex:1">
        <div style="font-size:13px;font-weight:600;margin-bottom:4px">${esc(s.artist)}</div>
        <div style="font-size:11px;color:var(--text3)">${esc(s.reason)}</div>
        <div class="discover-links" style="margin-top:6px">
          <a href="${s.tidal}" target="_blank">🎵 Tidal</a>
          <a href="${s.qobuz}" target="_blank">🎧 Qobuz</a>
          <a href="${s.mono}" target="_blank">🖤 Monochrome</a>
        </div>
      </div>`;
    wrap.appendChild(d);
  });
  showSection('discover');
}

// ── FIND MORE MUSIC (Spotiflac-like) ────────────────────────────────
async function findMoreMusic(){
  const query = document.getElementById('findMusicSearch').value.trim();
  if(!query){toast('Enter an artist or song name.','warning');return;}
  const resultsDiv = document.getElementById('findMusicResults');
  resultsDiv.innerHTML='<div style="padding:20px;text-align:center;color:var(--text3)">🔍 Searching for "'+esc(query)+'"...</div>';
  
  // Use Spotify/Tidal/Qobuz search URLs (these are the download sources)
  // In a real implementation, you'd call an API. Here we create search links.
  const searchUrl = encodeURIComponent(query);
  
  // Create result cards with download source options
  let html = '';
  html += '<div class="discover-card">';
  html += '  <div style="flex:1">';
  html += '    <div style="font-size:14px;font-weight:600;margin-bottom:4px">🔍 Search Results for: '+esc(query)+'</div>';
  html += '    <div style="font-size:11px;color:var(--text3);margin-top:8px">Select a source to search and download:</div>';
  html += '    <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">';
  html += '      <a href="https://open.spotify.com/search/'+searchUrl+'" target="_blank" class="btn btn-sm" style="background:#1DB954;color:#000;text-decoration:none">🎵 Spotify</a>';
  html += '      <a href="https://listen.tidal.com/search?q='+searchUrl+'" target="_blank" class="btn btn-sm" style="background:#000;color:#fff;text-decoration:none">🎵 Tidal</a>';
  html += '      <a href="https://play.qobuz.com/search?query='+searchUrl+'" target="_blank" class="btn btn-sm" style="background:#fff;color:#000;text-decoration:none">🎧 Qobuz</a>';
  html += '      <a href="https://music.apple.com/search?term='+searchUrl+'" target="_blank" class="btn btn-sm" style="background:#fc3c44;color:#fff;text-decoration:none">🍎 Apple Music</a>';
  html += '      <a href="https://www.deezer.com/search/'+searchUrl+'" target="_blank" class="btn btn-sm" style="background:#A238FF;color:#fff;text-decoration:none">🎧 Deezer</a>';
  html += '    </div>';
  html += '    <div style="font-size:10px;color:var(--text3);margin-top:12px">💡 Tip: Click a source to search. Use these services to find and download new music.</div>';
  html += '  </div>';
  html += '</div>';
  
  resultsDiv.innerHTML = html;
  showSection('discover');
}

// ── DUPLICATES ───────────────────────────────────────────────
function renderDupResults(dups){
  _dupResults=dups;
  const wrap=document.getElementById('dupResults');wrap.innerHTML='';
  if(!dups||!dups.length){wrap.innerHTML='<div style="color:var(--text3)">No duplicates found.</div>';return;}
  document.getElementById('moveDupesBtn').style.display='';
  dups.forEach((g,i)=>{
    const card=document.createElement('div');card.className='dup-card';
    const header=document.createElement('div');header.className='dup-card-header';
    header.innerHTML=`<span>${g.items[0].name.substring(0,30)}...</span><span>${g.count} files</span>`;
    card.appendChild(header);
    g.items.forEach((item,idx)=>{
      const it=document.createElement('div');it.className='dup-item';
      it.dataset.path=item.path;
      it.innerHTML=`<input type="checkbox" class="dup-checkbox"> <span>${item.folder}/${item.name.substring(0,20)}</span>`;
      card.appendChild(it);
    });
    wrap.appendChild(card);
  });
}

// ── GENRE MANAGER ────────────────────────────────────────────
let _selectedGenres=new Set();
async function loadGenres(){
  toast('Scanning genres…','info');
  const d=await fetch('/api/genres',{method:'POST'}).then(r=>r.json());
  const grid=document.getElementById('genreGrid');grid.innerHTML='';
  if(!d.genres||!d.genres.length){grid.innerHTML='<span style="color:var(--text3);font-size:12px">No genre tags found.</span>';return;}
  d.genres.forEach(g=>{
    const p=document.createElement('div');p.className='genre-pill';
    p.innerHTML=`<span>🎭</span><span>${esc(g)}</span>`;
    p.dataset.genre=g;p.onclick=()=>{p.classList.toggle('selected');if(p.classList.contains('selected'))_selectedGenres.add(g);else _selectedGenres.delete(g);};
    grid.appendChild(p);
  });
  toast(`Found ${d.genres.length} genres.`,'success');
}
async function previewGenreRemoval(){
  if(!_selectedGenres.size){toast('Select at least one genre to remove.','warning');return;}
  const s=await fetch('/api/settings').then(r=>r.json());
  const d=await fetch('/api/remove-genres',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({genres:[..._selectedGenres]})}).then(r=>r.json());
  document.getElementById('genrePreview').style.display='';
  document.getElementById('genreCount').textContent=`Will remove: ${d.count} files (protected items excluded)`;
  document.getElementById('genreSample').innerHTML=d.files.map(f=>'<div>'+esc(f)+'</div>').join('');
  document.getElementById('genreRemoveBtn').style.display=d.count>0?'':'none';
}
async function confirmGenreRemoval(){
  const ok=await conf(`⚠️ Permanently DELETE ${document.getElementById('genreCount')?.textContent}?\n\nThis CANNOT be undone!`);
  if(!ok)return;
  fetch('/api/confirm-genre-remove',{method:'POST'});
  showSection('dashboard');
  document.getElementById('genrePreview').style.display='none';
  document.getElementById('genreRemoveBtn').style.display='none';
}

// ── PAIRING ──────────────────────────────────────────────────
let _pairUrl='';
async function loadPairingInfo(){
  const d=await fetch('/api/network-info').then(r=>r.json());
  _pairUrl=d.url;
  document.getElementById('pairUrl').textContent=d.url;
  document.getElementById('pairIp').textContent='LAN IP: '+d.ip+'  ·  Port: '+d.port;
  const btn=document.getElementById('startupBtn');
  if(btn)btn.textContent=d.startup?'✓ Auto-Start Enabled — Disable':'⟳ Enable Auto-Start on Login';
}
function copyPairUrl(){
  navigator.clipboard.writeText(_pairUrl).then(()=>toast('URL copied!','success'));
}
async function toggleStartup(){
  const d=await fetch('/api/network-info').then(r=>r.json());
  const ep=d.startup?'/api/startup-remove':'/api/startup-install';
  const r=await fetch(ep,{method:'POST'}).then(r=>r.json());
  toast(r.message,r.ok?'success':'error');loadPairingInfo();
}

// ─ HELPERS ──────────────────────────────────────────────────
function esc(s){return String(s).replace(/&/g,'&').replace(/</g,'<').replace(/>/g,'>').replace(/"/g,'"')}

// ─ INIT ─────────────────────────────────────────────────────
(async()=>{
  const s=await fetch('/api/settings').then(r=>r.json());
  if(s.accent1)document.getElementById('c-a1').value=s.accent1;
  if(s.accent2)document.getElementById('c-a2').value=s.accent2;
  _chips.ext=s.extensions||['.flac','.mp3'];_chips.excl=s.excluded_folders||[];
  _chips.pa=s.protected_artists||[];_chips.pb=s.protected_albums||[];_chips.ps=s.protected_songs||[];
  applyColors();updatePreview();
  await loadFolders();
  logLine('⚡ Songanizer Pro ready.','success');
  logLine('Add music folders to get started.','info');
  logLine('Access from other devices via Device Pairing (sidebar).','info');
})();
</script>
</body>
</html>
"""


# ════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ════════════════════════════════════════════════════════════════════════
def _local_ip():
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(("8.8.8.8",80)); ip=s.getsockname()[0]; s.close(); return ip
    except Exception: return "127.0.0.1"


def main():
    ip, port = _local_ip(), 5050
    print("=" * 56)
    print("  ⚡  Songanizer Pro")
    print("=" * 56)
    print(f"  Local  :  http://localhost:{port}")
    print(f"  Network:  http://{ip}:{port}  (share with other devices)")
    print("  Press Ctrl+C to stop.")
    print("=" * 56)
    try:
        threading.Thread(target=lambda: (time.sleep(1.2), webbrowser.open(f"http://localhost:{port}")), daemon=True).start()
    except Exception:
        pass  # Browser open optional, don't crash if it fails
    app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
