"""Organizer – uses the simple mover engine."""

from ..mover import plan_files, execute_plan
from .. import events


def plan_library(tracks, root, folder_pattern, naming_pattern):
    """Build a move plan from an inventory (compatibility with existing API)."""
    file_paths = [t['path'] for t in tracks if not t.get('error')]
    return plan_files(file_paths, folder_pattern, naming_pattern, root)


def apply_plan(plan, root, backup=False):
    """Execute a plan (compatibility)."""
    moved, errors = execute_plan(plan, dry_run=False, backup=backup)
    return moved, errors