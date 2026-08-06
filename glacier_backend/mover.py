"""Simple, reliable file mover for Glacier.

Reads metadata, applies user‑defined folder and filename patterns,
and moves files safely with dry‑run and logging.
"""

import os
import re
import shutil
from typing import Dict, List, Tuple

from mutagen import File

from . import events


# --- Tag reading ---------------------------------------------------------

def read_tags(path: str) -> Dict[str, str]:
    """Read canonical tags from a supported audio file."""
    tags = {}
    try:
        audio = File(path)
        if audio is None:
            return tags
        # FLAC / generic
        if hasattr(audio, 'get'):
            for key in ('artist', 'albumartist', 'album', 'title', 'tracknumber', 'date', 'genre'):
                val = audio.get(key, [''])[0] if audio.get(key) else ''
                tags[key] = str(val)
            # year fallback
            if not tags.get('date'):
                tags['date'] = audio.get('year', [''])[0] or ''
        # MP3 via EasyID3
        elif hasattr(audio, 'get'):
            # already handled
            pass
        else:
            # fallback: mutagen.File
            audio = File(path)
            if audio and hasattr(audio, 'get'):
                for key in ('artist', 'albumartist', 'album', 'title', 'tracknumber', 'date', 'genre'):
                    val = audio.get(key, [''])[0] if audio.get(key) else ''
                    tags[key] = str(val)
    except Exception as e:
        events.log(f"Failed to read tags from {path}: {e}", "warning")
    # Normalise track number: extract first number
    if 'tracknumber' in tags:
        m = re.search(r'\d+', tags['tracknumber'])
        tags['tracknumber'] = m.group(0) if m else ''
    return tags


# --- Path rendering ------------------------------------------------------

def sanitize(name: str, fallback: str = "Unknown") -> str:
    """Clean a string for filesystem use."""
    if not name or not name.strip():
        return fallback
    # Remove illegal characters
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    return name.strip()


def render_pattern(pattern: str, tags: Dict[str, str]) -> str:
    """Replace {field} placeholders with tag values."""
    def repl(match):
        field = match.group(1)
        # Handle albumartist fallback to artist
        if field == 'albumartist':
            val = tags.get('albumartist') or tags.get('artist') or ''
        else:
            val = tags.get(field, '')
        return sanitize(str(val))
    return re.sub(r'\{([^}]+)\}', repl, pattern)


# --- Move planning -------------------------------------------------------

def plan_files(file_paths: List[str], folder_pattern: str, filename_pattern: str,
               library_root: str) -> List[Dict]:
    """Build a move plan for a list of files.

    Returns list of dicts with source, destination, and metadata.
    """
    plan = []
    for src in file_paths:
        if not os.path.isfile(src):
            continue
        tags = read_tags(src)
        # Build destination folder
        folder = render_pattern(folder_pattern, tags)
        # Build filename
        base = render_pattern(filename_pattern, tags)
        ext = os.path.splitext(src)[1]
        # Add track number if missing from pattern but available
        if '{track}' not in filename_pattern and tags.get('tracknumber'):
            base = f"{base} - {tags['tracknumber']}"
        new_name = base + ext
        dest = os.path.join(library_root, folder, new_name)
        plan.append({
            'source': src,
            'destination': dest,
            'tags': tags,
        })
    return plan


def execute_plan(plan: List[Dict], dry_run: bool = True, backup: bool = False) -> Tuple[int, List[str]]:
    """Execute a move plan. Returns (moved_count, errors)."""
    moved = 0
    errors = []
    for item in plan:
        src = item['source']
        dest = item['destination']
        if dry_run:
            events.log(f"[DRY] Would move: {src} -> {dest}", "verbose")
            moved += 1
            continue
        try:
            # Safety: prevent moving into itself
            if os.path.abspath(src) == os.path.abspath(dest):
                events.log(f"Skipping: source equals destination {src}", "warning")
                continue
            # Create destination folder
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            # Optional backup
            if backup and os.path.exists(src):
                bak = src + ".bak"
                shutil.copy2(src, bak)
            # Move
            shutil.move(src, dest)
            moved += 1
            events.log(f"Moved: {src} -> {dest}", "success")
        except Exception as e:
            errors.append(f"{src} -> {dest}: {e}")
            events.log(f"Error moving {src}: {e}", "error")
    return moved, errors


def move_files(file_paths: List[str], folder_pattern: str, filename_pattern: str,
               library_root: str, dry_run: bool = True, backup: bool = False) -> Tuple[int, List[str]]:
    """High‑level wrapper: plan and execute in one call."""
    plan = plan_files(file_paths, folder_pattern, filename_pattern, library_root)
    return execute_plan(plan, dry_run, backup)