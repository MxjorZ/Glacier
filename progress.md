# Glacier — Development Memory (progress.md)

This file is Glacier's persistent development memory. It is updated after every
meaningful change so development can continue across sessions and even if a
session is lost mid-way. Always read this file first, then update it after you
change code.

**Last updated:** 2026-08-04

---

## CHANGELOG (most recent first)

- **2026-08-04 Stage 3 start — Libraries connection/selection UI + Docker stack**
  - **Libraries page** now shows a real **server-connection state** (loading /
    connected / unreachable banner with Retry), an explicit **“Load libraries”**
    button, and a per-library **Active/Disabled switch**. Disabled libraries are
    excluded from “all-library” scans/operations (analyze-all, exclusivity,
    artist exclusivity/resolve, report) but their files stay on disk.
  - Backend: new `enabled` flag per library (default true, tolerant upgrade);
    `Store.set_library_enabled()`; `GET /api/libraries/status` (returns
    `enabled` + `exists` for each configured path — the UI uses it to flag
    unreachable drives); `PATCH /api/libraries/<id>` now also sets `enabled`;
    `_enabled_libs()` helper used by batch ops.
  - **Docker stack (Stage 3):** multi-stage `Dockerfile` (Node builds frontend
    → Python/Gunicorn serves API + UI in one container), `compose.yaml`
    (`./music` bind mount + `glacier-data:/data` volume, healthcheck), `.env.example`,
    `.dockerignore`, `wsgi.py` (Gunicorn entry). `HOME=/data` keeps settings &
    cache in the volume. Docs added to `DEPLOYMENT.md` §6 and README quick start.
  - Verified: backend smoke test passes; new `probe_library_enabled.py`
    (temporary) passes (status, enabled PATCH, batch-analyze skips disabled);
    `npm run build` succeeds; live server serves UI + `/api/system` +
    `/api/libraries/status` (all 200).


- **2026-08-04 Stage 2 (full build)** — Live **path/filename preview** (new
  `/api/preview-path`, Tools Organize live preview w/ unknown-token flags);
  **AMOLED + auto + custom hex/rgb accent** theme (themes.js + `.amoled` CSS +
  Settings UI); **job-complete sound** (lib/sound.js, SSE done trigger,
  placeholder `public/sounds/job-done.wav`, sound settings); **artist
  exclusivity** (scan + report_only/keep_preferred resolve, SSE
  `artist_exclusivity_report`, Libraries page); **create library & move**
  wizard (`library/extract.py` filters incl. Hebrew-script, dry-run + confirm,
  move-not-copy); **Plex rating sync** (metadata `rating` FLAC RATING / MP3
  POPM, `plex/sync.py`, manual sync + 10-min background poll, rating_overwrite
  default false). **Fixed pre-existing bug:** missing `Supervisor.history`
  property broke `/api/jobs/history`. Verified: backend smoke + new API probe,
  `npm run build`.

- **2026-08-04** Frontend: full **SpotiFLAC 1:1 visual redesign** (user did not
  like the previous interface). Same layout (56px icon sidebar + top bar),
  same color scheme (dark/light via oklch CSS variables, 9 accents), same
  shadcn-style icon components (lucide-react), **no emojis anywhere**.
  - Ported the SpotiFLAC component set to this codebase in JSX +
    Tailwind v4: `button`, `card`, `input`, `select`, `checkbox`, `switch`,
    `label`, `tabs`, `tooltip`, `progress`, `table`, `badge`, `dialog`.
    Vite config now uses `@tailwindcss/vite` + `@import "tailwindcss"`.
  - Rewrote ALL 9 pages on the new primitives: Dashboard, Libraries, Tools,
    Cleanup, Tags, Plex, Logs, Settings, About.
  - **Fixed** `select.jsx`: used `SelectPrimitive.Text` (removed in
    @radix-ui/react-select@2.3.7) → `SelectPrimitive.ItemText`.
  - **Fixed** Tools.jsx `report` name collision (state vs function) →
    `generateReport`.
  - Tags page gained a folder-browse modal (`FolderPicker`).
  - Verified: `npm run build` succeeds; `glacier.py` serves UI (200) with the
    new build; `/api/system`, `/api/list-dir` respond.

- **2026-08-04** Docs: rewrote `README.md` and added `DEPLOYMENT.md`
  (dev + LAN server deployment + systemd/Task Scheduler notes).
- **2026-08-04** Backend: added `/api/run/rebuild-covers` (force overwrite of
  existing cover files; `reports/exporter.extract_covers(force=True)` also
  clears stale cover files of other extensions). `/api/run/covers` now accepts
  `force`. Frontend Covers tab has "Run" and "Rebuild (overwrite)" buttons.
