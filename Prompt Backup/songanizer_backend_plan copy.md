# Songanizer Pro Backend — Execution & Upgrade Planning Guide

> **Purpose:** Dense architectural blueprint of the working backend in `rebuild_music.py`, plus a plan to run it **better** under a new UI (e.g. SpotiFLAC-style shell) without rewriting application code in this document.  
> **Source:** Flask localhost app, SSE progress bus, mutagen tag layer, multi-folder library ops, AI discovery, Plex, Windows startup.  
> **Scope:** Inventory what exists, what is incomplete or fragile, how the API contract works, and how to operationalize it more reliably for the new app.

---

## 0. System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Browser / New UI  (localhost or LAN)                                   │
│    HTTP JSON  +  Server-Sent Events (/api/events)                       │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────┐
│  Flask app (host 0.0.0.0 : 5050, threaded)                              │
│    Routes: settings, folders, run/<op>, tags, genres, network, startup  │
│    Global: _events Queue · _processing lock · _genre_candidates         │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
  Filesystem ops          mutagen (FLAC/MP3)      External services
  (Path, shutil,          tag read/write          OpenAI / Gemini /
   rglob, rename)         cover extract           Claude / Plex API
```

**Runtime model**

| Concern | Current behavior |
|---------|------------------|
| Process model | Single Python process; long ops in daemon threads |
| Concurrency | One heavy op at a time (`_processing` + `_lock`) |
| Progress | SSE event stream; client never polls job status |
| Config | `~/.songanizer_settings.json` merged over `DEFAULT_SETTINGS` |
| UI coupling | Monolithic `HTML` string embedded in the same file |

**Dependencies**

- Required: `flask`, `mutagen`
- Optional: `plexapi` (Plex ops degrade with clear error if missing)
- Stdlib: `urllib`, `threading`, `queue`, `socket`, `winreg` (Windows startup only)

---

## 1. Settings Contract

**File:** `Path.home() / ".songanizer_settings.json"`

### 1.1 Schema (canonical keys)

| Key | Type | Role |
|-----|------|------|
| `folders` | `string[]` | Multi-root music library paths |
| `extensions` | `string[]` | e.g. `.flac`, `.mp3` |
| `excluded_folders` | `string[]` | Subpath name fragments to skip |
| `folder_pattern` | string | Dest folder template |
| `naming_pattern` | string | Dest filename template |
| `backup_before_move` | bool | `.bak` copy before rename |
| `auto_playlist` | bool | Run playlist gen after organize |
| `log_to_file` / `log_path` | bool / path | File logging (declared; weak usage) |
| `dup_priority` | `deluxe` \| `flac` \| `largest` | Keep-winner rule for dupes |
| `cover_format` | `png` \| `jpg` | Cover export extension |
| `accent1` / `accent2` / `glow_opacity` | UI-only | Theme (new UI can ignore) |
| `openai_key` / `gemini_key` / `claude_key` | string | AI credentials |
| `ai_providers` | `string[]` | Ordered preference list |
| `genres_to_remove` | `string[]` | Staged genre purge list |
| `protected_artists` / `protected_albums` / `protected_songs` | `string[]` | Genre-delete exemptions |
| `ai_genre_filter` / `ai_artist_filter` | `string[]` | Discovery filters (settings fallback) |
| `plex_url` / `plex_token` / `plex_music_section` | string | Plex connection |
| `plex_target_rating` | float | Default rating (e.g. 10.0) |

### 1.2 Load/save rules

- `_load()`: read JSON → merge onto defaults (missing keys filled).
- `_save(d)`: full overwrite write; no schema validation, no secret redaction on disk.
- Export route strips secrets for download; import merges into current settings.

### 1.3 Template variables for organize

**Folder pattern defaults:** `{albumartist}/{album} ({year})`  
**Naming pattern defaults:** `{artist} - {album} - {track:02d} - {title}`

Available tokens: `artist`, `albumartist`, `album`, `year`, `track` (int), `title`.  
Hebrew-aware path: if tags contain Hebrew, `_normalize_hebrew_artist` prefers Hebrew primary for `albumartist` / `artist` in destination paths.

---

## 2. Event Bus (SSE)

**Endpoint:** `GET /api/events` — `text/event-stream`

### 2.1 Event types emitted by backend

| `type` | Payload fields | When |
|--------|----------------|------|
| `connected` | — | Client attaches |
| `ping` | — | Keepalive ~25s idle |
| `log` | `message`, `level` (`info`/`success`/`warning`/`error`) | All ops |
| `progress` | `current`, `total`, `label` | Scanning / processing |
| `done` | `message` | Op finished (also clears `_processing`) |
| `stats` | `total`, `artists`, `albums`, `size`, `ext_counts`, `folder_counts` | After analyze |
| `discover_results` | `suggestions[]`, `provider` | AI discovery |
| `cross_duplicates` | `duplicates[]`, `check_type` | Cross-folder dup scan |
| `genre_preview` | `count`, `files[]` (sample) | Genre scan (op path; route path returns JSON) |
| `plex_search_results` | `artists[]` | Plex search when not rating |
| `plex_duplicates` | `duplicates[]` | Plex dedup scan |

### 2.2 Progress helpers

```
_emit(t, **kw)
_log(m, lv="info")
_progress(cur, tot, lbl="")
_done(m)   # sets _processing = False
```

Queue max size: **4000**. Overflow risk under very chatty ops is real; plan for client resilience (reconnect) and optional server-side drop-oldest policy later.

### 2.3 Concurrency invariant

`_dispatch` refuses a second heavy job while `_processing` is true.  
**Gap:** several routes start threads **outside** `_dispatch` (`report`, `move_duplicates`, `confirm-genre-remove`) and do not always set/clear `_processing` the same way → overlapping filesystem work is possible.

---

## 3. Audio & Filesystem Core

### 3.1 Tag read (`_read_tags`)

| Format | Library | Fields returned |
|--------|---------|-----------------|
| FLAC | `mutagen.flac.FLAC` | artist, albumartist, title, album, tracknumber, date (year), genre, bitrate=`"FLAC"` |
| MP3 | `mutagen.mp3.MP3` + ID3 frames | same + bitrate as `"NNN kbps"` |

Missing mutagen → all tag ops return `None` / empty; app still boots with warning.

### 3.2 Tag write (`/api/tag-save`)

- FLAC: set Vorbis comments for title/artist/albumartist/album/tracknumber/date/genre.
- MP3: map to `TIT2`, `TPE1`, `TPE2`, `TALB`, `TRCK`, `TDRC`, `TCON`.

**Gaps:** no ISRC/UPC/composer/cover write; no batch save; no dry-run.

### 3.3 File discovery

- `_get_files(folder, settings)` — recursive `rglob` by extension; exclude if excluded name substring appears in path string.
- `_get_all_files(settings)` — union over all `folders`.

**Gaps:** exclusion is substring-based (can over-match); no symlink policy; no ignore of hidden system dirs beyond patterns.

### 3.4 Destination builder (`_build_dest`)

Sanitizes illegal path chars (`<>:"/\|?*`), applies folder + naming patterns, returns `(dest_dir, dest_file)`.

