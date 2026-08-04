"""In-library duplicate detection.

Detects tracks that share the same identity *within a single library*, as
distinct from cross-library exclusivity violations. Uses the same identity
normalization defined in ``exclusivity``.
"""

from . import exclusivity


def detect_inventory(tracks, identity_mode, fallback_filename=True):
    """Return duplicate groups within one library's inventory.

    Each group lists tracks sharing a normalized identity. Groups with a single
    track are omitted.
    """
    groups = {}
    for tr in tracks:
        if tr.get("error"):
            continue
        ident = exclusivity.choose_identity(
            tr.get("tags", {}), identity_mode,
            tr["path"] if fallback_filename else None)
        if not ident:
            continue
        groups.setdefault(ident, []).append(tr)

    result = []
    for ident, group_tracks in groups.items():
        if len(group_tracks) > 1:
            result.append({
                "identity": ident,
                "tracks": group_tracks,
                "count": len(group_tracks),
            })
    return result
