"""Glacier launcher.

Run from the project root:

    python glacier.py [--host HOST] [--port PORT]

Reads persistent settings for host/port, allowing CLI overrides. Serves both the
API and the built frontend.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from glacier_backend.app import create_app
from glacier_backend import config


def main():
    settings = None
    try:
        from glacier_backend.settings import store
        settings = store.get()
    except Exception:
        pass

    default_host = config.DEFAULT_HOST
    default_port = config.DEFAULT_PORT
    if settings:
        default_host = settings["server"].get("host") or default_host
        default_port = int(settings["server"].get("port") or default_port)

    parser = argparse.ArgumentParser(description="Glacier music library server")
    parser.add_argument("--host", default=default_host)
    parser.add_argument("--port", type=int, default=default_port)
    args = parser.parse_args()

    if args.port != default_port:
        pass  # allow override; could persist later

    app = create_app(host=args.host, port=args.port)
    print(f"Glacier {config.APP_VERSION} starting on {args.host}:{args.port}")
    try:
        app.run(host=args.host, port=args.port, debug=False, threaded=True)
    except Exception as exc:
        print(f"Failed to start server: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
