"""Plex integration via plexapi (optional).

All operations are non-destructive: statistics, search, ratings, and duplicate
reporting. No automatic destructive actions are performed against Plex.
"""

import time

from .. import events
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
        return {"ok": True, **(_section_stats(section))}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _section_stats(section, track_cap=200000):
    """Return {section, tracks, artists, albums} counting Plex's own DB.

    Artists/albums are counted in full; tracks are counted but bounded by
    ``track_cap`` so the call stays responsive on gigantic libraries.
    """
    albums = 0
    tracks = 0
    artists = section.all()
    for a in artists:
        try:
            alb = a.albums()
        except Exception:  # noqa: BLE001
            alb = []
        albums += len(alb)
        for al in alb:
            try:
                tr = al.tracks()
            except Exception:  # noqa: BLE001
                tr = []
            tracks += len(tr)
            if tracks >= track_cap:
                return {
                    "section": getattr(section, "title", ""),
                    "artists": len(artists),
                    "albums": albums,
                    "tracks": tracks,
                    "approximate": True,
                }
    return {
        "section": getattr(section, "title", ""),
        "artists": len(artists),
        "albums": albums,
        "tracks": tracks,
        "approximate": False,
    }


def get_all_music_stats(url, token):
    """Return per-library statistics for every music section on the server (Stage 4 #13)."""
    try:
        server = _connect(url, token)
        sections = [lib for lib in server.library.sections() if lib.type == "artist"]
        out = [{"name": lib.title, **(_section_stats(lib))}
               for lib in sections]
        return {"ok": True, "libraries": out, "count": len(out)}
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


def test_connection(url, token):
    """Validate a Plex connection with the given (possibly not-yet-saved)
    credentials. Thin wrapper so the API can test before the user applies
    settings. Returns the same shape as ``get_status``."""
    return get_status(url, token)


def get_sections(url, token):
    """List every Plex library section plus its on-disk folder locations.

    Used by the "load Plex folders" feature: given a server URL + token we can
    enumerate the sections and their real folder paths, so Glacier can add them
    as managed libraries without manually browsing the mount.
    """
    try:
        server = _connect(url, token)
        out = []
        for lib in server.library.sections():
            locations = []
            try:
                for loc in lib.locations:
                    locations.append(getattr(loc, "path", None))
            except Exception:  # noqa: BLE001
                locations = []
            out.append({
                "name": lib.title,
                "type": lib.type,
                "key": getattr(lib, "key", None),
                "count": (lib.totalSize
                          if getattr(lib, "totalSize", None) is not None else None),
                "locations": [p for p in locations if p],
            })
        return {"ok": True, "sections": out, "count": len(out)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def export_library(url, token, section_name, limit=200000):
    """Pull full metadata for a Plex music section into a JSON list.

    Each record carries the fields Glacier + the user care about (artist, album,
    title, track, year, duration, rating, genre), so the data can be exported /
    analysed outside Plex without needing Portainer or the Plex UI.
    """
    try:
        server = _connect(url, token)
        section = _music_section(server, section_name)
        if section is None:
            return {"ok": False, "error": "No music section found"}
        artists = section.all()
        total_artists = len(artists)
        out = []
        for ai, artist in enumerate(artists):
            try:
                albums = artist.albums()
            except Exception:  # noqa: BLE001
                albums = []
            for alb in albums:
                try:
                    tracks = alb.tracks()
                except Exception:  # noqa: BLE001
                    tracks = []
                for t in tracks:
                    genres = []
                    try:
                        genres = [g.tag for g in (t.genres or [])]
                    except Exception:  # noqa: BLE001
                        genres = []
                    out.append({
                        "artist": (getattr(t, "grandparentTitle", None)
                                   or getattr(t, "artist", None)
                                   or getattr(artist, "title", None) or ""),
                        "album": getattr(alb, "title", None) or "",
                        "title": getattr(t, "title", None) or "",
                        "track": getattr(t, "index", None),
                        "year": getattr(t, "year", None) or getattr(alb, "year", None),
                        "duration_ms": getattr(t, "duration", None),
                        "rating": getattr(t, "userRating", None),
                        "genre": genres,
                        "key": getattr(t, "key", None),
                    })
            if len(out) >= limit:
                break
            if ai % 5 == 0 or ai == total_artists - 1:
                events.progress(ai + 1, total_artists,
                                f"Exporting {getattr(section, 'title', section_name)}")
        events.log(
            f"Plex export pulled {len(out)} track(s) from "
            f"'{getattr(section, 'title', section_name)}'", "success")
        return {
            "ok": True,
            "section": getattr(section, "title", section_name),
            "artists": total_artists,
            "count": len(out),
            "tracks": out,
            "exported_at": time.time(),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
