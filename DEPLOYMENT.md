# Glacier — Deployment Guide

Glacier runs like other self-hosted services (Lidarr, Sonarr, Radarr, slskd,
DroppedNeedle, Plex Web): everything runs on one server PC, and client PCs
reach it through a browser over the LAN.

```
Server PC
 ├── Glacier backend
 ├── Glacier frontend
 └── music libraries (e.g. D:\Music, E:\Archive)

Client PC (browser)
 └── http://SERVER_IP:5050
```

---

## 1. Development (localhost)

```sh
# from the project root
glacier_env\Scripts\python.exe glacier.py --host 127.0.0.1 --port 5050
```

Open `http://127.0.0.1:5050`.

Changes to the backend take effect on restart. For frontend hot-reload during
development, run `npm run dev` in `glacier_frontend` (Vite proxies `/api` to
`127.0.0.1:5050`).

After editing frontend source, rebuild the static bundle:

```sh
cd glacier_frontend
npm run build
cd ..
```

The backend serves the built app from `glacier_frontend/dist`.

---

## 2. LAN deployment (permanent server host)

1. Configure host/port — either in the **Settings → Server** page (saved to
   `~/.glacier_settings.json`) or with CLI flags:
   ```sh
   glacier_env\Scripts\python.exe glacier.py --host 0.0.0.0 --port 5050
   ```
2. Ensure Windows Firewall allows inbound TCP on the chosen port (e.g. 5050).
3. Add your music folders in **Libraries** (nothing is hardcoded).
4. Open `http://<server-ip>:5050` from a client PC on the same network.
   Find the server IP in the top bar or `http://<server-ip>:5050/api/system`.

### Run it as a persistent background service

Windows (Task Scheduler):
- Create a task that runs at startup / logon:
  `Program: C:\Users\...\Glacier\glacier_env\Scripts\python.exe`
  `Add arguments: C:\Users\...\Glacier\glacier.py --host 0.0.0.0 --port 5050`
  `Start in: C:\Users\...\Glacier`

Linux (systemd example):
```ini
[Unit]
Description=Glacier music library manager
After=network.target

[Service]
User=glacier
WorkingDirectory=/opt/glacier
ExecStart=/opt/glacier/glacier_env/bin/python glacier.py --host 0.0.0.0 --port 5050
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## 6. Docker deployment (docker compose) — Stage 3

Glacier also ships as a self-contained **docker compose** stack. The image
builds the React frontend (Node) and runs the Python backend under Gunicorn,
so the whole service is **one container** serving both the API and the UI.

```sh
# from the project root (where compose.yaml lives)
docker compose up -d --build
# open http://localhost:5050  (or the host machine's IP on the LAN)
```

### Configuration (`compose.yaml` + `.env`)

- Copy `.env.example` to `.env` and edit the values you need.
- `GLACIER_PORT`: host port the UI is published on (default 5050).
- `HOST_MNT` (default `/mnt`): which **host** directory is exposed inside the
  container at the same path (`${HOST_MNT}:/mnt`). **This is how Glacier sees
  your music.** If your libraries live under host `/mnt/music` and
  `/mnt/MusicFolder`, leave this default — the container’s `/mnt` then contains
  exactly those folders and the file explorer (and library paths) work like
  your native file browser. If your music is elsewhere, point `HOST_MNT` there
  or add explicit bind mounts (see below).
- `MUSIC_DIR`: optional **host** path mounted to `/music` for music that is not
  under `/mnt`. Inside Glacier → Libraries you add the library using the
  **container** path `/music` (or a subfolder like `/mnt/music`).
- To manage more than one library, add another bind mount in `compose.yaml`
  (commented examples are provided) and add the library as that container path.

> **Important:** a Docker container is isolated — it cannot see the host’s
> files unless they are bind-mounted. The reason Glacier’s explorer showed an
> empty `/mnt` is that only `/music` was mounted; the host `/mnt` was not.
> The stack now mounts `HOST_MNT` and runs as **root** so Glacier can read and
> manage all mounted music.

### Root & permissions

The container intentionally runs as **root** (`Dockerfile: USER root` and
`compose.yaml: user: "0:0"`). Glacier browses, scans, organizes, moves and tags
the mounted files, so root access to the mounted libraries is required for the
app to work properly. This applies only inside the container; it does not
change anything on the host (host folders are fully controlled by their own
filesystem permissions).

### Volumes & persistence

- `glacier-data:/data` — **must not** be removed. Glacier keeps
  `~/.glacier_settings.json` and the scan cache (`~/.glacier_cache`) here, so
  your libraries and settings survive restarts and rebuilds.
- The music folders are bind-mounted from the host so Glacier can scan,
  organize, move and tag your actual files. Only mount folders you are happy
  for Glacier to manage (exclusivity / organize can move files).

### Common commands

```sh
docker compose up -d --build      # build & start in the background
docker compose logs -f glacier    # follow the log
docker compose ps                 # status / health
docker compose down               # stop (data volume persists)
docker compose down -v            # stop AND wipe data/settings (destructive)
docker pull / rebuild             # after code changes: docker compose up -d --build
```

The container includes a healthcheck that calls `/api/system`; the service
shows as healthy once the backend responds.

> Docker is not required — the native Python + `npm run build` flow in §1/§2
> remains fully supported.

---

## 7. Settings persistence

All settings (libraries, templates, extensions, exclusions, exclusivity policy,
theme, Plex) live in `~/.glacier_settings.json` and survive restarts.
The inventory/cache that avoids re-reading every file lives in
`~/.glacier_cache/<library_id>.json`.

Export/import the whole configuration from **Settings → Export/Import**.

---

## 4. Security notes

Glacier is built for a **trusted LAN environment**. For any exposure beyond a
trusted network:

- Put it behind a reverse proxy with HTTPS (nginx/Caddy).
- Add an API token / authentication layer (not yet built-in).
- **Never** expose it directly to the public internet.

The app performs filesystem operations (move/rename/delete) on the server's
music folders. It never modifies files without explicit confirmation, and every
destructive operation requires a dry run + confirm dialog.

---

## 5. Quick verification

```sh
glacier_env\Scripts\python.exe backend_smoke_test.py   # backend functional test
cd glacier_frontend && npm run build                   # frontend build
```
