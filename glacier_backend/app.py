"""Glacier Flask application factory.

Creates the Flask app, enables CORS (LAN browser clients), registers the REST
API routes, and serves the built React frontend when present. The backend never
renders HTML templates itself.
"""

import os
import threading
import time
from pathlib import Path

from flask import Flask, send_from_directory

from . import config
from .api import register_routes, op_plex_rating_sync
from .jobs import supervisor
from .settings import store


def create_app(host=None, port=None):
    app = Flask(__name__, static_folder=None)
    app.config["HOST"] = host or config.DEFAULT_HOST
    app.config["PORT"] = port or config.DEFAULT_PORT

    try:
        from flask_cors import CORS
        CORS(app)
    except Exception:  # pragma: no cover
        pass

    register_routes(app)

    # Background poller for Plex rating -> tag sync (Stage 2). Re-checks every
    # 30s and runs a full sync pass when enabled, configured & due, respecting
    # the single-job supervisor lock.
    def _rating_timer():
        while True:
            time.sleep(30)
            try:
                plex = store.get().get("plex", {})
                if not plex.get("rating_sync_enabled"):
                    continue
                if not (plex.get("url") and plex.get("token")):
                    continue
                last = plex.get("last_rating_sync") or 0
                interval = int(plex.get("rating_sync_interval_sec", 600) or 600)
                if time.time() - last >= interval and not supervisor.running():
                    supervisor.start("plex-rating-sync", op_plex_rating_sync)
            except Exception:
                # Never let the background timer crash the app.
                pass

    threading.Thread(target=_rating_timer, daemon=True).start()

    # Locate the built frontend (../glacier_frontend/dist).
    frontend_dist = Path(__file__).resolve().parent.parent / "glacier_frontend" / "dist"

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def spa(path):
        if frontend_dist.exists():
            if path and (frontend_dist / path).exists() and not path.startswith("api/"):
                return send_from_directory(str(frontend_dist), path)
            index = frontend_dist / "index.html"
            if index.exists():
                return send_from_directory(str(frontend_dist), "index.html")
        return (f"Glacier backend is running. Build the frontend to get the UI. "
                f"(Version {config.APP_VERSION})"), 200

    return app


if __name__ == "__main__":
    import sys
    print("Run via `python glacier.py` from the project root.")
