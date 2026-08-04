"""Library Exclusivity engine.

This is Glacier's signature feature: a track identity should exist in only one
managed library. Tracks are grouped by a normalized identity and, when the same
identity appears in more than one library, an exclusivity violation is recorded.

Identity priority (used for matching):
    1. ISRC
    2. Artist + Title + Album
    3. Artist + Title
    4. Filename fallback (report only)

Resolution is always non-destructive by default (report_only). Destructive /
moving policies require an explicit dry-run + confirmation in the API layer.
"""

import os
import re
import shutil

from ..config import (
    EXCLUSIVITY_AUTO, EXCLUSIVITY_ISRC, EXCLUSIVITY_AT_A, EXCLUSIVITY_AT,
    POLICY_REPORT_ONLY, POLICY_KEEP_BEST_QUALITY, POLICY_KEEP_PREFERRED_LIBRARY,
    POLICY_KEEP_NEWEST, POLICY_MOVE_TO_LIBRARY, POLICY_QUARANTINE,
    QUALITY_RANK,
)

_FEAT_RE = re.compile(r"([\s\-]?(feat\.?|ft\.?|featuring|with)[\s\-]?.*)$", re.I)
_PUNCT_RE = re.compile(r"[\W_]+")


def normalize(value):
    """Normalize a text value for identity matching."""
    if not value:
        return ""
    s = str(value).lower()
    s = _FEAT_RE.sub("", s)          # remove feat/ft noise
    s = _PUNCT_RE.sub(" ", s)        # remove punctuation
    s = re.sub(r"\s+", " ", s).strip()  # collapse spaces
    return s


def identity(tags, mode, filename=None):
    """Compute identity levels for a track's tags.

    Returns a dict with each level key present when computable:
    {isrc, artist_title_album, artist_title, filename}
    """
    artist = normalize(tags.get("artist"))
    title = normalize(tags.get("title"))
    album = normalize(tags.get("album"))
    isrc = normalize(tags.get("isrc"))
    ident = {
        "isrc": f"isrc:{isrc}" if isrc else "",
        "artist_title_album": f"{artist}|{title}|{album}" if artist and title and album else "",
        "artist_title": f"{artist}|{title}" if artist and title else "",
    }
    if filename:
        base = os.path.splitext(os.path.basename(filename))[0]
        ident["filename"] = "file:" + normalize(base)
    return ident


def choose_identity(tags, mode, filename=None):
    """Return the strongest available identity string for a track."""
    ident = identity(tags, mode, filename)
    ordering = {
        EXCLUSIVITY_ISRC: ["isrc", "artist_title_album", "artist_title", "filename"],
        EXCLUSIVITY_AT_A: ["artist_title_album", "artist_title", "filename"],
        EXCLUSIVITY_AT: ["artist_title", "filename"],
        EXCLUSIVITY_AUTO: ["isrc", "artist_title_album", "artist_title", "filename"],
    }
    seq = ordering.get(mode, ordering[EXCLUSIVITY_AUTO])
    for key in seq:
        if ident.get(key):
            return ident[key]
    return filename or ""


def _quality(track):
    fmt = (track.get("format") or "").lower()
    return QUALITY_RANK.get(fmt, 0)


def scan_violations(inventories, identity_mode, preferred_library_id=None,
                    fallback_filename=True):
    """Group tracks by identity and return exclusivity violations.

    ``inventories`` is a mapping {library_id: [track, ...]}. Returns a list of
    violation groups; each group contains tracks with the same identity that
    span more than one library.
    """
    groups = {}
    for lib_id, tracks in inventories.items():
        for tr in tracks:
            if tr.get("error"):
                continue
            tags = tr.get("tags", {})
            ident = choose_identity(tags, identity_mode, tr["path"] if fallback_filename else None)
            if not ident:
                continue
            groups.setdefault(ident, []).append(tr)

    violations = []
    for ident, tracks in groups.items():
        lib_set = {t["library_id"] for t in tracks}
        if len(lib_set) > 1:
            violations.append({
                "identity": ident,
                "tracks": tracks,
                "libraries": sorted(lib_set),
                "count": len(tracks),
            })
    return violations