**Hebrew rule:** if artist/albumartist tags contain Hebrew script, normalized Hebrew name drives path components.

### 3.5 Covers & playlists

- `_extract_cover`: FLAC picture type 3 or MP3 `APIC` → write `cover.{png|jpg}` in album folder.
- `_album_folders`: dirs whose name matches year pattern `\(\d{4}\)` or `Unknown Year` and contain audio.
- Playlists: one `.m3u` per album folder with `#EXTINF` duration + bitrate annotation.

---

## 4. Operation Catalog

All heavy ops are designed to stream `log` + `progress` + `done` (and sometimes a structured event).

### 4.1 Library analysis & hygiene

| Op ID | Function | Scope | Output |
|-------|----------|-------|--------|
| `analyze` | `_op_analyze` | **All folders** | Stats event + counts |
| `organize` | `_op_organize` | **First folder only** | Rename/move by tags |
| `various` | `_op_various` | First folder; paths containing “various artists” | Re-home by tags |
| `duplicates` | `_op_dupes` | First folder | Delete losers by priority |
| `covers` | `_op_covers(force=False)` | First folder album dirs | Generate missing covers |
| `rebuild_covers` | `_op_covers(force=True)` | First folder | Overwrite covers |
| `playlists` | `_op_playlists` | First folder | Generate missing M3Us |
| `clean_dup_fold` | `_op_clean_dup_fold` | First folder | Remove year-less empty twin folders |
| `clean_empty` | `_op_clean_empty` | First folder | Remove empty dirs bottom-up |
| `missing_tags` | `_op_missing_tags` | First folder | Report incomplete tags |
| `corrupt` | `_op_corrupt` | First folder | Report unreadable files |
| `report` | `_op_report` | All folders | Text report path |

