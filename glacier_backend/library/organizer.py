"""Organizer — the single home of pattern preview, planning and apply.

Wraps the mover engine: build a move plan from an inventory, execute it, and
render a live preview path for the pattern editor (``/api/preview-path``).
"""

import os

from ..mover import plan_files, execute_plan, render_pattern, unknown_tokens


def preview_path(folder_pattern, naming_pattern, sample_tags, root=None,
                ext=".flac"):
    """Render a sample destination path for the given patterns + tags.

    Returns {relative_path, full_path, unknown_tokens} — ``unknown_tokens``
    lists pattern placeholders that can never be filled from tags, so the UI
    can flag typos like ``{albulm}`` before an organize run.
    """
    folder = render_pattern(folder_pattern or "", sample_tags or {})
    base = render_pattern(naming_pattern or "", sample_tags or {})
    rel = os.path.join(folder, base + (ext or ".flac"))
    full = os.path.join(root, rel) if root else None
    unknown = unknown_tokens(folder_pattern or "") + unknown_tokens(naming_pattern or "")
    return {"relative_path": rel, "full_path": full,
            "unknown_tokens": unknown}


def plan_library(tracks, root, folder_pattern, naming_pattern):
    """Build a move plan from an inventory (compatibility with existing API)."""
    file_paths = [t['path'] for t in tracks if not t.get('error')]
    return plan_files(file_paths, folder_pattern, naming_pattern, root)


def apply_plan(plan, root, backup=False, copy=False):
    """Execute a plan (compatibility)."""
    moved, errors = execute_plan(plan, dry_run=False, backup=backup, copy=copy)
    return moved, errors
