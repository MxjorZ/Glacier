"""Tag editing operations on top of the metadata reader/writer.

These map directly to the /api/tag-list, /api/tag-read, /api/tag-save routes.
"""

import os

from .. import events
from ..cancel import is_cancelled, JobCancelled
from ..library import metadata

CANONICAL_FIELDS = ["artist", "albumartist", "album", "title", "track", "date", "genre", "isrc", "rating"]


def list_capable(paths):
    """Return which paths are editable (supported format, exists)."""
    out = []
    for p in paths:
        if not os.path.exists(p):
            out.append({"path": p, "ok": False, "reason": "missing"})
            continue
        _, fmt = metadata.resolve(p)
        out.append({"path": p, "ok": fmt is not None,
                    "reason": None if fmt else "unsupported_format", "format": fmt})
    return out


def read_batch(paths):
    """Read canonical tags for a batch of files."""
    results = []
    for p in paths:
        rec = metadata.read(p)
        results.append({
            "path": p,
            "format": rec.get("format"),
            "tags": rec.get("tags", {}),
            "error": rec.get("error"),
        })
    return results


def apply(paths, field, value):
    """Set one canonical field across many files. Returns (ok, applied, errors)."""
    applied = 0
    errors = []
    for i, p in enumerate(paths):
        if is_cancelled():
            raise JobCancelled()
        res = metadata.write(p, {field: value})
        if res.get("ok"):
            applied += 1
        else:
            errors.append({"path": p, "error": res.get("error")})
        if (i + 1) % 25 == 0 or i + 1 == len(paths):
            events.progress(i + 1, len(paths), f"Tagging {field}")
    return applied, errors