### 4.2 Genre purge (two-phase)

1. **Preview:** `POST /api/remove-genres` with `{genres: [...]}`  
   - Scans **all folders**, applies protected lists, returns `{count, files[:40]}` and stages full list in `_genre_candidates`.
2. **Confirm:** `POST /api/confirm-genre-remove`  
   - Deletes staged paths via `_op_confirm_remove_genres`.

`_op_remove_genres` exists but is **not fully wired** as a complete delete op (stops at preview emit); the **route path** is the real implementation.

### 4.3 Cross-folder duplicates

| Op / route | Behavior |
|------------|----------|
| `cross_dupes` | Group by filename / tags / metadata / all; emit `cross_duplicates` |
| `move_duplicates` | Body `{moves: [{from, to}, ...]}` — `shutil.move` with name collision suffix |

### 4.4 AI discovery

| Op | Behavior |
|----|----------|
| `discover` | Filter library by optional genre/artist sets → sample ≤10 artists → call first AI provider with key → parse `ARTIST: reason` lines → emit `discover_results` with Tidal/Qobuz/Monochrome search links |

Providers: OpenAI `gpt-4o`, Gemini `gemini-1.5-flash`, Claude `claude-3-haiku-20240307`.  
Filters: prefer request body `filters.genres` / `filters.artists`, else settings filters.

### 4.5 Plex

| Op ID | Behavior |
|-------|----------|
| `plex_rate_all` | Rate every album + track in section to `plex_target_rating` |
| `plex_search` | Search artists by title; if rating > 0 rate first match; else emit search results |
| `plex_dedup` | Group tracks by (title, artist); emit groups (does **not** auto-delete in Plex) |
| `plex_stats` | Count artists / albums / tracks |

Connection: `PlexServer(url, token, timeout=60)`.

### 4.6 Tag editor API

| Route | Method | Role |
|-------|--------|------|
| `/api/tag-list` | POST | List audio files under one folder (defaults first settings folder) |
| `/api/tag-read` | POST | Read tags for one path |
| `/api/tag-save` | POST | Write tags for one path |

### 4.7 Folders & FS browser

| Route | Role |
|-------|------|
| `GET/POST /api/folders` | List / append folder to settings |
| `DELETE /api/folders/<index>` | Remove by index |
| `POST /api/list-dir` | Directory browser (drives on Windows root) |
| `GET /api/files/export` | Export inventory JSON |
| `POST /api/files/import` | Import folder list / file metadata merge |

### 4.8 Network & Windows startup

| Route | Role |
|-------|------|
| `/api/network-info` | LAN IP, port, pair URL, startup flag |
| `/api/startup-install` / `startup-remove` | HKCU Run key `Songanizer` |

---

## 5. HTTP Surface Map (for new UI binding)

```
GET  /                      → legacy HTML (ignore in new UI)
GET  /api/events            → SSE bus
GET  /api/settings          → full settings JSON
POST /api/settings          → merge + save
GET  /api/settings/export   → downloadable JSON (secrets stripped)
POST /api/settings/import   → merge imported JSON
GET  /api/folders
POST /api/folders           body: {folder}
DELETE /api/folders/<i>
GET  /api/files/export
POST /api/files/import
POST /api/list-dir          body: {path}
POST /api/run/<op_id>       body: {settings?, output?, check_type?, query?, moves?}
POST /api/genres
POST /api/artists
POST /api/remove-genres      body: {genres:[]}
POST /api/confirm-genre-remove
POST /api/tag-list | tag-read | tag-save
GET  /api/network-info
POST /api/startup-install | startup-remove
```

**Primary client pattern for the new app**

1. Open SSE once on launch.
2. Load settings + folders.
3. Trigger `POST /api/run/<op>` (or specialized routes).
4. Render `log` / `progress` / structured events until `done`.
5. Gate UI buttons while any job is active (mirror server `_processing`).

---

## 6. Gaps, Bugs & Incomplete Edges (as implemented)

These are **backend facts** the new plan must either work around or schedule as upgrades.

### 6.1 Multi-folder inconsistency

| Op | Uses all folders? |
|----|-------------------|
| analyze, report, genres, artists, remove-genres preview, cross_dupes, discover | Yes |
| organize, various, duplicates, covers, playlists, clean_*, missing_tags, corrupt | **No — first folder only** |

**Plan implication:** new UI must either (a) document “active folder” selection and pass a single root, or (b) treat multi-folder ops as phase-2 and loop `run` per folder client-side until server is fixed.

