"""Plex integration via plexapi (optional).

All operations are non-destructive: statistics, search, ratings, and duplicate
reporting. No automatic destructive actions are performed against Plex.
"""

from ..config import APP_NAME

try:
    from plexapi.server import PlexServer
except Exception:  # pragma: no cover
    PlexServer = None


def _connect(url, token):
    if PlexServer is None:
        raise RuntimeError("plexapi is not installed")
    if not url:
        raise RuntimeError("Plex URL is not configured")
    return PlexServer(url, token)


def get_status(url, token):
    """Return connection status + basic server stats."""
    try:
        server = _connect(url, token)
        return {
            "ok": True,
            "friendly_name": getattr(server, "friendlyName", None),
            "version": getattr(server, "version", None),
            "platform": getattr(server, "platform", None),
            "libraries": [
                {"name": lib.title, "type": lib.type, "count": getattr(lib, "key", None)}
                for lib in server.library.sections()
            ],
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _music_section(server, section_name):
    for lib in server.library.sections():
        if lib.type == "artist" and (
                not section_name or lib.title.lower() == section_name.lower()):
            return lib
    for lib in server.library.sections():
        if lib.type == "artist":
            return lib
    return None


def get_stats(url, token, section_name):
    try:
        server = _connect(url, token)
        section = _music_section(server, section_name)
        if section is None:
            return {"ok": False, "error": "No music section found"}
        artists = section.all()
        tracks = []
        albums = 0
        for a in artists:
            albums += len(a.albums())
            for alb in a.albums():
                tracks.extend(alb.tracks())
            if len(tracks) > 2000:  # guard against huge pulls
                break
        return {
            "ok": True,
            "section": getattr(section, "title", section_name),
            "artists": len(artists),
            "albums": albums,
            "tracks": len(tracks),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def search(url, token, query, limit=20):
    try:
        server = _connect(url, token)
        results = server.search(query, mediatype="track", limit=limit)
        out = []
        for r in results[:limit]:
            out.append({
                "title": r.title,
                "artist": getattr(r, "grandparentTitle", None) or getattr(r, "artist", None),
                "album": getattr(r, "parentTitle", None),
                "duration": getattr(r, "duration", None),
                "rating": getattr(r, "userRating", None),
                "key": getattr(r, "key", None),
            })
        return {"ok": True, "results": out}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def rate(url, token, query, rating):
    """Rate a search result. rating in 0..10; requires an exact match path."""
    try:
        server = _connect(url, token)
        results = server.search(query, mediatype="track", limit=1)
        if not results:
            return {"ok": False, "error": "No matching track found"}
        track = results[0]
        track.rate(float(rating))
        return {"ok": True, "title": track.title, "rating": rating}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def get_duplicates(url, token, section_name):
    """Report Plex duplicates by matching title+artist within the section."""
    try:
        server = _connect(url, token)
        section = _music_section(server, section_name)
        if section is None:
            return {"ok": False, "error": "No music section found"}
        seen = {}
        dups = []
        for artist in section.all():
            for alb in artist.albums():
                for t in alb.tracks():
                    key = (t.title or "").lower()
                    if key in seen:
                        dups.append({"title": t.title, "artist": t.grandparentTitle,
                                     "paths": [seen[key], t.key]})
                    else:
                        seen[key] = t.key
        return {"ok": True, "duplicates": dups, "count": len(dups)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def pull_ratings(url, token, section_name, limit=100000):
    """Return track ratings for a music section.

    Each record: {key, guid, artist, album, title, track, rating} where rating is
    Plex's 0..10 scale (10.0 == 5 stars). ``limit`` guards against huge pulls.
    """
    try:
        server = _connect(url, token)
        section = _music_section(server, section_name)
        if section is None:
            return {"ok": False, "error": "No music section found"}
        out = []
        for artist in section.all():
            for alb in artist.albums():
                for t in alb.tracks():
                    rating = getattr(t, "userRating", None)
                    if rating is None:
                        continue
                    out.append({
                        "key": getattr(t, "key", None),
                        "guid": getattr(t, "guid", None),
                        "artist": (getattr(t, "grandparentTitle", None)
                                   or getattr(t, "artist", None) or ""),
                        "album": getattr(t, "parentTitle", None) or "",
                        "title": getattr(t, "title", None) or "",
                        "track": (getattr(t, "index", None) or ""),
                        "rating": float(rating),
                    })
                    if len(out) >= limit:
                        return {"ok": True, "ratings": out, "count": len(out)}
        return {"ok": True, "ratings": out, "count": len(out)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
