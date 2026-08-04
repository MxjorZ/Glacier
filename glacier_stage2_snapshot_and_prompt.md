# Glacier — Stage 2 Snapshot, Feature Baseline & Development Prompt

**Product:** Glacier  
**Document purpose:** Session-handoff snapshot + next-stage build brief  
**Use:** Send this file (and prior plans) to any coding agent to continue development without losing context  
**Status date:** 2026-08-04  

---

## 0. How to use this document

1. Treat **this file** as the living product memory for Glacier.
2. After every meaningful change, append a short entry under **§12 Change log**.
3. Priority order when docs conflict:
   1. This file (Stage 2 + deltas)
   2. `glacier_build_prompt.md` (original product brief)
   3. `songanizer_backend_plan.md` (backend ops inventory)
   4. `spotiflac_ui.md` (UI shell / theme / motion contract)
4. **Do not** pull features from SpotiFLAC-Next in this stage.
5. At the end of Stage 2 work, the human will provide **SpotiFLAC-Next** for selective tool imports (audio quality analyzer, resampler, converter, file manager, lyrics manager, metadata enricher)—only where Glacier does not already implement an equivalent.

---

## 1. Product snapshot (current intended app)

Glacier is a local music-library operator console:

- Multi-library roots (named libraries with paths)
- Analyze / organize / clean / tag / report
- SSE live progress
- **Library exclusivity** (a logical track must not live in more than one library)
- UI inspired by SpotiFLAC shell (sidebar, theme, motion)—branded **Glacier**, not SpotiFLAC
- Backend lineage: Songanizer / `rebuild_music.py` capabilities, improved for multi-library + safer jobs

### 1.1 Architecture (target)

```
Glacier/
  backend/          # Python API (Flask or FastAPI)
  frontend/         # SPA (React+Tailwind preferred; matches SpotiFLAC shell contract)
  README.md
  glacier_*.md      # planning docs
```

- Settings file: `~/.glacier_settings.json`
- Real-time: SSE (`log`, `progress`, `done`, plus structured events)
- One heavy job at a time (job lock)
- Destructive ops: dry-run + confirm with counts

### 1.2 Core pages (UI map)

| Nav | Purpose |
|-----|---------|
| Home / Dashboard | Stats, recent activity, quick actions |
| Libraries | Roots, exclusivity scan/resolve, **create library + move**, artist exclusivity |
| Tools | Organize, covers, playlists, missing tags, corrupt, clean empty/dup folders |
| Cleanup | In-library dupes, genre purge (two-phase) |
| Tags | Tag browser / editor |
| Discover | Optional AI discovery |
| Plex | Stats / search / rate / **rating sync** |
| Logs | Live SSE log |
| Settings | Patterns, themes (**incl. AMOLED + custom hex/rgb**), sounds, Plex, exclusivity policies |

### 1.3 Backend capability baseline (from Stage 1 brief)

Assume or implement if missing:

- Settings get/set; library CRUD
- `analyze` (all libraries or one)
- `organize` (explicit `library_id` or all—not first-folder-only)
- In-library duplicates
- Covers / playlists / empty folders / missing tags / corrupt / report
- Genre list + two-phase purge with protections
- Cross-folder dupes + selective move
- Tag read/write
- SSE job runner + lock
- **Library exclusivity scan** (`report_only` minimum) with identity: ISRC → artist/title/album → artist/title
- Optional: AI discover keys, Plex connect

### 1.4 UI baseline (from SpotiFLAC contract)

- ~56px icon sidebar, ~40px top bar, content inset
- Light / dark theme tokens (OKLCH-style or equivalent)
- Primary accent presets
- Motion: dialog fade/zoom, progress transitions, reduced-motion respect
- Toasts; live progress for long jobs

---

## 2. NEW FEATURES FOR STAGE 2 (must implement)

### 2.1 Final folder & naming layout — live format preview

**Goal:** Organization template preview updates **in real time** as the user edits patterns.

**Requirements:**

- Settings (or Organize panel) fields:
  - Folder pattern (e.g. `{albumartist}/{album} ({year})`)
  - Filename pattern (e.g. `{artist} - {album} - {track:02d} - {title}`)
- Sample track context (fixed demo row and/or last selected real file tags)
- **Live preview** of resulting relative path + filename on every keystroke / control change (no Apply required for preview)
- Show example full path under a chosen library root
- Invalid tokens highlighted; unknown tokens listed
- Preview must reflect: track padding, year, albumartist vs artist, Various Artists rules if backend supports them

**API (suggested):**

