# Build Prompt: **Glacier**

Copy everything below this line into a coding AI as the primary product brief.

---

## Mission

Build **Glacier**, a local desktop/web music library control app.

- **UI language:** Clone the visual system, layout, density, theme engine, and motion style of SpotiFLAC (see attached `spotiflac_ui.md`).
- **Backend capabilities:** Reuse and improve the working logic from Songanizer Pro / `rebuild_music.py` (see attached `songanizer_backend_plan.md`).
- **Product name:** Glacier (not SpotiFLAC, not Songanizer).
- **Primary new feature:** **Library exclusivity** — user maintains **two (or more) libraries**; Glacier scans them and ensures a track cannot live in more than one library at a time (same song must not appear in both).

Do **not** embed the old Songanizer HTML UI. Do **not** call the product SpotiFLAC. Treat SpotiFLAC only as a **visual/UX reference**.

---

## Product summary

Glacier is an operator console for large local music collections (FLAC/MP3 first). It:

1. Manages multiple library roots (folders).
2. Analyzes, organizes, cleans, tags, and reports on those libraries.
3. Discovers new music via optional AI keys (suggestions + outbound search links is fine for v1).
4. Optionally talks to Plex (stats, search, rate, report dupes).
5. **Enforces exclusive ownership of tracks across libraries** (the signature Glacier feature).

Target runtime for v1:

- **Backend:** Python 3.11+ / Flask (or FastAPI if you justify it), mutagen, optional plexapi.
- **Frontend:** Modern SPA that matches SpotiFLAC shell (React + Tailwind + motion is ideal; Vue/Svelte acceptable if the same layout/theme/motion contract is met).
- **Delivery:** Localhost app, bindable to LAN, default port configurable (e.g. 5050). Frameless desktop wrapper is optional later; browser-first is OK for v1.

---

## UI requirements (from `spotiflac_ui.md`)

Implement the shell and interaction language described in `spotiflac_ui.md`:

### Shell

- Fixed **left sidebar** ~56px, icon-only, tooltips on the right, active state `primary/10`.
- Fixed **top title/status bar** ~40px with backdrop blur (drag region if desktop-wrapped).
- Content area inset: left 56px, top 40px; padding `p-4` / `md:p-8`.
- Narrow pages (`max-w-4xl`) for Settings / Support-like views; full width for tools and lists.
- Bottom-left short toasts; floating progress affordance; scroll-to-top FAB when needed.
- Minimum comfortable viewport ~1024×600.

### Pages / nav (adapt names to Glacier)

Suggested sidebar map:

| Nav | Page |
|-----|------|
| Home | Dashboard — stats, recent activity, quick actions |
| Libraries | Multi-root folder management + **Exclusivity / Cross-library** |
| Tools | Organize, covers, playlists, missing tags, corrupt scan, clean empty/dup folders |
| Cleanup | In-library duplicates, genre purge (two-phase), empty folders |
| Tags | Tag browser + editor |
| Discover | AI discovery + filters |
| Plex | Stats / search / rate / Plex dup report |
| Logs | Live op log (SSE stream) |
| Settings | All operational settings |
| Pairing / About | LAN URL, optional auto-start (Windows) |

Tools can be a single page with sections or a dropdown submenu (SpotiFLAC pattern).

### Theme

- OKLCH-based light/dark tokens; **primary accent presets** (include a cool default suitable for “Glacier”, e.g. sky/cyan/teal, plus the SpotiFLAC-style palette set).
- Theme mode: auto / light / dark.
- Font stack: modern sans + mono for logs/percentages.
- Radius ~0.625rem; dense icon buttons 40×40.

### Motion

- Dialog: fade + zoom ~200ms.
- Icon hover path-draw ~800ms easeInOut where icons are animated.
- Progress width transitions ~300ms.
- Honor `prefers-reduced-motion`.

### UX rules

- Destructive actions always need an explicit confirm with **counts**.
- Show live progress for long scans via SSE.
- Lowercase mono-style toasts optional; clear success/error/warning levels required.

---

## Backend requirements (from `songanizer_backend_plan.md`)

Port and **improve** the Songanizer backend. Keep the mental model:

