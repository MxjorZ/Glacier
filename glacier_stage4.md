# Glacier Development Roadmap

## Overview

This document outlines the next major improvements planned for Glacier. The focus is on improving usability, reliability, performance, and transparency while making the application significantly more beginner-friendly.

---

# 1. Concurrent Background Jobs

## Goal

Remove the current limitation that prevents multiple background tasks from running simultaneously.

## Current Issue

The application displays an error similar to:

> "Another job is already running."

This prevents users from performing independent operations at the same time.

## Expected Behaviour

Implement a proper background job queue that supports multiple concurrent jobs.

Examples:

* Scan Library A while Plex Rating Sync is running.
* Organize one library while another library is being scanned.
* Refresh metadata while another task is processing.

Each task should have:

* Independent progress
* Independent logs
* Independent status
* Independent cancellation (future support)

The application should never block unrelated operations because another task is already active.

---

# 2. Global Error Center

## Goal

Create a centralized error reporting system.

## Current Issue

Errors are only visible inside Docker logs or Portainer.

Most users never look there.

## Expected Behaviour

Add an Error Center accessible from the application's context menu.

Every error should automatically appear there.

Each entry should include:

* Timestamp
* Error title
* Detailed error message
* Stack trace (expandable)
* Source module
* Severity

Allow:

* Copy Error
* Clear Errors
* Export Errors

Errors should remain available until manually cleared.

---

# 3. Universal Progress System

## Goal

Provide complete visibility into background activity.

## Expected Behaviour

Create a floating progress panel that is always visible.

The panel should display:

* Current task
* Current stage
* Percentage complete
* Estimated remaining time (ETA)
* Current processing speed
* Current item count
* Total item count

Example:

Scanning Library...
███████████░░░░░░░░
58%

19,320 / 33,182 tracks

Estimated Time Remaining:
4 minutes 12 seconds

This system should automatically work for:

* Library scans
* Organizing
* Metadata updates
* Plex sync
* Genre operations
* Tag editing
* Future background jobs

The same information should also appear inside the application's log panel.

---

# 4. Per-Library Operations

## Goal

Every operation should work on individual libraries instead of globally.

## Current Issue

Many actions affect every loaded library.

## Expected Behaviour

Operations should always allow selecting:

* Library A
* Library B
* Multiple libraries
* All libraries

Examples:

* Rescan selected library
* Organize selected library
* Update metadata for selected library
* Refresh artwork for selected library

Users should never be forced to rescan every library.

---

# 5. Automatic Startup Scan

## Goal

Quickly detect library changes when Glacier starts.

## Expected Behaviour

Store an indexed database of every library.

On startup:

* Load stored database
* Perform a fast change detection
* Detect:

  * New files
  * Deleted files
  * Modified metadata
  * Renamed files

Avoid full rescans whenever possible.

Only changed files should be processed.

This should greatly improve startup speed.

---

# 6. Improve Library Configuration

## Goal

Make the Library settings understandable for beginners.

## Current Issue

Terms like:

* Preferred Library
* Move Target

are confusing.

## Expected Behaviour

Replace technical terminology with beginner-friendly language.

Every setting should include:

* Plain language explanation
* Tooltip
* Example

Example:

Instead of:

Preferred Library

Use:

Primary Music Library

"This library will be used as the default destination whenever Glacier needs to move or organize music."

---

# 7. Improve "Create Library & Move"

## Goal

Simplify the workflow.

## Current Issues

The feature is difficult to understand.

Some fields appear mandatory even when they should be optional.

Especially:

* Filters

## Expected Behaviour

Clearly separate:

Required Fields

Optional Fields

Only require information that is actually necessary.

Provide validation messages explaining exactly what is missing.

---

# 8. Better Recent Operations

## Goal

Improve operation history.

## Current Issue

Entries only display generic completion messages.

Example:

Plex Rating Sync Complete

## Expected Behaviour

Each operation should record:

* Timestamp
* Operation
* Library
* Result
* Duration

Timestamp format:

DD/MM/YYYY HH:mm

If today:

Today 21:35

If yesterday:

Yesterday 18:42

Examples:

Today 20:12

Library Scan Completed

Yesterday 17:54

Plex Rating Sync Completed

05/08/2026 11:32

Metadata Refresh Completed

---

# 9. Genre Manager

## Goal

Provide bulk genre management.

## Expected Behaviour

