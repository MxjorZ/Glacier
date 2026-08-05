"""Glacier backend configuration constants and default settings.

These defaults are used when no settings file exists yet. All paths are
user-defined at runtime; nothing here hardcodes a music library location.
"""

from pathlib import Path
import os
import socket

APP_NAME = "Glacier"
APP_VERSION = "1.0.0"

# Host / port used by the Flask dev server wrapper (glacier.py).
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5050

# Where persistent settings are stored on disk.
SETTINGS_PATH = Path.home() / ".glacier_settings.json"

# Stage 4: persistent global error center + recent operations history.
ERRORS_PATH = Path.home() / ".glacier_errors.json"
OPERATIONS_PATH = Path.home() / ".glacier_operations.json"

# Audio file extensions Glacier knows how to read metadata for.
SUPPORTED_EXTENSIONS = [".flac", ".mp3", ".ogg", ".m4a", ".opus", ".wma"]

# Excluded folder names by default (matched by exact lowercase name).
DEFAULT_EXCLUDED_FOLDERS = ["playlists", "- playlists", ".thumbnails", "@eadir"]

DEFAULT_FOLDER_PATTERN = "{albumartist}/{album} ({year})"
DEFAULT_NAMING_PATTERN = "{artist} - {album} - {track:02d} - {title}"

# Identity matching priority for cross-library exclusivity (flag based).
EXCLUSIVITY_AUTO = "auto"          # use the first identity level that matches
EXCLUSIVITY_ISRC = "isrc"
EXCLUSIVITY_AT_A = "artist_title_album"
EXCLUSIVITY_AT = "artist_title"

# Resolution policies for exclusivity violations.
POLICY_REPORT_ONLY = "report_only"
POLICY_KEEP_BEST_QUALITY = "keep_best_quality"
POLICY_KEEP_PREFERRED_LIBRARY = "keep_preferred_library"
POLICY_KEEP_NEWEST = "keep_newest"
POLICY_MOVE_TO_LIBRARY = "move_to_library"
POLICY_QUARANTINE = "quarantine"

# Artist exclusivity resolution policies (Stage 2).
ARTIST_POLICY_REPORT_ONLY = "report_only"
ARTIST_POLICY_KEEP_PREFERRED_LIBRARY = "keep_preferred_library"

# Quality ordering used to decide "best" format (higher is better).
QUALITY_RANK = {
    "flac": 100,
    "wav": 95,
    "ape": 90,
    "alac": 85,
    "m4a": 60,
    "ogg": 65,
    "opus": 70,
    "wma": 50,
    "mp3": 40,
    "aac": 45,
}

DEFAULT_SETTINGS = {
    "server": {
        "host": DEFAULT_HOST,
        "port": DEFAULT_PORT,
    },
    "libraries": [],
    "extensions": [".flac", ".mp3"],
    "excluded_folders": list(DEFAULT_EXCLUDED_FOLDERS),
    "folder_pattern": DEFAULT_FOLDER_PATTERN,
    "naming_pattern": DEFAULT_NAMING_PATTERN,
    "dup_priority": "flac",
    "exclusivity": {
        "identity": EXCLUSIVITY_AUTO,
        "default_policy": POLICY_REPORT_ONLY,
        "preferred_library_id": "",
    },
    # Top-level exclusivity policy for Stage 2 artist exclusivity.
    "exclusivity_artist_policy": ARTIST_POLICY_REPORT_ONLY,
    "artist_exclusivity_exceptions": [],
    "preferred_library_id": None,
    "backup_before_move": False,
    "plex": {
        "url": "",
        "token": "",
        "music_section": "Music",
        # Stage 2: Plex star ratings -> local tag rating sync.
        "rating_sync_enabled": False,
        "rating_sync_interval_sec": 600,
        "rating_overwrite": False,
        "last_rating_sync": None,
        "last_rating_sync_result": None,
    },
    # Stage 2: sounds on completed activity.
    "sound_on_complete": True,
    "sound_on_error": False,
    "sound_asset_complete": "sounds/job-done.wav",
    # Stage 2: theme incl. AMOLED + custom accent.
    "theme": {
        "mode": "dark",          # light | dark | amoled | auto
        "accent": "cyan",        # preset name or "custom"
        "accent_custom": None,   # hex "#RRGGBB" / "#RGB" or "r,g,b"
    },
    # Stage 4 (#16): Enhanced UI animations.
    "animations": {
        "preset": "modern",         # minimal | modern | material | smooth | fast | playful
        "page_transitions": True,   # fade/slide between pages
        "hover": True,
        "click": True,
        "duration_ms": 220,
        "easing": "ease-out",
    },
}

# Server identity exposed to the UI (LAN IP / hostname).
def detect_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"