- Settings JSON in the user home dir (e.g. `~/.glacier_settings.json`).
- Multi-folder roots.
- SSE event bus: `log`, `progress`, `done`, plus structured events.
- One heavy job at a time with a real job supervisor (fix Songanizer’s uneven locking).
- mutagen for FLAC/MP3 tags; cover extract; organize by templates; Hebrew-aware artist normalization may be kept if already useful.

### Must-have operations

- Analyze (all libraries)
- Organize / rename-move by tag templates
- In-library duplicates (with keep priority: deluxe / flac / largest)
- Covers generate / rebuild
- Playlist (m3u) generate
- Clean empty folders / duplicate folder shells
- Missing tags report
- Corrupt file report
- Library report export
- Genre list + two-phase genre purge with protected artists/albums/songs
- Cross-folder duplicate scan + selective move
- Tag list / read / save
- Folder CRUD + directory browser
- Settings get/set/export/import
- AI discover (OpenAI / Gemini / Claude keys optional)
- Plex connect: stats, search, rate, dedup **report**
- Network info + optional Windows startup entry

### Backend upgrades required vs Songanizer

1. **All library-mutating ops accept an explicit target folder or “all folders”** — no silent “first folder only”.
2. **Single job runner** with `_processing` (or job id) applied to every long task; refuse concurrent heavy jobs cleanly.
3. **Dry-run option** for organize, in-library dupes, genre purge, and **library exclusivity** actions.
4. Structured JSON results persisted or returned so the UI can show tables, not only log lines.
5. Product strings, settings filename, and default port branded **Glacier**.

---

## Signature feature: Library exclusivity

### Concept

User defines **two or more libraries** (e.g. `Library A` = main FLAC archive, `Library B` = phone/sync set, or “Lossless” vs “Lossy”).  
A logical track identity must be **owned by at most one library**.

### Identity keys (match priority)

Compute identity for each audio file in this order (configurable later; v1 implement all):

1. **ISRC** if present in tags (strongest).
2. Else normalized **(artist, title, album)** — casefold, strip feat./ft./punctuation noise, collapse whitespace.
3. Else normalized **(artist, title)** only.
4. Optional weak fallback: filename stem (report-only, never auto-delete on filename alone unless user opts in).

### Scan behavior

Op id suggestion: `library_exclusivity` or `exclusive_scan`.

1. Index all files under each configured library root (respect extensions + exclusions).
2. Group by identity key.
3. Any group with files in **2+ different libraries** is a **violation**.
4. Emit structured event, e.g. `exclusivity_report`:

```json
{
  "type": "exclusivity_report",
  "violations": [
    {
      "key": ["artist", "title", "album"],
      "identity_mode": "tags",
      "items": [
        {"path": "...", "library_id": "lib_a", "library_name": "Main", "size": 123, "ext": ".flac", "bitrate": "..."},
        {"path": "...", "library_id": "lib_b", "library_name": "Mobile", "size": 456, "ext": ".mp3", "bitrate": "..."}
      ]
    }
  ],
  "summary": {"files_scanned": 0, "violation_groups": 0, "libraries": 2}
}
```

### Resolution policies (user chooses per run or per group)

| Policy | Meaning |
|--------|---------|
| `keep_preferred_library` | User picks a preferred library; delete or move extras from other libs |
| `keep_best_quality` | Prefer FLAC > higher bitrate > larger size > deluxe path heuristic |
| `keep_newest` / `keep_oldest` | By mtime |
| `move_to_library` | Move losers into a chosen library (or a quarantine folder) |
| `report_only` | Default safe mode — no deletes |

Every destructive resolution must support:

- **Dry-run** (list actions only)
- **Confirm** with counts
- **Protected lists** (artist/album/title) that never auto-delete
- Per-group overrides in the UI (checkboxes)

### UI for exclusivity

On **Libraries** page:

1. List libraries (name + path + file count).
2. Button: **Scan exclusivity**.
3. Results table: identity, files per library, quality hints, suggested keeper.
4. Bulk actions: apply policy to selected groups / all.
5. Clear empty status when zero violations (“Libraries are exclusive”).

### Rules

- A file inside the same library tree twice is **in-library duplicate** (existing dup tool), not exclusivity.
- Exclusivity only triggers when the **same identity appears under different library roots**.
- Never delete the last remaining copy of an identity unless the user explicitly chooses a “delete all copies” path (do not offer that in v1).