def resolve_group(group, policy, preferred_library_id, move_target_library_id=None):
    """Decide an action for one violation group (without performing it).

    Returns: {"identity", "keep": [...], "remove": [...], "action": str}
    """
    tracks = group["tracks"]
    if policy in (POLICY_REPORT_ONLY,):
        return {"identity": group["identity"], "keep": tracks, "remove": [],
                "action": "report_only",
                "note": "No action; violation reported only."}

    if policy == POLICY_KEEP_BEST_QUALITY:
        best = max(tracks, key=lambda t: (_quality(t), t.get("bitrate") or 0, t.get("size") or 0))
        keep = [best]
        remove = [t for t in tracks if t is not best]
        return {"identity": group["identity"], "keep": keep, "remove": remove,
                "action": "keep_best_quality"}

    if policy == POLICY_KEEP_PREFERRED_LIBRARY:
        if preferred_library_id:
            preferred = [t for t in tracks if t["library_id"] == preferred_library_id]
            if preferred:
                keep = preferred
                remove = [t for t in tracks if t not in preferred]
                return {"identity": group["identity"], "keep": keep,
                        "remove": remove, "action": "keep_preferred_library"}
        best = max(tracks, key=lambda t: (_quality(t), t.get("bitrate") or 0))
        keep = [best]
        remove = [t for t in tracks if t is not best]
        return {"identity": group["identity"], "keep": keep, "remove": remove,
                "action": "keep_preferred_library"}

    if policy == POLICY_KEEP_NEWEST:
        best = max(tracks, key=lambda t: t.get("mtime") or 0)
        keep = [best]
        remove = [t for t in tracks if t is not best]
        return {"identity": group["identity"], "keep": keep, "remove": remove,
                "action": "keep_newest"}

    if policy == POLICY_MOVE_TO_LIBRARY:
        if move_target_library_id:
            already = [t for t in tracks if t["library_id"] == move_target_library_id]
            if already:
                keep = already
                remove = [t for t in tracks if t not in already]
            else:
                keep = []
                remove = tracks
            return {"identity": group["identity"], "keep": keep, "remove": remove,
                    "action": "move_to_library",
                    "target_library": move_target_library_id}
        return {"identity": group["identity"], "keep": tracks, "remove": [],
                "action": "report_only",
                "note": "move_to_library requires a target library."}

    if policy == POLICY_QUARANTINE:
        return {"identity": group["identity"], "keep": [], "remove": tracks,
                "action": "quarantine"}

    return {"identity": group["identity"], "keep": tracks, "remove": [],
            "action": "report_only", "note": "Unknown policy."}


def execute_removal(track, policy, quarantine_dir=None, move_dir=None):
    """Physically act on a 'remove' track according to policy.

    Only called after explicit confirmation/dry-run. Returns (ok, detail).
    """
    path = track.get("path")
    if not path or not os.path.exists(path):
        return False, "already missing"
    if policy == POLICY_QUARANTINE and quarantine_dir:
        dest_dir = quarantine_dir
    elif policy == POLICY_MOVE_TO_LIBRARY and move_dir:
        dest_dir = move_dir
    else:
        return False, "no-op (policy does not act)"

    try:
        dest_dir = os.path.abspath(dest_dir)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, os.path.basename(path))
        dest = _unique_path(dest)
        shutil.move(path, dest)
        return True, "moved to " + dest
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _unique_path(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(f"{base} ({i}){ext}"):
        i += 1
    return f"{base} ({i}){ext}"


# --- Artist exclusivity (Stage 2) ---------------------------------------

def normalize_artist(name):
    return normalize(name or "")


def scan_artist_violations(inventories, exceptions=None):
    """Group tracks by normalized artist and return violations (artist present
    in more than one library).

    ``inventories`` is {library_id: [track, ...]}. ``exceptions`` is a list of
    normalized artist names allowed in multiple libraries. Returns a list of
    group dicts with artist, display, libraries[] and tracks[].
    """
    exceptions = {normalize_artist(x) for x in (exceptions or [])}
    by_artist = {}
    for lib_id, tracks in inventories.items():
        for tr in tracks:
            if tr.get("error"):
                continue
            tags = tr.get("tags", {})
            artist = normalize_artist(tags.get("artist") or tags.get("albumartist"))
            if not artist or artist in exceptions:
                continue
            rec = dict(tr)
            rec["artist_name"] = (tags.get("artist")
                                  or tags.get("albumartist") or artist)
            by_artist.setdefault(artist, []).append(rec)

    groups = []
    for artist, tracks in by_artist.items():
        lib_ids = {t["library_id"] for t in tracks if t.get("library_id")}
        if len(lib_ids) > 1:
            display = max((t["artist_name"] for t in tracks), key=len)
            lib_map = {}
            for t in tracks:
                lid = t.get("library_id")
                lib_map.setdefault(lid, 0)
                lib_map[lid] += 1
            groups.append({
                "artist": artist,
                "display": display,
                "libraries": [{"library_id": lid, "count": c}
                              for lid, c in sorted(lib_map.items())],
                "tracks": tracks,
            })
    return groups


def resolve_artist_groups(groups, policy, preferred_library_id=None):
    """Build keep/remove plans for artist exclusivity violations.

    ``keep_preferred_library`` keeps all of the artist's tracks in the
    preferred library and marks the rest as remove (to be moved). Always returns
    non-destructive plans; actual moves are performed by the caller with
    explicit confirmation.
    """
    plans = []
    for group in groups:
        if policy == "keep_preferred_library" and preferred_library_id:
            keep = [t for t in group["tracks"]
                    if t.get("library_id") == preferred_library_id]
            remove = [t for t in group["tracks"]
                      if t.get("library_id") != preferred_library_id]
            action = "keep_preferred_library"
        else:
            keep = group["tracks"]
            remove = []
            action = "report_only"
        plans.append({
            "artist": group["artist"],
            "display": group["display"],
            "action": action,
            "target_library": preferred_library_id if action == "keep_preferred_library" else None,
            "keep": keep,
            "remove": remove,
        })
    return plans

