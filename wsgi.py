"""Gunicorn WSGI entry point for the Glacier Docker image.

The Flask app serves both the REST API and the built React frontend from
``glacier_frontend/dist``, so ``gunicorn wsgi:app`` inside the container exposes
the full Glacier service on the configured port.

Run locally (dev, Windows): ``glacier_env\\Scripts\\python.exe glacier.py``
instead. This module is only used by the production ``compose.yaml`` stack.
"""

from glacier_backend.app import create_app

app = create_app()