### 6.2 Genre remove staging

- Candidates live in process memory (`_genre_candidates`). Lost on restart; not multi-client safe.
- Preview sample limited; confirm deletes full staged list.

### 6.3 Concurrency holes

- `report`, `move_duplicates`, genre confirm start threads without uniform `_dispatch` locking.
- No cancel token: once started, ops run to completion (no cooperative cancel).

### 6.4 Duplicate deletion is destructive

- In-folder `duplicates` **unlinks** files immediately after scan—no second confirm at API level (UI confirm only).
- Plex dedup only reports; does not remove media or library entries.

### 6.5 AI discovery limits

- Hard cap 10 artists in prompt; 15 suggestions requested.
- Link targets are third-party search URLs (squid.wtf / monochrome), not authenticated download APIs.
- Single provider used (first with key), not multi-engine ensemble despite multi-select UI.

### 6.6 Tag / format coverage

- Only FLAC + MP3.
- Album folder detection depends on `(YYYY)` or `Unknown Year` in folder name—pre-organized libraries may miss covers/playlists.
- Progress counters in analyze sometimes use fragile file ordering (`x <= f`).

### 6.7 Security / deployment

- Binds `0.0.0.0` with **no auth** — intentional for LAN pairing, risky on hostile networks.
- API keys stored plaintext in home JSON.
- Path operations trust client-supplied paths (tag-save, move, list-dir).

### 6.8 UI/backend entanglement

- Entire frontend is an `HTML` constant in the same module—new UI should treat `/` as disposable and speak only `/api/*`.

---

## 7. Execution Plan for the New App (No Code — Operational Blueprint)

### Phase A — Treat current backend as a stable API

1. **Detach UI:** run `rebuild_music.py` as API-only server; never depend on embedded HTML.
2. **Session bootstrap:** `GET settings` → `GET folders` → open SSE → optional `network-info` for LAN badge.
3. **Job UX contract:**  
   - Disable destructive actions while waiting for `done`.  
   - Map SSE `log.level` to toast/log pane (parity with SpotiFLAC toast levels).  
   - Progress bar = `current/total`; ETA can be client-side.
4. **Settings drawer:** bind only functional keys; drop accent/glow or map them to the new theme system independently.
5. **Folder management:** use folder CRUD + `list-dir` browser; keep multi-root list visible always.

### Phase B — Feature surfaces mapped to SpotiFLAC-style pages

| New UI page / panel | Backend capability to drive it |
|---------------------|--------------------------------|
| Dashboard / Home | `analyze` + live stats event; log stream |
| Library tools | organize, covers, playlists, clean_*, missing_tags, corrupt |
| Cleanup | duplicates, cross_dupes + move_duplicates, genre purge two-step |
| Discover | `discover` + filters via genres/artists endpoints |
| Plex | plex_stats, plex_search, plex_rate_all, plex_dedup |
| Tags / File manager | tag-list / tag-read / tag-save |
| Settings | settings GET/POST/export/import |
| Support / Pairing | network-info + startup install/remove |

### Phase C — Safer execution policies (behavioral, not code in this doc)

1. **Confirm matrix**
   - Soft: analyze, missing_tags, corrupt, covers, playlists, plex_stats, discover  
   - Hard: organize, duplicates, genre confirm, move_duplicates, plex_rate_all  
2. **Active folder strategy** until multi-folder parity exists:  
   - UI selects “target folder” for first-folder ops; still analyze across all.  
3. **Genre purge:** always show count + sample → explicit confirm → only then call confirm endpoint.  
4. **Never auto-run** destructive ops on startup.  
5. **SSE reconnect:** on `error`/close, reopen EventSource; show “reconnecting” without assuming job died.

### Phase D — Backend upgrade priorities (ordered backlog)

When improving the Python side later, prioritize in this order:

1. **Unify multi-folder** for organize/dupes/covers/playlists/clean (loop all roots or accept `folder` parameter).  
2. **Single job supervisor:** all long work through `_dispatch`; add `cancel` flag checked in loops.  
3. **Dry-run mode** for organize, duplicates, genre remove (return planned actions without mutating).  
4. **Persist job results** (last analyze stats, last dup groups) to disk for UI reload.  
5. **Auth gate** optional token for non-localhost access.  
6. **Expand formats** (m4a/alac/wav/opus) if new UI promises broader library support.  
7. **Album detection** independent of `(year)` folder naming (tag-based grouping).  
8. **Secrets:** store API keys via OS keychain or env vars; never export them.  
9. **Plex dedup:** optional delete/keep policy with explicit confirmation payload.  
10. **AI:** multi-provider merge, larger artist samples, rate-limit handling, structured JSON responses instead of regex line parse.

