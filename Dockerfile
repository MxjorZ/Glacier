# syntax=docker/dockerfile:1
#
# Glacier — multi-stage Docker image.
#
# Stage 1 builds the React frontend (Node). Stage 2 runs the Python backend and
# copies the built frontend into it. The Flask app serves both the API and the
# static UI, so the whole service is a single container.

# ---------- Stage 1: build the React frontend ----------
FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY glacier_frontend/package.json glacier_frontend/package-lock.json ./
RUN npm ci
COPY glacier_frontend/ ./
RUN npm run build

# ---------- Stage 2: Python runtime ----------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    HOME=/data \
    PIP_NO_CACHE_DIR=1

# Run as root (the default) so Glacier has full access to the bind-mounted
# music folders (e.g. the host's /mnt). This is intentional and required for
# Glacier to browse and manage the mounted libraries.
USER root

WORKDIR /app

COPY requirements.txt ./
# gunicorn is only needed in the (Linux) container; keep it out of the Windows
# dev requirements so `glacier_env` continues to install cleanly.
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir "gunicorn>=21,<24"

COPY wsgi.py ./
COPY glacier.py ./
COPY glacier_backend/ ./glacier_backend/
COPY --from=frontend-build /app/frontend/dist ./glacier_frontend/dist

# Everything is served on this port inside the container.
EXPOSE 5050

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:5050/api/system', timeout=5); raise SystemExit(0 if r.status==200 else 1)"

# gthread worker keeps SSE streaming happy; single worker matches the app's
# single-job supervisor design. Host port mapping is done in compose.yaml.
CMD ["gunicorn", "--bind", "0.0.0.0:5050", "--workers", "1", "--threads", "8", "--timeout", "300", "--keep-alive", "65", "wsgi:app"]
