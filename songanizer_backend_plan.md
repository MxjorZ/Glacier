# Glacier Backend Architecture Plan

## Purpose

This document defines the backend requirements for **Glacier**, the replacement application for the previous Songanizer Pro backend.

Glacier keeps the proven backend capabilities from `rebuild_music.py`:

* Flask-based local API
* Mutagen audio processing
* Multi-library management
* SSE live progress events
* Tag editing
* Organization tools
* Duplicate detection
* Cleanup tools
* Plex integration
* Settings management

The old embedded HTML interface is removed completely.

Glacier becomes a proper self-hosted application similar in operation style to:

* Lidarr
* slskd
* DroppedNeedle
* Plex-style local services

The backend runs on the server machine where the music files exist.

---

# Deployment Model

## Development phase

Initial development:

```
Server PC
 ├── Glacier backend
 ├── Glacier frontend
 └── Music libraries
```

Access:

```
http://localhost:5050
```

Testing is performed directly on the server.

---

## Final deployment

The server becomes the permanent host:

```
Server PC
 ├── Glacier API
 ├── Glacier Web UI
 ├── /mnt/music
 └── /mnt/MusicFolder
```

Client PC accesses:

```
http://SERVER_IP:5050
```

Example:

```
http://192.168.x.x:5050
```

The application should behave like any self-hosted service:

* LAN accessible
* configurable port
* no dependency on the client machine
* all filesystem operations happen on the server
* browser is only the control interface

---

# Supported Libraries

Glacier manages user-defined music libraries.

Example:

```json
{
  "libraries": [
    {
      "id": "main",
      "name": "Main Music Library",
      "path": "/mnt/music"
    },
    {
      "id": "secondary",
      "name": "Secondary Music Library",
      "path": "/mnt/MusicFolder"
    }
  ]
}
```

The user can add, remove, and rename libraries.

The application must not assume fixed paths.

The two current mounted libraries are only defaults.

---

# Removed Features

The following Songanizer features are removed:

## Phone/device integration

Removed:

* phone synchronization
* mobile library assumptions
* phone-specific workflows

Glacier manages server-side libraries only.

---

## AI Discovery

Removed:

* OpenAI music recommendations
* Gemini discovery
* Claude discovery
* external recommendation workflows

Future versions may reintroduce this as an optional plugin.

---

# Core Backend Stack

## Required

Python:

```
Python 3.11+
```

Framework:

```
Flask
```

Libraries:

```
mutagen
flask-cors
```

Optional:

```
plexapi
```

---

# Backend Structure

Recommended layout:

```
glacier/
│
├── backend/
│   ├── app.py
│   ├── config.py
│   ├── settings.py
│   ├── events.py
│   ├── jobs.py
│   │
│   ├── library/
│   │   ├── scanner.py
│   │   ├── organizer.py
│   │   ├── duplicates.py
│   │   └── exclusivity.py
│   │
│   ├── tags/
│   │   └── editor.py
│   │
│   ├── plex/
│   │   └── client.py
│   │
│   └── reports/
│       └── exporter.py
│
├── frontend/
│
├── requirements.txt
└── glacier.py
```

---

# Settings System

Settings location:

```
~/.glacier_settings.json
```

Example:

```json
{
  "libraries": [
    {
      "id": "main",
      "name": "Main Library",
      "path": "/mnt/music"
    },
    {
      "id": "secondary",
      "name": "Secondary Library",
      "path": "/mnt/MusicFolder"
    }
  ],

  "extensions": [
    ".flac",
    ".mp3"
  ],

  "excluded_folders": [
    "Playlists"
  ],

  "folder_pattern": "{albumartist}/{album} ({year})",

  "naming_pattern": "{artist} - {album} - {track:02d} - {title}",

  "dup_priority": "flac",

  "theme": "glacier",

  "theme_mode": "auto",

  "plex_url": "",
  "plex_token": ""
}
```

---

# Event System

Glacier uses Server Sent Events.

Endpoint:

```
GET /api/events
```

Events:

```json
{
  "type": "progress",
  "current": 500,
  "total": 20000,
  "label": "Scanning files"
}
```