Load every genre used across the selected library.

Examples:

Rock

Metal

Blues

Jazz

Folk

Funk

Pop

Hip-Hop

Display:

Genre

Track Count

Album Count

Artist Count

Allow:

* Delete genre from selected tracks
* Replace genre
* Merge genres
* Bulk edit genres

---

# 10. Large-Scale Tag Editor

## Goal

Efficiently edit metadata for large collections.

## Expected Behaviour

Load tracks using pagination.

Options:

20

50

100

tracks per page.

Only load the currently visible page.

Support:

* Queue-style browsing
* Multi-selection
* Bulk editing
* Metadata editing
* Artwork viewing
* Sorting
* Filtering

This improves both usability and performance.

---

# 11. Date & Time Standardization

## Goal

Use one consistent format throughout the application.

## Expected Behaviour

Use:

DD/MM/YYYY HH:mm:ss

24-hour clock.

Example:

Current:

8/5/2026, 9:50:58 PM

Desired:

05/08/2026 21:50:58

Apply this consistently across:

* Logs
* Recent operations
* History
* Metadata views
* Notifications
* Tooltips

---

# 12. Plex Rating Sync Toggle

## Goal

Simplify configuration.

## Expected Behaviour

Replace the current configuration with a simple boolean toggle.

Enabled

Disabled

The option should be immediately understandable without additional configuration.

---

# 13. Plex Library Statistics

## Goal

Expand the Plex integration.

## Expected Behaviour

Automatically detect all music libraries available on the connected Plex server.

Display each library separately.

Example:

Music

Music YouTube

Each section should display Plex's statistics directly from the server:

* Total Tracks
* Total Artists
* Total Albums

These values should reflect Plex's database rather than the local Glacier library index.

---

# 14. Floating Log Console

## Goal

Replace the current logging experience.

## Expected Behaviour

Create a docked footer that stays attached to the bottom of the application.

Features:

* Always accessible
* Resizable
* Collapsible
* Floating
* Highest z-index
* Adjustable opacity

Log categories:

* All — White
* Info — Light Gray
* Success — Green
* Warning — Yellow/Orange
* Error — Red
* Connected — Green
* Disconnected — Red
* Progress — Orange

Include:

* Search
* Filter by category
* Copy selected logs
* Download logs
* Auto-scroll toggle

---

# 15. Remove Duplicate Organization Settings

## Goal

Avoid duplicate functionality.

## Current Issue

The organization feature exists in both:

* Settings
* Tools

## Expected Behaviour

Keep Organization exclusively inside the **Tools** section.

Remove it from Settings to eliminate confusion and avoid conflicting configuration locations.

---

# 16. Enhanced UI Animations

## Goal

Provide a more customizable and polished user experience.

## Expected Behaviour

Expand the application's animation system.

Support multiple animation presets.

Examples:

* Minimal
* Modern
* Material
* Smooth
* Fast
* Playful

Allow customization of:

* Animation speed
* Hover animations
* Click animations
* Transition duration
* Easing style
* Enable/disable individual animations

All animation settings should be configurable from the application's Settings page.

---

# Design Principles

Every future feature should follow these principles:

* Beginner-friendly and self-explanatory.
* Avoid technical jargon where possible.
* Keep long-running tasks asynchronous and non-blocking.
* Provide continuous feedback during background operations.
* Prioritize performance with large music libraries.
* Maintain consistent UI, terminology, and formatting across the entire application.

---

# Stage 4 — Implementation Status

Legend: `[x]` complete · `[~]` partial / adapted · `[ ]` not started.

## 1. Concurrent Background Jobs — `[x]`
- The job supervisor (`jobs.py`) already ran jobs concurrently; it was confirmed
  with `probe_concurrency.py` (two jobs at once, no reject) and the Plex rating
  timer no longer blocks on `supervisor.running()` (see `app.py`).
- Each job keeps independent progress, logs and status (SSE events are keyed by
  `job_id`; the dock shows one card per running job).

## 2. Global Error Center — `[x]`
- New `glacier_backend/errors.py`: a persistent error store (`~/.glacier_errors.json`)
  with timestamp, title, message, source module, severity, job id and an
  expandable stack trace. Entries persist until the user clears them.
