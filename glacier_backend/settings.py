"""Persistent settings management.

Settings are stored as JSON at ``~/.glacier_settings.json`` and are loaded at
startup, surviving restarts. A module-level ``Store`` singleton is provided for
use by route handlers.
"""

import json
import copy
import threading
import uuid
from pathlib import Path

from . import config


def _normalize(raw):
    """Merge raw loaded settings over the defaults recursively."""
    merged = copy.deepcopy(config.DEFAULT_SETTINGS)
    # <-- ADD THIS AFTER merged is defined
    merged.setdefault("startup_scan_enabled", False)
    if not isinstance(raw, dict):
        return merged

    def deep_merge(base, patch):
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                deep_merge(base[key], value)
            else:
                base[key] = value

    deep_merge(merged, raw)

    # Guard invariants
    if not isinstance(merged["libraries"], list):
        merged["libraries"] = []
    for lib in merged["libraries"]:
        lib.setdefault("id", uuid.uuid4().hex[:8])
        lib.setdefault("name", "Library")
        lib.setdefault("path", "")
        lib.setdefault("scan", None)
        # Active vs disabled (Stage 3): disabled libraries are excluded from
        # "all-library" scans/operations but keep their files on disk.
        lib.setdefault("enabled", True)
    if not isinstance(merged["extensions"], list) or not merged["extensions"]:
        merged["extensions"] = [".flac", ".mp3"]
    for ext in merged["extensions"]:
        if not ext.startswith("."):
            merged["extensions"][merged["extensions"].index(ext)] = "." + ext

    # Stage 2 keys — tolerant upgrades from older settings files.
    merged["exclusivity_artist_policy"] = merged.get(
        "exclusivity_artist_policy", config.ARTIST_POLICY_REPORT_ONLY)
    if not isinstance(merged.get("artist_exclusivity_exceptions"), list):
        merged["artist_exclusivity_exceptions"] = []
    merged["preferred_library_id"] = merged.get("preferred_library_id") or None

    merged["sound_on_complete"] = bool(merged.get("sound_on_complete", True))
    merged["sound_on_error"] = bool(merged.get("sound_on_error", False))
    merged["sound_asset_complete"] = merged.get("sound_asset_complete",
                                                "sounds/job-done.wav")

    plex = merged.setdefault("plex", {})
    plex.setdefault("rating_sync_enabled", False)
    plex.setdefault("rating_sync_interval_sec", 600)
    plex.setdefault("rating_overwrite", False)
    plex.setdefault("last_rating_sync", None)
    plex.setdefault("last_rating_sync_result", None)
    try:
        plex["rating_sync_interval_sec"] = max(
            60, int(plex.get("rating_sync_interval_sec") or 600))
    except (TypeError, ValueError):
        plex["rating_sync_interval_sec"] = 600

    theme = merged.setdefault("theme", {})
    theme.setdefault("mode", "dark")
    theme.setdefault("accent", "cyan")
    theme.setdefault("accent_custom", None)
    if theme.get("mode") not in ("light", "dark", "amoled", "auto"):
        theme["mode"] = "dark"

    # Stage 4 (#16): animation settings (tolerant upgrades).
    anim = merged.setdefault("animations", {})
    anim.setdefault("preset", "modern")
    anim.setdefault("page_transitions", True)
    anim.setdefault("hover", True)
    anim.setdefault("click", True)
    anim.setdefault("duration_ms", 220)
    anim.setdefault("easing", "ease-out")
    try:
        anim["duration_ms"] = max(50, min(1000, int(anim.get("duration_ms") or 220)))
    except (TypeError, ValueError):
        anim["duration_ms"] = 220
    if anim.get("preset") not in ("minimal", "modern", "material", "smooth", "fast", "playful"):
        anim["preset"] = "modern"

    return merged


class Store:
    def __init__(self, path=None):
        self._path = Path(path or config.SETTINGS_PATH)
        self._lock = threading.Lock()
        self._data = config.DEFAULT_SETTINGS
        self.load()

    def load(self):
        with self._lock:
            try:
                if self._path.exists():
                    # utf-8-sig tolerates a UTF-8 BOM (PowerShell/older editors
                    # can write one), which would otherwise break json.load and
                    # silently reset the settings to defaults on cold start.
                    with open(self._path, "r", encoding="utf-8-sig") as fh:
                        self._data = _normalize(json.load(fh))
                else:
                    self._data = copy.deepcopy(config.DEFAULT_SETTINGS)
            except Exception:
                self._data = copy.deepcopy(config.DEFAULT_SETTINGS)
            return self._data

    def save(self):
        with self._lock:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._path, "w", encoding="utf-8") as fh:
                    json.dump(self._data, fh, indent=2, ensure_ascii=False)
            except Exception as exc:
                raise RuntimeError(f"Failed to persist settings: {exc}")

    def get(self):
        with self._lock:
            return copy.deepcopy(self._data)

    def replace(self, new_data):
        """Replace the whole settings payload (used by import)."""
        with self._lock:
            self._data = _normalize(copy.deepcopy(new_data))
        self.save()

    def update(self, patch):
        """Deep merge a patch into the current settings and persist."""
        with self._lock:
            raw = copy.deepcopy(self._data)
            merged = _normalize(_deep_merge_patch(raw, patch))
            self._data = merged
        self.save()
        return self.get()

    # --- library helpers -------------------------------------------------
    def get_library(self, library_id):
        for lib in self._data["libraries"]:
            if lib["id"] == library_id:
                return lib
        return None

    def add_library(self, name, path):
        with self._lock:
            for lib in self._data["libraries"]:
                if lib["path"].lower() == path.lower():
                    raise ValueError("Library with that path already exists")
            lib = {
                "id": uuid.uuid4().hex[:8],
                "name": name or path,
                "path": path,
                "scan": None,
                "enabled": True,
            }
            self._data["libraries"].append(lib)
        self.save()
        return lib

    def remove_library(self, library_id):
        with self._lock:
            self._data["libraries"] = [
                lib for lib in self._data["libraries"] if lib["id"] != library_id
            ]
        self.save()

    def rename_library(self, library_id, name):
        with self._lock:
            lib = self.get_library(library_id)
            if lib:
                lib["name"] = name
        self.save()

    def set_library_enabled(self, library_id, enabled):
        """Enable / disable a library (disabled ones are skipped by
        "all-library" scans/operations but their files stay on disk)."""
        with self._lock:
            lib = self.get_library(library_id)
            if lib:
                lib["enabled"] = bool(enabled)
        self.save()

    def set_scan(self, library_id, scan_payload):
        with self._lock:
            lib = self.get_library(library_id)
            if lib:
                lib["scan"] = scan_payload
        self.save()


def _deep_merge_patch(base, patch):
    if isinstance(patch, dict):
        for key, value in patch.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                base[key] = _deep_merge_patch(base[key], value)
            else:
                base[key] = copy.deepcopy(value)
    return base


# Module-level singleton used by the Flask app.
store = Store()