### Phase E — Quality bars for “better than previous app”

| Bar | Measure |
|-----|---------|
| Observability | Every op emits start log, progress ≥ N steps, terminal `done` or error `done` |
| Idempotence | Re-run covers/playlists skips existing; organize no-ops if already at dest |
| Recoverability | Failed file does not abort entire batch; per-file error logs |
| Predictability | Same settings + library → same organize destinations (Hebrew rules documented) |
| Safety | Two-phase for deletes; backups optional but visible; no silent unlinks from new UI |
| Responsiveness | SSE keeps UI live; button states track server job flag |
| Completeness | UI never offers an op that only works on folder[0] without labeling it |

---

## 8. Recommended Client State Machine

```
[Idle]
  │ run op
  ▼
[Running] ←── SSE: log, progress, intermediate events
  │
  ├─ done (success message) → [Idle] + refresh stats if analyze
  ├─ done (error message)   → [Idle] + error toast
  └─ SSE drop               → [Reconnecting] → resume or mark unknown
```

**Derived UI flags**

- `jobActive`: true between accepted `POST /api/run/...` and next `done` (or timeout policy).
- `libraryLoaded`: `folders.length > 0`.
- `plexConfigured`: non-empty `plex_token`.
- `aiConfigured`: any provider key present for selected providers.

---

## 9. Data Shapes the New UI Must Handle

### 9.1 Discover suggestion

```
{ artist, reason, tidal, qobuz, mono }
```

### 9.2 Cross-duplicate group

```
{ key, count, items: [{ path, name, folder, size, ext }] }
```

### 9.3 Stats event

```
{ total, artists, albums, size, ext_counts, folder_counts }
```

### 9.4 Genre preview response

```
{ count, files: string[] }  // sample; full list staged server-side
```

### 9.5 Plex search result

```
{ artists: [{ title, albums }] }
```

---

## 10. Mapping to SpotiFLAC-Style Shell (Integration Intent)

Without implementing UI code, align **roles**:

| SpotiFLAC shell concept | Songanizer backend role |
|-------------------------|-------------------------|
| Fixed sidebar pages | Dashboard, Tools, Cleanup, Discover, Plex, Tags, Settings, Pairing |
| Title-bar status | LAN IP / job running / folder count |
| SSE/progress toast | Map `progress` + `done` to floating progress + Sonner-like toasts |
| Settings page | Patterns, extensions, protections, AI keys, Plex, dup priority |
| Destructive confirm dialogs | genre confirm, duplicates, organize |
| Log / debug page | SSE `log` ring buffer export |

The **backend remains the source of truth** for filesystem mutations; the new UI is a stricter, clearer operator console.

---

## 11. What Was Already Strong (Keep)

- Multi-folder library concept and folder CRUD.
- SSE progress model (correct direction for long scans).
- Two-phase genre deletion with protection lists.
- Cross-folder duplicate detection + selective move.
- Template-based organize with sanitization + Hebrew preference.
- Plex rating + stats + search scaffolding.
- Settings export/import and file list export/import.
- LAN pairing + optional Windows auto-start.

## 12. What Felt Unfinished (Fix via Plan Above)

- First-folder-only ops vs multi-folder marketing.
- Genre op function vs route duplication.
- No job cancel, uneven locking.
- Destructive dup delete without server-side dry-run.
- AI discovery as “links out” rather than integrated acquisition.
- Plex dedup report-only.
- Embedded legacy UI competing with API clarity.
- Plaintext secrets and open bind without auth.

---

## 13. Success Criteria for the New App Using This Backend

1. User can add multiple roots, analyze all, and see live stats without using the old HTML.  
2. Every destructive action requires an explicit UI confirm and surfaces counts before mutation.  
3. Organize/covers/playlists behavior is labeled with the active target folder until multi-folder is unified.  
4. Discover and Plex panels never crash the UI when keys/token missing—backend error logs map to toasts.  
5. SSE outage does not corrupt library state; at worst job status becomes “unknown” until next `done` or restart.  
6. Settings round-trip (export → import) restores operational config without requiring the old theme keys.

---

*End of planning document. No application code included—execution blueprint only.*