- `POST /api/preview-path` `{ folder_pattern, naming_pattern, sample_tags, library_id? }` → `{ folder, filename, relative_path }`
- Or pure client-side if token set is documented and identical to backend organizer

**Acceptance:** Changing any pattern character updates the preview within one UI frame / debounce ≤150ms without running organize.

---

### 2.2 Plex library rating → FLAC tag sync

**Goal:** Actively sync Plex user star ratings into local FLAC (and optionally MP3) tags.

**Rules:**

- Plex 5-star scale: **5 stars = 10.0** in Plex rating API terms (as used by Plex clients)
- Map to file tag **`rating = 100`** on a full 5-star rating  
  - Linear map suggested: `tag_rating = round(plex_rating_10 * 10)` so 10.0 → 100, 5.0 → 50, etc.
  - Document the mapping in Settings
- **Poll every 10 minutes** while Glacier is running (configurable interval; default 600s)
- Scope: configured Plex music section(s) / libraries the user selects
- Match Plex tracks to local files via: guid/path if available, else artist+album+title (+ track) normalized
- Write with mutagen (or existing tag writer); prefer FLAC `%rating` / popular frames the app already uses—**be consistent with Tags editor**
- UI:
  - Settings: enable sync, interval, section pick, last run time, last stats
  - Manual **Sync ratings now**
  - Log SSE lines for matches / misses / writes
- Do not overwrite a higher local rating unless setting `plex_rating_overwrite: true` (default **true** for “Plex is source of truth” or default **false**—**choose default false** for safety; document)

**Acceptance:** With Plex connected, a 5-star track becomes `rating=100` on the matched local FLAC within one poll cycle or manual sync.

---

### 2.3 Theme customization — AMOLED + custom colors

**Goal:** Extend SpotiFLAC-style theming.

**Add:**

1. **Color mode: AMOLED**
   - True black backgrounds (`#000000` / equivalent tokens)
   - Surfaces barely elevated (optional `#0a0a0a` for cards if needed for separation)
   - Text/icons remain readable (primary accent + light gray text)
2. **Custom accent color**
   - User can enter **hex** (`#RRGGBB` or `#RGB`) and/or **RGB** (r,g,b 0–255)
   - Live swatch + apply to `--primary` (and derived hover/muted tokens)
   - Persist in settings: `theme_mode: light | dark | amoled | auto`, `accent_preset: ... | custom`, `accent_custom: "#00A3FF"`

**Acceptance:** User selects AMOLED and sees pure black chrome; user enters a custom hex and the accent updates across sidebar active states, buttons, and focus rings.

---

### 2.4 Sound on finished activity

**Goal:** Play a short sound when a job finishes (success or failure distinct if possible).

**Requirements:**

- Trigger on SSE `done` (and optionally on exclusivity resolve / move batch complete)
- Sound asset: **taken from SpotiFLAC** (same notification/finish sound used there—extract from SpotiFLAC frontend assets when available in workspace; if not present, placeholder path `frontend/public/sounds/job-done.wav` and note “replace with SpotiFLAC asset”)
- Settings toggles:
  - `sound_on_complete: true/false`
  - `sound_on_error: true/false` (optional second asset or same sound)
- Respect OS / browser autoplay policies (user gesture once may be required—document)
- Do not block UI on audio play

**Acceptance:** Completing Analyze or Organize plays the configured sound when toggle is on.

---

### 2.5 Duplicate & exclusivity management — tracks AND artists

**Goal:** Stronger multi-library separation.

#### A. Track exclusivity (already in brief — harden)

- Same identity must exist in **at most one** library
- Scan + report + resolve (dry-run, preferred library, best quality, move, report_only)
- Identity: ISRC → artist/title/album → artist/title

#### B. Artist exclusivity (NEW)

- A given **artist** (normalized name) must belong to **one library only**
- If artist appears under library A and B → **violation group**
- Resolution policies:
  - `keep_preferred_library` (move all that artist’s albums/tracks from other libs)
  - `report_only`
  - optional `split_exception` list (artists allowed in multiple libs—rare)
- UI: Libraries → Exclusivity tabs: **Tracks** | **Artists**
- SSE / structured events: `artist_exclusivity_report`

**Acceptance:** Artist present in two libraries appears in Artist exclusivity report; resolve moves or lists actions so only one library retains that artist.

---

### 2.6 Create new library + move matching files (one action)

**Goal:** e.g. separate Hebrew repertoire into a new library in one flow.

**Flow:**

