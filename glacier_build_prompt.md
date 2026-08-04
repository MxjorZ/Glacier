# Glacier — Self Hosted Music Library Manager

## Mission

Build **Glacier**, a self-hosted local music library management application.

Glacier is inspired by the visual style of SpotiFLAC but is a completely separate product.

SpotiFLAC is only a UI/UX reference.

Glacier runs like other self-hosted applications:

* Server PC hosts:

  * Glacier backend
  * Glacier frontend
  * music libraries
* Client PCs access Glacier through a browser over LAN.
* Development starts locally with localhost testing.
* Deployment later runs permanently on the server.

Example usage model:

```
Server PC
 ├── Glacier backend
 ├── Glacier frontend
 ├── /mnt/music
 └── /mnt/MusicFolder

Client PC
 └── Browser
      http://server-ip:5050
```

---

# Product Goals

Glacier manages large FLAC/MP3 libraries.

Main functions:

* Manage multiple music library folders.
* Scan and analyze collections.
* Organize files using metadata templates.
* Edit tags.
* Generate covers and playlists.
* Detect duplicates.
* Clean libraries.
* Export reports.
* Integrate with Plex.
* Provide a modern web interface.

The unique Glacier feature:

## Library Exclusivity

A track should only belong to one managed library.

Example:

```
Library A
/mnt/music

Artist - Album - Track.flac


Library B
/mnt/MusicFolder

Artist - Album - Track.mp3
```

Glacier detects this as the same track existing in two libraries.

---

# Deployment Requirements

## Development

Initial development:

```
localhost only
```

Example:

```
http://127.0.0.1:5050
```

After testing:

```
http://SERVER_IP:5050
```

LAN access must work like:

* Lidarr
* Sonarr
* Radarr
* slskd
* DroppedNeedle
* Plex Web

---

# Technology Stack

## Backend

Python 3.11+

Preferred:

* Flask or FastAPI
* mutagen
* optional plexapi

Responsibilities:

* filesystem operations
* metadata processing
* job execution
* SSE events
* settings
* API

---

## Frontend

Modern SPA.

Preferred:

* React
* Tailwind CSS
* Motion animations

Must follow:

`spotiflac_ui.md`

for:

* layout
* sidebar
* themes
* density
* animations

---

# Backend Features

Keep useful Songanizer functionality.

## Library Management

Users choose folders manually.

Example:

```
Libraries:

Main FLAC Archive
/mnt/music


Secondary Archive
/mnt/MusicFolder
```

Required:

* add library
* remove library
* rename library
* browse folders
* scan libraries
* show statistics

Do not hardcode paths.

---

# Required Operations

## Analyze

Scan all libraries.

Show:

* tracks
* artists
* albums
* file sizes
* formats
* folder statistics

---

## Organize

Move/rename files based on metadata.

Example:

Folder:

```
{albumartist}/{album} ({year})
```

Filename:

```
{artist} - {album} - {track} - {title}
```

Must support:

* dry run
* preview
* confirmation
* selected library target

---

## Duplicate Management

Two separate systems:

### In-library duplicates

Same library contains duplicates.

### Cross-library duplicates

Same track exists in different libraries.

---

# Library Exclusivity

## Identity matching

Priority:

1. ISRC
2. Artist + Title + Album
3. Artist + Title
4. Filename fallback (report only)

Normalization:

* lowercase
* remove punctuation
* remove feat/ft noise
* collapse spaces

---

## Default behavior

Never delete automatically.

Default:

```
REPORT ONLY
```

Resolution options:

* keep preferred library
* keep best quality
* keep newest
* move loser
* quarantine

Every destructive operation requires:

* dry run
* confirmation
* count display

---

# Remove From Original Scope

Not required for v1:

* AI music discovery
* phone/device synchronization
* mobile applications
* downloader functionality

---

# Keep From Original Backend

Required:

* SSE progress system
* tag editor
* Plex integration
* reports
* covers
* playlists
* cleanup tools
* settings import/export
* folder browser

---

# Self Hosted Requirements

The application must:

* bind configurable host/port
* support LAN access
* have persistent settings
* survive restart
* show running jobs
* expose logs
* never silently modify files

---

# Implementation Order

1. Backend skeleton
2. Settings system
3. Library management
4. SSE event system
5. Job supervisor
6. Library exclusivity engine
7. Duplicate tools
8. Organize system
9. Tag editor
10. Cleanup tools
11. Plex
12. Frontend shell
13. Connect UI and API
14. Deployment documentation

---

# Final Requirement

Create a working application, not a mockup.

Do not generate placeholder UI without backend logic.

Every button shown in the UI must connect to a real API operation.