- **2026-08-04** Backend: report job now also returns `json` payload and
  `json_text` (JSON serialization of total + per-library + problems).
- **2026-08-04** Created `progress.md` as the persistent development memory.
- **2026-08-04** Verified end-to-end after docs + covers/report changes:
  server serves built UI (200), `rebuild-covers` route present and validates
  correctly (400 on missing library_id), backend smoke test passes, frontend
  `npm run build` passes.

---

## 1. What Glacier Is

A self-hosted local music library management application (Flask + React).
The signature feature is **Library Exclusivity**: the same track identity may
exist in only one managed library. It manages multiple library folders,
analyzes collections, organizes files by metadata templates, edits tags,
detects duplicates, cleans clutter, exports covers/playlists/reports, and
integrates read-only with Plex. UI style inspired by SpotiFLAC but it is an
independent product named **Glacier**.

Stack: Python 3.11+ / Flask / mutagen / flask-cors / plexapi — React / Vite /
Tailwind CSS. Dev on localhost:5050; deployment on a LAN server.

---

## 2. Project Layout

```
C:\Users\0pxxL\Pictures\Glacier\
├── glacier.py                  # launcher (host/port, dev server)
├── requirements.txt
├── glacier_backend/            # Flask backend package
│   ├── app.py                  # app factory + SPA static serving
│   ├── api.py                  # all REST routes + job op callbacks
│   ├── config.py               # constants + default settings
│   ├── settings.py             # persistent settings store (~/.glacier_settings.json)
│   ├── events.py               # SSE hub
│   ├── jobs.py                 # job supervisor (single-run gating)
│   ├── browser.py              # directory browser
│   ├── library/
│   │   ├── metadata.py         # mutagen read/write (FLAC + MP3)
│   │   ├── scanner.py          # scan + stats + persistent inventory cache
│   │   ├── organizer.py        # template move/rename (dry-run/apply)
│   │   ├── duplicates.py       # in-library duplicates
│   │   └── exclusivity.py      # cross-library exclusivity engine
│   ├── tags/editor.py          # tag-list/read/save
│   ├── cleanup/cleaner.py      # empty folders, dup shells, missing tags, corrupt
│   ├── reports/exporter.py     # JSON/text reports, covers, playlists
│   └── plex/client.py          # plexapi integration (read-only)
├── glacier_frontend/           # React SPA (Vite + Tailwind)
│   ├── index.html
│   ├── vite.config.js          # dev proxy /api -> 127.0.0.1:5050
│   ├── tailwind.config.js      # CSS-variable theme tokens
│   ├── src/
│   │   ├── main.jsx  App.jsx  index.css  api.js  theme.js
│   │   ├── useSSE.js  useJob.js  toast.jsx  dialog.jsx
│   │   ├── ui.jsx  ui2.jsx      # Button/Card/Input/Select/... + Table/Tabs/Stat
│   │   ├── FolderPicker.jsx
│   │   └── pages/            # Dashboard Libraries Tools Cleanup Tags Plex Logs Settings About
├── backend_smoke_test.py     # end-to-end backend functional test (FAST PASSES)
└── progress.md               # this file
```

---

## 3. Current State (DONE — working)

### Backend — COMPLETE and tested
- Persisted settings (`~/.glacier_settings.json`), deep-merge normalization,
  library CRUD (add/remove/rename), scan metadata stored back into settings.
- SSE hub at `GET /api/events` (connected/log/progress/done/job_state), with
  history endpoint `GET /api/logs`.
- Job supervisor: only one filesystem-heavy job at a time; new jobs rejected
  while running; every job ends with a `done` event; result in history.
- Scanner: walks a library, reads FLAC/MP3 tags via mutagen, computes stats
  (tracks/artists/albums/size/extensions/duration/errors/covers), persists an
  inventory cache per library keyed by a lightweight dir fingerprint.
- Exclusivity engine: identity normalization (lowercase, strip punctuation,
  strip feat/ft, collapse spaces); priority ISRC → artist+title+album →
  artist+title → filename fallback. Violation grouping + non-destructive
  resolution policies: report_only / keep_best_quality / keep_preferred_library
  / keep_newest / move_to_library / quarantine. Apply requires confirm=true.
- In-library duplicates via same identity normalization.
- Organizer: folder + filename templates with format specs ({track:02d}); dry
  run returns plan; apply requires confirm and refuses to escape library root.
- Tag editor: tag-list / tag-read / tag-save over FLAC and MP3.
- Cleanup: empty folders, duplicate folder shells, missing tags, corrupt files;
  removal requires confirm.
- Covers (extract embedded artwork), playlists (per-album .m3u), reports
  (JSON/text).
- Plex: status, stats, search, rate, duplicates (all read-only).
- Directory browser (`POST /api/list-dir`) incl. roots.
- `glacier.py` launcher reads host/port from settings with CLI override.
- CORS enabled; backend serves the built frontend from `glacier_frontend/dist`.