1. User clicks **Create library & move**
2. Wizard:
   - New library name + destination path (create folder if needed)
   - Filter rules (combinable):
     - Language / script heuristic (e.g. Hebrew characters in artist/title/album path)
     - Genre contains …
     - Artist in list …
     - Path regex …
     - Tag equals …
   - Source libraries to pull from
   - Dry-run preview table (count, bytes, sample paths)
3. Confirm → create library entry in settings → move files (not copy by default) → refresh indexes
4. SSE progress; final sound on complete

**API sketch:**

- `POST /api/libraries` create
- `POST /api/run/library_extract_move` `{ name, path, filters, source_library_ids, dry_run }`

**Acceptance:** User can create “Hebrew”, filter Hebrew-script tags/paths, dry-run, then move into the new library in one confirmed action.

---

## 3. Settings schema additions (Stage 2)

Merge into `~/.glacier_settings.json`:

```json
{
  "theme_mode": "auto",
  "accent_preset": "sky",
  "accent_custom": null,
  "sound_on_complete": true,
  "sound_on_error": false,
  "sound_asset_complete": "sounds/job-done.wav",
  "folder_pattern": "{albumartist}/{album} ({year})",
  "naming_pattern": "{artist} - {album} - {track:02d} - {title}",
  "plex_url": "",
  "plex_token": "",
  "plex_music_section": "Music",
  "plex_rating_sync_enabled": false,
  "plex_rating_sync_interval_sec": 600,
  "plex_rating_overwrite": false,
  "exclusivity_track_policy": "report_only",
  "exclusivity_artist_policy": "report_only",
  "preferred_library_id": null,
  "artist_exclusivity_exceptions": []
}
```

---

## 4. Implementation order (Stage 2)

1. **Audit** current repo vs §1 (list what exists vs missing)—write into §12  
2. Live **path/filename preview**  
3. **AMOLED + custom accent**  
4. **Job-complete sound** (placeholder asset OK until SpotiFLAC sound copied)  
5. Harden **track exclusivity** resolve UX  
6. **Artist exclusivity** scan + report_only + resolve  
7. **Create library & move** wizard  
8. **Plex rating sync** (manual then 10-minute timer)  
9. Polish: settings persistence, SSE labels, README  

---

## 5. Agent instructions (for the coding AI)

- Prefer **working code** and real files on disk.
- Brand all UI strings **Glacier**.
- Multi-library safe: never silently operate on “first folder only.”
- Every long task: job lock + SSE.
- Destructive paths: dry-run + confirm counts.
- After each completed milestone, append **§12 Change log** with date, files touched, and behavior added.
- Do **not** integrate SpotiFLAC-Next tools in this stage.
- If Stage 1 items from §1 are missing, implement them before or while doing Stage 2 features as dependencies require.

### Suggested first agent message

```text
Read glacier_stage2_snapshot_and_prompt.md (this file) plus glacier_build_prompt.md.

1) Audit the current Glacier repo and summarize what already exists vs §1 baseline.
2) Implement Stage 2 in the order in §4, starting with live folder/naming preview,
   then AMOLED+custom accent, then completion sound, then exclusivity (track+artist),
   then create-library-and-move, then Plex rating sync.
3) Append each finished milestone to §12 Change log in this file.
```

---

## 6. Explicit non-goals (this stage)

- Importing SpotiFLAC-Next modules (quality analyzer, resampler, converter, file manager, lyrics manager, metadata enricher)
- Full SpotiFLAC downloader / streaming clone
- Cloud sync service
- Auto-delete without confirmation

---

## 7. Reminder for the human (after Stage 2)

When Stage 2 is stable, **send SpotiFLAC-Next** so the next session can evaluate and port only missing tools:

- Audio quality analyzer  
- Audio resampler  
- Audio converter  
- File manager  
- Lyrics manager  
- Metadata enricher  

Skip any item Glacier already covers well.

---

## 8. Reference doc index

| File | Role |
|------|------|
| `glacier_stage2_snapshot_and_prompt.md` | **This file** — Stage 2 source of truth |
| `glacier_build_prompt.md` | Original Glacier build brief |
| `songanizer_backend_plan.md` | Backend ops / gaps |
| `spotiflac_ui.md` | UI/layout/theme/motion |
| `rebuild_music.py` | Optional logic reference only |

---

## 9. Acceptance checklist (Stage 2 done when)

- [ ] Path/filename preview updates live with pattern edits  
- [ ] AMOLED mode + custom hex/rgb accent persist and apply  
- [ ] Job completion plays sound when enabled  
- [ ] Track exclusivity: scan + resolve so a song is in one library only  
- [ ] Artist exclusivity: scan + resolve so an artist is in one library only  
- [ ] Create new library + filter move (e.g. Hebrew split) with dry-run  
- [ ] Plex ratings polled every 10 minutes (when enabled); 5 stars → rating tag 100  
- [ ] §12 change log updated for work performed  