Supported events:

## connected

Client connected.

---

## log

Example:

```json
{
"type":"log",
"level":"info",
"message":"Scanning library"
}
```

Levels:

```
info
success
warning
error
```

---

## progress

Used for:

* scans
* organizing
* duplicate detection
* cleanup

---

## done

Every job must end with:

```json
{
"type":"done",
"message":"Operation complete"
}
```

---

# Job Manager

All heavy operations use one job supervisor.

Rules:

* Only one filesystem-heavy operation runs at once.
* UI receives running state.
* New jobs are rejected while another job runs.
* Every job has:

  * id
  * operation
  * start time
  * status
  * result

Example:

```
ID: 1234
Operation: analyze
Status: running
```

---

# Required API

## Settings

```
GET /api/settings

POST /api/settings
```

---

## Libraries

```
GET /api/libraries

POST /api/libraries

DELETE /api/libraries/<id>
```

---

## Directory browser

```
POST /api/list-dir
```

Used for selecting folders.

---

# Library Operations

## Analyze

Endpoint:

```
POST /api/run/analyze
```

Scans all libraries.

Returns:

* total files
* artists
* albums
* size
* extensions
* library counts

---

## Organize

```
POST /api/run/organize
```

Must require:

```json
{
"library_id":"main",
"dry_run":true
}
```

Never silently chooses the first folder.

---

## Duplicate detection

Two types:

### Internal duplicates

Same library:

```
/mnt/music/album/song.flac
/mnt/music/old/song.flac
```

---

### Cross-library duplicates

Same identity:

```
/mnt/music/song.flac
/mnt/MusicFolder/song.mp3
```

---

# Library Exclusivity

This is Glacier's main feature.

A song identity may exist in only one library.

Identity priority:

1. ISRC
2. Artist + Title + Album
3. Artist + Title
4. Filename fallback (report only)

Example violation:

```
Track:
Daft Punk - Something About Us

Found:

Main Library
/mnt/music/Daft Punk/Discovery/05.flac

Secondary Library
/mnt/MusicFolder/Daft Punk/05.mp3
```

Result:

```json
{
"type":"exclusivity_report",
"violations":1
}
```

---

# Exclusivity Resolution

Policies:

```
report_only
keep_best_quality
keep_preferred_library
move_to_library
```

All destructive actions require:

1. dry-run
2. count confirmation
3. explicit execution

Never automatically delete.

---

# Tag Management

Supported:

FLAC:

* artist
* albumartist
* album
* title
* track
* date
* genre

MP3:

* ID3 equivalents

Routes:

```
POST /api/tag-list

POST /api/tag-read

POST /api/tag-save
```

---

# Cleanup Tools

Required:

## Empty folders

```
clean_empty
```

---

## Duplicate folder shells

```
clean_dup_fold
```

---

## Missing tags

```
missing_tags
```

---

## Corrupt files

```
corrupt
```

---

# Covers

Operations:

```
covers
rebuild_covers
```

Functions:

* extract embedded artwork
* create cover files
* rebuild album folders

---

# Playlists

Generate:

```
.m3u
```

Per album folder.

Include:

* title
* duration
* bitrate

---

# Reports

Generate:

* JSON report
* text report

Includes:

* library statistics
* file inventory
* problems

---

# Plex Integration

Keep:

* statistics
* search
* ratings
* duplicate reports

Remove:

* automatic destructive actions

Required:

```
plex_stats

plex_search

plex_rate

plex_duplicates
```

---

# Security

Initial:

LAN trusted environment.

Later:

Optional:

* API token
* HTTPS reverse proxy
* authentication

Never expose publicly without protection.

---

# Backend Quality Requirements

Every operation must:

* support multiple libraries
* stream progress
* survive individual file failures
* provide structured results
* avoid silent destructive actions
* be restart safe

---

# Final Goal

Glacier should become:

A self-hosted music library management server that runs permanently on the user's server machine, manages multiple music libraries, organizes and cleans collections, and guarantees that the same track does not exist in multiple managed libraries.