- Job failures automatically record into the store (`jobs.py` supervisor).
- API: `GET/POST/DELETE /api/errors` + `GET /api/errors/export`.
- UI: new **Error Center** page (`pages/Errors.jsx`) with Copy / Clear / Export
  and a severity filter; reachable from the title-bar error bell and the new
  right-click **context menu** (`App.jsx`).

## 3. Universal Progress System — `[x]`
- `ActivityDock.jsx` reworked: every running job shows task, stage label,
  percentage, ETA, live speed (items/sec) and current/total in a docked footer
  at the highest z-index.
- Progress also lands in the log console as a "Progress" category (useSSE adds a
  throttled line at ~10% buckets and completion).
- Backend `events.progress()` already carried `job_id`/`ts`, which drives the ETA
  and speed calculations client-side.

## 4. Per-Library Operations — `[x]`
- Backend ops accept `library_ids`: `op_analyze` / `op_quick_scan`,
  `op_exclusivity`, `op_artist_exclusivity`, `op_artist_resolve`,
  `op_resolve` (plus the `genres` ops which always pass a library).
- Dashboard has an "All libraries / <library>" selector for Scan and Quick scan.
  Organize/Duplicates/Covers/Playlists/Report already operated per-library via
  the per-page selector; Genres operates on a selected library.
- Note: track/artist exclusivity are inherently cross-library, so they scan the
  enabled libraries together (backend still accepts an explicit scope).

## 5. Automatic Startup Scan — `[x]`
- Scanner cache now stores a per-file index (path → size/mtime) so `detect_changes`
  / `quick_scan` can detect new / modified / deleted / renamed files and re-read
  only the changed ones, dropping stale entries.
- On startup (`app.py`) a background "Startup scan" job runs ~20s after launch;
  a manual trigger is Dashboard → Quick scan / `POST /api/run/quick-scan`.

## 6. Improve Library Configuration (terminology) — `[x]`
- Settings: "Preferred library" → **Primary Music Library** with a plain-language
  explanation; Plex rating sync simplified to a boolean toggle with helper text;
  required fields in "Create library & move" are labelled and validated.

## 7. Improve "Create Library & Move" — `[x]`
- `Libraries.jsx` extract modal separates required fields, marks the required
  inputs, and shows inline validation errors (name, destination path, at least
  one source library).

## 8. Better Recent Operations — `[x]`
- New `glacier_backend/operations.py` (`~/.glacier_operations.json`) records each
  finished job with timestamp, operation, library, status, duration and result.
- API `GET /api/operations`. Dashboard "Recent operations" shows friendly names,
  `Today HH:mm` / `Yesterday HH:mm` / `DD/MM/YYYY HH:mm` plus duration.

## 9. Stage 4 — Follow-up fixes `[x]`

After the initial Stage 4 implementation a few issues were found and fixed:

- **FileExplorer `onKeyDown` crash** — `FileExplorer.jsx` referenced an undefined
  `onKeyDown` handler on the file-list scroll container, which caused a runtime
  `ReferenceError` on every page that mounted the file explorer (Libraries and
  Tags). Fixed by implementing a proper keyboard-navigation handler (ArrowUp/Down
  cycles a highlight, Enter opens a folder, Space toggles selection, Backspace
  goes up a level, Escape closes) and passing a `focused` prop to the grid/list
  items for visual feedback.

- **Dashboard auto‑analyze on every page refresh** — `Dashboard.jsx` had an
  unconditional `useEffect` that called `analyze(false)` on mount, starting a
  full library scan every time the page loaded (including plain browser
  refreshes). Replaced with a cached `GET /api/stats` endpoint that aggregates
  the persisted inventory cache without re‑reading files. The dashboard now
  loads instant stats on mount and only runs a scan when the user explicitly
  clicks Scan / Quick scan.

- **Job termination** — Added `POST /api/jobs/<id>/terminate` and a cooperative
  cancellation mechanism (`glacier_backend/cancel.py`) using a per‑job
  `threading.Event`. The job supervisor catches `JobCancelled` and records the
  job as `cancelled` in the history. Long‑running scan loops in the scanner
  (`scan_library`, `quick_scan`) check the flag every 10 files. The
  `ActivityDock` now shows a right‑click context menu on each running job card
  with a **Terminate job** option.

- **„New library” missing `enabled` flag** — `store.add_library()` did not
  include the `enabled` field, causing the raw API response to omit it (the
  frontend used `?? true` as a fallback, so it was only a cosmetic issue).
  Fixed by setting `"enabled": True` on creation.