---

## 10. SpotiFLAC sound asset note

Locate SpotiFLAC frontend notification/complete sound (often under `public/`, `assets/`, or toast sound helper). Copy into Glacier as:

`frontend/public/sounds/job-done.wav` (or original extension)

Wire `sound_asset_complete` to that path. If the asset is not in the workspace yet, implement the player + setting and leave a clear TODO path.

---

## 11. Plex rating mapping reference

| Plex rating (0–10 scale) | Stars (approx) | Glacier file tag `rating` |
|-------------------------|----------------|---------------------------|
| 10.0 | 5 | 100 |
| 8.0 | 4 | 80 |
| 6.0 | 3 | 60 |
| 4.0 | 2 | 40 |
| 2.0 | 1 | 20 |
| 0 / unset | — | skip write (default) |

Formula: `tag_rating = clamp(round(plex_rating * 10), 0, 100)`.

---

## 12. Change log (append only)

### 2026-08-04 — Document created
- Stage 2 snapshot and development prompt authored.
- Baseline features summarized from Glacier planning (UI SpotiFLAC-like, backend Songanizer-like, track exclusivity).
- New requirements recorded: live path preview, Plex rating sync (10 min), AMOLED + custom colors, completion sound (SpotiFLAC asset), track+artist exclusivity, create-library-and-move.
- SpotiFLAC-Next import explicitly deferred; human reminder included.

### (Agent: append new entries below)

```
### YYYY-MM-DD — <milestone>
- ...
- Files: ...
```

---

### 2026-08-04 — Stage 2 implemented (full build)
- **Live folder/filename preview (2.1)**: `POST /api/preview-path` + `organizer.preview_path()` with unknown-token validation; Tools → Organize now renders the relative/full path live (debounced ≤150ms), invalid tokens highlighted.
- **AMOLED + custom accent (2.3)**: `themes.js` added `amoled` mode (true-black chrome), `auto` (system), custom hex/rgb accent with luminance-based foreground; `index.css` `.amoled` block; Settings Theme card extended with mode + custom color + live swatch.
- **Job-complete sound (2.4)**: `lib/sound.js` (unlock on first user gesture), SSE `done` trigger in App.jsx; placeholder `frontend/public/sounds/job-done.wav` (TODO: replace with SpotiFLAC asset); `sound_on_complete`/`sound_on_error`/`sound_asset_complete` settings + Settings Sound card.
- **Artist exclusivity (2.5B)**: `scan_artist_violations()` / `resolve_artist_groups()` in `library/exclusivity.py`; ops + routes `artist-exclusivity`, `resolve-artist-exclusivity`; SSE `artist_exclusivity_report`; Libraries page Artist-exclusivity card (report_only / keep_preferred_library, dry-run + confirm).
- **Create library & move (2.6)**: new `library/extract.py` (script/genre/artist/path-regex/tag filters) + `op_extract_move` + `library_extract_move` route; Libraries "Create library & move" wizard (filters, source libs, dry-run table, confirm → create dir + library + move).
- **Plex rating sync (2.2)**: `metadata.py` gained `rating` (FLAC `RATING` / MP3 `POPM:no@email`); `plex/client.pull_ratings()`; new `plex/sync.py` (`tag_rating=clamp(round(plex*10),0,100)`, `rating_overwrite` default **false**); manual `POST /api/plex/sync-ratings`, `GET /api/plex/sync-status`, 10-min background poll in `app.py`; Plex page "Sync ratings now" + status card; Settings Plex card toggles/interval/overwrite. Mapping documented in Settings/Plex.
- **Fixed pre-existing bug**: `Supervisor.history` property was missing, breaking `/api/jobs/history` (used by all async job UI) — added it in `jobs.py`.
- Files: backend `config.py`, `settings.py`, `jobs.py`, `events.py`, `app.py`, `api.py`, `library/{organizer,metadata,exclusivity,extract}.py`, `tags/editor.py`, `plex/{client,sync}.py`; frontend `App.jsx`, `api.js`, `lib/{themes,sound}.js`, `pages/{Settings,Tools,Libraries,Plex,Tags}.jsx`, `index.css`; asset `frontend/public/sounds/job-done.wav`.
- Verified: backend smoke test passes; new API probe passes (preview, artist-exclusivity, extract dry-run + apply move, sync-status); `npm run build` succeeds.

---

*End of Glacier Stage 2 snapshot & prompt*