**Backend test:** `backend_smoke_test.py` builds real temp FLAC/MP3 files and
verifies scanner, organizer, duplicates, exclusivity, tags, cleanup, covers/
playlists, resolver, and the Flask API client. It PASSES fully.

### Frontend — BUILD SUCCEEDS and served (SpotiFLAC 1:1 redesign)
- Theme: oklch CSS variables; dark (default) + light modes; 9 accent presets
  (cyan, sky, teal, blue, purple, green, orange, red, yellow); `applySettingsTheme()`
  switches mode/accent at runtime from Settings.
- Layout: fixed 56px icon sidebar + 40px top bar + content offset; toasts
  (Sonner); live job progress overlay; hash routing between 9 pages.
- Pages all rewired to real API calls: Dashboard, Libraries, Tools
  (Organize/Duplicates/Exclusivity/Covers/Playlists/Report), Cleanup, Tags,
  Plex, Logs (SSE), Settings, About.
- Reusable shadcn-style primitives (ported from SpotiFLAC, lucide icons):
  Button, Card, Input, Textarea, Select, Checkbox, Switch, Label, Tabs,
  Tooltip, Progress, Table, Badge, Dialog + Modal/Confirm helpers.
- Folder picker modal (`/api/list-dir`) reused by Libraries and Tags.
- `npm run build` → dist/; backend serves index.html + assets.

### Verified end-to-end
- `python glacier.py --port 5050` → 200 OK, React index served.
- `/api/system` returns name=Glacier, host/port/ip.
- `/api/settings`, `/api/libraries`, static JS asset all served.
- Job supervisor ran `/api/run/analyze` to completion through the API.
- Organize apply physically moved a file into `Artist/Album (year)/NN - Title`.

---

## 4. Env / Third-party notes
- venv: `glacier_env` (Python 3.12.10). Run: `glacier_env\Scripts\python.exe`.
- Pip-installed: Flask 2.3.1, Werkzeug>=2.3,<3 (pinned — Flask 2.3.1 breaks on
  Werkzeug 3.1 `__version__`), mutagen 1.48.1, flask-cors 6.0.5, plexapi 4.18.2.
- Node v22 / npm 11 available. Frontend deps installed; esbuild postinstall
  approved. Build: `npm run build` in `glacier_frontend`.
- mutagen 1.48: cannot create FLAC/MP3 from an empty file; must write a valid
  stream first (see smoke-test helpers `_minimal_flac` / `_mp3`).

---

## 5. TO DO / NEXT STEPS (not required for v1 but good next)

Backend:
- [x] Deployment documentation (`README.md` + `DEPLOYMENT.md`).
- [x] `rebuild-covers` endpoint (force overwrite) — added.
- [x] Report job returns JSON payload + `json_text`.
- [ ] Settings: persist CLI `--port` override back into settings (optional).
- [ ] Optional auth/API-token + HTTPS reverse-proxy note for public exposure
      (LAN trusted env only for now).
- [ ] Quarantine directory configurable (currently `~/.glacier_quarantine`).

Frontend:
- [x] Confirm dialogs for Plex actions (currently read-only, so none needed).
- [x] A search/browse library tab in Tags to navigate subfolders — added
      folder-browse modal (`FolderPicker`) to the Tags page.
- [ ] Settings server host/port: optionally restart-prompt after save.

Docs / QoL:
- [x] Update root README.md with the real run steps for backend + frontend.
- [x] Write DEPLOYMENT.md covering dev (localhost) and LAN server deployment.
- [x] **Docker stack (Stage 3)**: multi-stage `Dockerfile`, `compose.yaml`,
      `.env.example`, `.dockerignore`, `wsgi.py` (Gunicorn). One container
      serves API + built UI. Docs in DEPLOYMENT.md §6 + README Option A.
      (Not build-tested here — Docker/Docker Desktop not installed on this dev
      box yet.)

Docker / Stage 3 (continuation):
- [ ] Actually build & run `docker compose up -d --build` on a Docker host;
      verify healthcheck, SSE live progress, and organize/exclusivity jobs
      through the container (gthread worker).
- [ ] Optionally add auth/API-token + HTTPS reverse-proxy note for Docker.

---

## 6. How to Run
```sh
# Docker (one container, serves API + built UI)
docker compose up -d --build
# then open http://<host>:5050  (configure music via .env / compose.yaml)

# Backend (native, from project root)
glacier_env\Scripts\python.exe glacier.py --port 5050
# then open http://127.0.0.1:5050

# Rebuild frontend after changes (from glacier_frontend)
npm run build

# Frontend dev server (hot reload, proxies /api to backend)
npm run dev
```

