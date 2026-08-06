"""Extract to new library – uses the simple mover engine."""

import os
import shutil

from ..mover import read_tags, sanitize
from .exclusivity import normalize
from .. import events
from ..cancel import is_cancelled, JobCancelled


def matches(tags, path, filters):
    """Return True if a track matches all supplied filters (AND)."""
    filters = filters or {}
    if filters.get('script'):
        # script filtering not implemented in mover – keep existing logic
        # we can re-use the script detection from the old extract if needed
        # but for simplicity we'll skip script filters
        pass
    if filters.get('genre_contains'):
        genre = tags.get('genre') or ''
        if filters['genre_contains'].lower() not in str(genre).lower():
            return False
    if filters.get('artists'):
        wanted = {normalize(a) for a in filters['artists']}
        artist = normalize(tags.get('artist') or tags.get('albumartist') or '')
        if not wanted or artist not in wanted:
            return False
    if filters.get('path_regex'):
        try:
            if not re.search(filters['path_regex'], path or ''):
                return False
        except re.error:
            return False
    for kind in ('tag_equals', 'tag_contains'):
        spec = filters.get(kind)
        if spec:
            for field, value in spec.items():
                if field not in tags:
                    return False
                actual = str(tags.get(field) or '')
                if kind == 'tag_equals' and actual != str(value):
                    return False
                if kind == 'tag_contains' and str(value) not in actual:
                    return False
    return True


def plan_extract(inventories, filters, target_path):
    """Build a move plan for extraction (compatibility)."""
    plan = []
    for lib_id, info in inventories.items():
        for tr in info.get('tracks', []):
            if tr.get('error'):
                continue
            if not matches(tr.get('tags', {}), tr.get('path'), filters):
                continue
            src = tr['path']
            dest = os.path.join(target_path, os.path.basename(src))
            # Avoid overwrite
            base, ext = os.path.splitext(dest)
            i = 1
            while os.path.exists(dest):
                dest = f"{base} ({i}){ext}"
                i += 1
            plan.append({
                'source': src,
                'destination': dest,
                'source_library_id': lib_id,
                'source_library_name': info.get('name', ''),
                'size': tr.get('size', 0),
            })
    return plan


def execute_extract(plan, target_path):
    """Execute the extraction plan (uses mover)."""
    os.makedirs(target_path, exist_ok=True)
    moved = 0
    errors = []
    for i, item in enumerate(plan):
        if is_cancelled():
            raise JobCancelled()
        try:
            src = item['source']
            dest = item['destination']
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(src, dest)
            moved += 1
            events.log(f"Extracted: {src} -> {dest}", "success")
        except Exception as e:
            errors.append({"source": item['source'], "error": str(e)})
        if (i + 1) % 25 == 0:
            events.progress(i + 1, len(plan), "Moving files into new library")
    if plan:
        events.progress(len(plan), len(plan), "Moving files into new library")
    return moved, errors