---

## Settings model (Glacier)

Extend Songanizer-style settings:

```json
{
  "libraries": [
    {"id": "lib_a", "name": "Main Archive", "path": "D:/Music"},
    {"id": "lib_b", "name": "Mobile", "path": "E:/PhoneMusic"}
  ],
  "extensions": [".flac", ".mp3"],
  "excluded_folders": ["Playlists", "- Playlists"],
  "folder_pattern": "{albumartist}/{album} ({year})",
  "naming_pattern": "{artist} - {album} - {track:02d} - {title}",
  "dup_priority": "flac",
  "exclusivity_identity": "auto",
  "exclusivity_default_policy": "report_only",
  "preferred_library_id": "lib_a",
  "backup_before_move": false,
  "openai_key": "",
  "gemini_key": "",
  "claude_key": "",
  "ai_providers": ["openai"],
  "plex_url": "http://127.0.0.1:32400",
  "plex_token": "",
  "plex_music_section": "Music",
  "theme": "sky",
  "theme_mode": "auto"
}
```

Migration: if loading old Songanizer `folders: string[]`, convert to `libraries[{id,name,path}]`.

---

## API sketch (implement fully)

Keep SSE: `GET /api/events`.

Core:

- `GET/POST /api/settings`
- `GET/POST/DELETE` libraries (or folders) endpoints
- `POST /api/run/<op_id>` for long jobs
- Tag routes, genres, artists, list-dir, network-info

**Required new/adjusted ops:**

- `analyze`
- `organize` (body includes `library_id` or `all`)
- `duplicates`
- `library_exclusivity` (scan)
- `library_exclusivity_resolve` (body: policy + selected groups or “all” + dry_run flag)
- `covers`, `rebuild_covers`, `playlists`, `clean_empty`, `clean_dup_fold`
- `missing_tags`, `corrupt`, `report`
- `discover`
- `cross_dupes`, `move_duplicates`
- Plex ops as in the backend plan

All long ops emit `log` / `progress` / `done`. Structured results via dedicated event types or a `GET /api/jobs/last` if useful.

---

## Non-goals for v1

- Full Spotify/Tidal downloader inside Glacier (outbound search links OK).
- Mobile native apps.
- Cloud sync service.
- Automatic deletion without confirmation.
- Perfect MusicBrainz online matching (optional later).

---

## Implementation order

1. **Backend skeleton** — settings, libraries, SSE, analyze, job lock.
2. **Exclusivity scan + report_only UI** — prove the signature feature early.
3. **Exclusivity resolve** with dry-run + keep_best_quality + preferred library.
4. **Shell UI** — sidebar, theme, dashboard, logs.
5. **Tools & cleanup** — organize, dupes, covers, playlists, genre purge.
6. **Tags editor**.
7. **Discover + Plex** (optional keys).
8. **Polish** — dry-run everywhere destructive, export/import, pairing page.

---

## Acceptance criteria

1. User can register ≥2 libraries and run **Scan exclusivity**; violations list every cross-library same-track group.
2. User can resolve violations with dry-run then real run so each identity remains in only one library.
3. Analyze works across all libraries; organize can target one library explicitly.
4. UI matches SpotiFLAC-level shell density (sidebar + top bar + themed primary + SSE progress), branded Glacier.
5. No concurrent heavy jobs; UI disables run buttons while a job is active.
6. Destructive actions show counts and require confirm.
7. App runs via a single clear command (e.g. `python glacier.py` or `docker`/script) and opens `http://localhost:<port>`.

---

## Reference attachments the coding AI should use

1. `spotiflac_ui.md` — visual/layout/motion contract.
2. `songanizer_backend_plan.md` — backend inventory, gaps, event types, op list.
3. Optional: original `rebuild_music.py` as logic reference to port (do not ship its HTML UI).

---

## Coding AI instructions

- Prefer a clean monorepo: `backend/` + `frontend/` (or single Python app serving built static frontend).
- Write real, working code; no pseudo-code placeholders for core paths.
- Match the exclusivity feature exactly as specified.
- Brand all user-visible strings **Glacier**.
- When unsure, choose the safer default (`report_only`, dry-run, confirm).
- After implementation, document how to run, settings path, and how exclusivity identity matching works in a short `README.md`.

**Build Glacier now.**
