# Glacier UI Blueprint

## Purpose

This document defines the visual system for Glacier.

Glacier is a self-hosted music library manager.

The UI style is inspired by SpotiFLAC:

* desktop-like density
* icon sidebar
* modern dark/light themes
* compact controls
* live operation feedback

Do not copy SpotiFLAC branding.

Product name:

```
Glacier
```

---

# Application Layout

Desktop-first web application.

Minimum supported viewport:

```
1024x600
```

Layout:

```
+------------------------------------------------+
|                 Top Bar 40px                   |
+----+-------------------------------------------+
|    |                                           |
| S  |                                           |
| i  |              Main Content                 |
| d  |                                           |
| e  |                                           |
|    |                                           |
|56px|                                           |
+----+-------------------------------------------+
```

---

# Main Shell

Root:

```
height: 100vh
overflow: hidden
```

Components always mounted:

* Sidebar
* TopBar
* Main content
* Toast system
* Job progress indicator

---

# Sidebar

Width:

```
56px
```

Position:

```
fixed left
full height
```

Style:

* icon only
* tooltips on hover
* compact spacing
* active page highlight

Navigation:

```
Dashboard
Libraries
Tools
Cleanup
Tags
Plex
Logs
Settings
About
```

---

## Sidebar States

Active:

```
background: primary / 10%
color: primary
```

Inactive:

```
ghost button
hover primary tint
```

Button size:

```
40x40
```

---

# Top Bar

Height:

```
40px
```

Contains:

Left:

```
Glacier status
```

Right:

```
server IP
job status
settings/menu
```

Style:

* blurred background
* subtle border
* compact controls

---

# Content Area

Offset:

```
left: 56px
top: 40px
```

Padding:

```
16px
```

Large screens:

```
32px
```

---

# Page Width Rules

Wide pages:

```
width: 100%
```

Examples:

* Dashboard
* Libraries
* Tools
* Logs
* Tags

Narrow pages:

```
max-width: 900px
```

Examples:

* Settings
* About

---

# Pages

## Dashboard

Purpose:

Library overview.

Show:

* total tracks
* artists
* albums
* storage usage
* recent operations
* quick actions

---

## Libraries

Main Glacier feature page.

Contains:

Library cards:

```
Name
Path
Track count
Size
Last scan
```

Actions:

* Add library
* Scan
* Remove
* Open folder

Exclusivity section:

```
Scan Library Exclusivity
```

Results:

```
Track identity
Library A
Library B
Suggested keeper
Action
```

---

## Tools

Operations:

* Organize
* Generate covers
* Generate playlists
* Missing tags
* Corrupt files
* Reports

---

## Cleanup

Operations:

* Duplicate scan
* Cross-library duplicate scan
* Empty folder cleanup
* Duplicate folder cleanup
* Genre cleanup

All destructive operations require:

1. preview
2. count
3. confirmation

---

## Tags

Features:

* browse files
* read tags
* edit tags
* save tags

Supported:

* FLAC
* MP3

---

## Plex

Features:

* connection status
* statistics
* search
* ratings
* duplicate report

---

## Logs

Live SSE viewer.

Display:

* timestamp
* level
* message

Levels:

```
info
success
warning
error
```

---

## Settings

Contains:

Libraries:

* paths
* extensions
* exclusions

Organization:

* folder templates
* filename templates

Duplicates:

* quality preference

Theme:

* mode
* accent

Plex:

* URL
* token

---

# Theme System

Use CSS variables.

Modes:

```
auto
light
dark
```

Default:

```
dark Glacier theme
```

---

# Accent Colors

Support presets:

```
cyan
sky
teal
blue
purple
green
orange
red
yellow
```

Only primary colors change.

Base surfaces stay consistent.

---

# Typography

Sans:

```
Inter
system-ui
```

Mono:

```
JetBrains Mono
monospace
```

Use mono for:

* logs
* percentages
* paths
* technical information

---

# Components

Required reusable components:

```
Button
Card
Dialog
Modal
Toast
Progress
Table
Tabs
Select
Input
Checkbox
Switch
Tooltip
```

---

# Motion

Use subtle animations only.

Required:

## Dialog

Open:

```
fade + zoom
200ms
```

---

## Buttons

Use:

```
transition-colors
150-200ms
```

---

## Progress

Use:

```
width transition
300ms
```

---

## Icons

Optional animated icons:

```
path draw animation
800ms
easeInOut
```

---

# Toasts

Used for:

* success
* errors
* warnings
* information

Example:

```
library scan completed
```

Short duration.

---

# Live Operations

Backend uses SSE.

Frontend:

On startup:

1. Connect `/api/events`
2. Receive logs
3. Display progress
4. Update job state

During jobs:

Disable conflicting actions.

---

# Confirm Dialog Rules

Required for:

* deleting duplicates
* moving files
* cleaning folders
* resolving exclusivity conflicts

Dialog must show:

Example:

```
124 files will be moved.

Continue?
```

---

# Responsive Behavior

This is not a mobile app.

Priority:

1. desktop browser
2. LAN access
3. server administration

---

# Design Goal

Glacier should feel like:

* Lidarr
* Plex
* DroppedNeedle
* slskd

A professional self-hosted management console.
