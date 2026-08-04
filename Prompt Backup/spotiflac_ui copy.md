# SpotiFLAC UI Blueprint — Visual & Architectural Planning Guide

> **Purpose:** Dense, file-oriented reference for cloning SpotiFLAC’s visual interface, theme system, layout grid, and motion language in a new Python (or other) frontend that talks to an independent backend.  
> **Source stack:** React 19 + Vite 8 + Tailwind CSS v4 + Radix UI primitives + `motion` (Motion One / Framer-compatible) + `tw-animate-css` + Lucide icons + Sonner toasts.  
> **Desktop shell:** Wails v2 frameless window (min 1024×600). Treat chrome (title bar, window controls) as first-class UI, not OS chrome.

---

## 0. High-Level Architecture Map

```
┌──────────────────────────────────────────────────────────────────────────┐
│ TitleBar (fixed, h-10, left-14 → right-0, z-40, backdrop-blur)           │
│   [drag region]                    [Menubar: volume + IP] [− □ ×]        │
├────┬─────────────────────────────────────────────────────────────────────┤
│ S  │ ContentScroll (fixed top-10 left-14 right-0 bottom-0, overflow-y)   │
│ i  │   ┌─────────────────────────────────────────────────────────────┐   │
│ d  │   │ Padding: p-4 (mobile) / md:p-8                              │   │
│ e  │   │ Width: max-w-4xl mx-auto  OR  w-full (wide modes)           │   │
│ b  │   │ space-y-6 vertical rhythm                                   │   │
│ a  │   │                                                             │   │
│ r  │   │  [Page content: main | history | settings | tools | …]      │   │
│    │   │                                                             │   │
│ w  │   └─────────────────────────────────────────────────────────────┘   │
│ -14│                                                                     │
│    │  Floating: DownloadProgressToast | CooldownBanner | ScrollTop btn  │
│    │  Overlays: DownloadQueue sheet | Dialogs (update, FFmpeg, VPN…)     │
└────┴─────────────────────────────────────────────────────────────────────┘
```

**Z-index ladder**

| Layer | z | Element |
|-------|---|---------|
| Base | 0 | Page content |
| Sidebar | 30 | Left rail |
| TitleBar drag strip | 40 | Top bar |
| TitleBar controls | 50 | Window buttons / menubar |
| Scroll-to-top FAB | 50 | Bottom-right |
| Dialogs / menus | 50+ | Radix portals |
| Toasts | Sonner default | Bottom-left |

**Pages (`PageType`)** — single-app SPA, no router library; state-driven switch in `App.tsx`:

| Key | Label | Content width |
|-----|-------|---------------|
| `main` | Home / Search & Download | Narrow until result/search; then full |
| `history` | History | Full |
| `settings` | Settings | `max-w-4xl` |
| `debug` | Debug Logs | Full |
| `audio-analysis` | Audio Quality Analyzer | Full |
| `audio-resampler` | Audio Resampler | Full |
| `audio-converter` | Audio Converter | Full |
| `file-manager` | File Manager | Full |
| `lyrics-manager` | Lyrics Manager | Full |
| `projects` | Other Projects | `max-w-4xl` |
| `support` | Support | `max-w-4xl` |

Wide content rule (`usesWideContent`):

- `main` → wide if search mode **or** metadata loaded  
- Other pages → wide unless `settings` | `projects` | `support`

---

## 1. FRONTEND LAYOUT & STRUCTURE

### 1.1 Global shell (`App.tsx`)

- Root: `h-screen overflow-hidden bg-background` inside `TooltipProvider`.
- `TitleBar` + `Sidebar` always mounted.
- Scroll container: `fixed top-10 right-0 bottom-0 left-14 overflow-y-auto overflow-x-hidden`.
- Inner padding: `p-4 md:p-8`.
- Content column: `space-y-6` + conditional `max-w-4xl mx-auto` vs `w-full`.
- Floating UI:
  - `DownloadProgressToast` (click opens queue)
  - `CooldownBanner`
  - `DownloadQueue` modal/sheet
  - Scroll-to-top: `fixed bottom-6 right-6 h-10 w-10 rounded-full shadow-lg` (appears when scrolled)
- Modal dialogs (non-dismissable FFmpeg gate, update, unsaved settings, VPN advice, album confirm).

### 1.2 Title bar (`TitleBar.tsx`)

**Geometry**

- Drag strip: `fixed top-0 left-14 right-0 h-10 z-40 bg-background/80 backdrop-blur-sm`  
  CSS custom property `--wails-draggable: drag`; double-click toggles maximize.
- Controls cluster: `fixed top-1.5 right-2 z-50 flex h-7 gap-0.5`.

**Controls (right → left conceptually)**

1. **Menubar** (Radix, borderless transparent):
   - Trigger: `SlidersHorizontal` icon, `w-8 h-7`, hover `bg-muted`.
   - Panel `min-w-70`:
     - **Preview Volume** label + live `%` (tabular-nums) + `Slider` 0–100 step 5.
     - Separator.
     - **Public IP / country** row: flag SVG from `/assets/flags/{cc}.svg`, country name, optional show/hide IP (`Eye` / `EyeOff`), refresh, blocked-country warning set for Spotify-restricted ISO codes.
2. **Window buttons** (native Wails): Minimize (`Minus`), Maximize (`Maximize`), Close (`X`).

No traditional menu bar text labels; icon-only density matches frameless desktop apps.

### 1.3 Sidebar (`Sidebar.tsx`)

**Geometry**

```
fixed left-0 top-0 h-full w-14
bg-card border-r border-border
flex flex-col items-center py-14 z-30
```

**Top cluster** (`flex flex-col gap-2 flex-1`)

| Order | Icon component | Page | Tooltip |
|-------|----------------|------|---------|
| 1 | `HomeIcon` | `main` | Home |
| 2 | `HistoryIcon` | `history` | History |
| 3 | `SettingsIcon` | `settings` | Settings |
| 4 | `TerminalIcon` (loop) | `debug` | Debug Logs |
| 5 | `ToolCaseIcon` | Tools dropdown | Tools |

**Tools dropdown** (`DropdownMenu`, side=`right`, `sideOffset={14}`, `min-w-50`):

- Audio Quality Analyzer → `ActivityIcon` (animated)
- Audio Resampler → `AudioLinesIcon`
- Audio Converter → `FileMusicIcon`
- File Manager → `FilePenIcon`
- Lyrics Manager → `FileTextIcon`

Each menu item: `gap-3 py-2 px-3`; hover starts/stops icon animation via ref handles.

**Bottom cluster** (`mt-auto flex flex-col gap-2`)

- Bug / feature report → `BugReportIcon` (opens agreement dialog then GitHub issues)
- Other projects → `BlocksIcon` → page `projects`
- Support / coffee → `CoffeeIcon` → page `support`

**Button states**

- Active: `variant="secondary"` + `bg-primary/10 text-primary hover:bg-primary/20`
- Inactive: `variant="ghost"` + `hover:bg-primary/10 hover:text-primary`
- Size: `h-10 w-10` icon buttons throughout.

### 1.4 Main / Home page composition

Rendered when `currentPage === "main"`:

1. **Optional Header** (brand / status) — component `Header.tsx`.
2. **SearchBar** (`SearchBar.tsx`) — primary interaction surface.
3. **Metadata panels** (mutually exclusive by entity type):
   - `TrackInfo` — single track card + actions
   - `AlbumInfo` — album header + `TrackList` + bulk controls
   - `PlaylistInfo` — playlist header + list
   - `ArtistInfo` — artist header, discography, gallery

**SearchBar layout (wireframe)**

```
[ Smart input field ………………… ✕ ] [📋] [☁ Fetch]
Recent Searches:  (chip row, pill bg-muted, hover:bg-accent)
  — chips show ✕ on group-hover

When search mode:
  Tabs: Tracks | Albums | Artists | Playlists  (border-b-2 active)
  Filter input with leading Search icon
  Result list cards / rows
```

- Placeholder rotates via typing effect among: artist names, track titles, Spotify URLs.
- Input kinds: empty | spotify URI/URL | free text | next-provider URL | invalid.
- History dropdown / recent list (max 8 local + backend recent fetches).
- Paste-from-clipboard icon button; clear (`XCircle`) when non-empty.

**Track / album list patterns**

- Pagination: 50 items per page (`ITEMS_PER_PAGE`).
- Selection: multi-select checkboxes for bulk download.
- Sort control (`SearchAndSort` / Select).
- Per-row actions: download, lyrics, cover, availability check, open folder, open album/artist.
- Status chips: downloading / downloaded / failed / skipped (lyrics & cover parallel maps).

### 1.5 Settings page (`SettingsPage.tsx`)

Long vertical form, sections typically:

- Download path + folder picker
- Downloader service: auto | tidal | qobuz | amazon
- Quality selectors per service + auto order / auto quality
- Custom API URLs (Tidal / Qobuz)
- Link resolver (songlink | songstats) + fallback toggle
- Theme color + theme mode (auto/light/dark)
- Font family + custom Google Fonts
- Folder preset / custom template
- Filename preset / album-specific template
- Metadata tag toggles grid
- Feature toggles: embed lyrics, max cover, playlist folder, M3U8, SFX, etc.
- Auto-convert / auto-resample blocks
- Unsaved-changes guard when navigating away

Content constrained to `max-w-4xl`.

### 1.6 Tool pages (shared pattern)

Each tool page is a full-width workspace:

- **Audio Analysis:** file drop / picker → spectrum viz (`SpectrumVisualization`) + metrics cards (peak, RMS, dynamic range, codec).
- **Converter / Resampler:** multi-file select, format/bitrate/sample-rate controls, progress list.
- **File Manager:** directory browser, metadata-driven rename preview.
- **Lyrics Manager:** scan folder, embed/extract LRC.

### 1.7 History / Support / Projects

- History: download history + fetch history lists with delete/clear.
- Support: Ko-fi / Patreon / crypto donation assets (`ko-fi.gif`, USDT/USDC images).
- Other Projects: cards linking SpotiFLAC Next, SpotubeDL, mobile forks, etc.

### 1.8 Overlay / chrome components

| Component | Placement | Role |
|-----------|-----------|------|
| `DownloadQueue` | Modal/sheet | Queue list, cancel, clear, export failed |
| `DownloadProgressToast` | Floating | Active download summary; click → queue |
| `CooldownBanner` | Top of content area | Community API break / rate-limit notice |
| Sonner `Toaster` | `bottom-left`, duration 1000 ms | Success/error/warning/info + SFX |

### 1.9 Responsive behavior

- **Hard minimum window:** 1024×600 (Wails config). Not a mobile-first app.
- Sidebar always 56 px (`w-14`); never collapses in current code.
- Content padding steps: `p-4` → `md:p-8`.
- Content max-width only on “settings-like” pages; main expands after first fetch.
- Tooltips on sidebar always `side="right"`, `delayDuration={0}`.
- Dialogs: `max-w-*` variants (`sm:max-w-125`, `max-w-md`, `max-w-xl`, etc.).

### 1.10 Control inventory (canonical)

| Control | Library | Notes |
|---------|---------|-------|
| Buttons | Radix Slot + CVA | variants: default, secondary, outline, ghost, destructive; sizes icon / default |
| Inputs | custom + context menu | paste, clear |
| Slider | Radix | volume, progress |
| Switch / Checkbox | Radix | settings toggles |
| Select | Radix | sort, quality, presets |
| Tabs | Radix | search result types |
| Dialog | Radix | animated overlay + zoom |
| Dropdown / Menubar / Context menu | Radix | sidebar tools, title bar |
| Tooltip | Radix | animate-in zoom/fade/slide |
| Progress | Radix / custom bar | downloads, FFmpeg install |
| Scroll area | Radix | optional long panels |
| Toggle / Toggle group | Radix | settings clusters |

---

## 2. CUSTOMIZATION & THEME DESIGN

### 2.1 Design tokens (`index.css` + `themes.ts`)

**Radius**

```
--radius: 0.625rem;          /* 10px */
--radius-sm: calc(var(--radius) - 4px);
--radius-md: calc(var(--radius) - 2px);
--radius-lg: var(--radius);
--radius-xl: calc(var(--radius) + 4px);
```

**Base surfaces (OKLCH — preferred over hex)**

| Token | Light | Dark |
|-------|-------|------|
| background | `oklch(1 0 0)` | `oklch(0.145 0 0)` |
| foreground | `oklch(0.145 0 0)` | `oklch(0.985 0 0)` |
| card | `oklch(1 0 0)` | `oklch(0.205 0 0)` |
| card-foreground | same as foreground | same as foreground |
| popover | same as card | same as card |
| secondary | `oklch(0.967 0.001 286.375)` | `oklch(0.274 0.006 286.033)` |
| muted | `oklch(0.97 0 0)` | `oklch(0.269 0 0)` |
| muted-foreground | `oklch(0.556 0 0)` | `oklch(0.708 0 0)` |
| accent | `oklch(0.97 0 0)` | `oklch(0.371 0 0)` |
| destructive | `oklch(0.58 0.22 27)` | `oklch(0.704 0.191 22.216)` |
| border | `oklch(0.922 0 0)` | `oklch(1 0 0 / 10%)` |
| input | `oklch(0.922 0 0)` | `oklch(1 0 0 / 15%)` |
| ring | `oklch(0.708 0 0)` | `oklch(0.556 0 0)` |

**Approximate sRGB equivalents (for non-OKLCH toolkits)**

| Role | Light ≈ | Dark ≈ |
|------|---------|--------|
| background | `#FFFFFF` | `#1A1A1A` |
| foreground | `#111111` | `#FAFAFA` |
| card (dark) | — | `#2A2A2A` |
| muted-fg | `#737373` | `#A3A3A3` |
| border | `#E5E5E5` | `rgba(255,255,255,0.1)` |
| destructive | `#DC2626` family | lighter red |

**Primary accents (theme presets)** — only `primary` + `primary-foreground` swap; everything else stays on base palette.

| Theme | Light primary | Dark primary |
|-------|---------------|--------------|
| amber | `oklch(0.67 0.16 58)` | `oklch(0.77 0.16 70)` |
| blue | `oklch(0.488 0.243 264.376)` | `oklch(0.42 0.18 266)` |
| cyan | `oklch(0.61 0.11 222)` | `oklch(0.71 0.13 215)` |
| emerald | `oklch(0.60 0.13 163)` | `oklch(0.70 0.15 162)` |
| fuchsia | `oklch(0.59 0.26 323)` | `oklch(0.67 0.26 322)` |
| green | `oklch(0.648 0.2 131.684)` | same |
| indigo | `oklch(0.51 0.23 277)` | `oklch(0.59 0.20 277)` |
| lime | `oklch(0.65 0.18 132)` | `oklch(0.77 0.20 131)` |
| neutral | `oklch(0.205 0 0)` | `oklch(0.922 0 0)` |
| orange | `oklch(0.646 0.222 41.116)` | `oklch(0.705 0.213 47.604)` |
| pink | `oklch(0.59 0.22 1)` | `oklch(0.66 0.21 354)` |
| purple | `oklch(0.56 0.25 302)` | `oklch(0.63 0.23 304)` |
| red | `oklch(0.577 0.245 27.325)` | `oklch(0.637 0.237 25.331)` |
| rose | `oklch(0.586 0.253 17.585)` | `oklch(0.645 0.246 16.439)` |
| sky | `oklch(0.59 0.14 242)` | `oklch(0.68 0.15 237)` |
| teal | `oklch(0.60 0.10 185)` | `oklch(0.70 0.12 183)` |
| violet | `oklch(0.541 0.281 293.009)` | `oklch(0.606 0.25 292.717)` |
| **yellow (default)** | `oklch(0.852 0.199 91.936)` | `oklch(0.795 0.184 86.047)` |

Application: `applyTheme(name)` writes CSS variables on `document.documentElement` for light or dark branch depending on `.dark` class.  
Mode: `themeMode` = `auto` | `light` | `dark` (`applyThemeMode` uses `prefers-color-scheme` when auto).

### 2.2 Typography

**Sans (UI)**

Default CSS:

```css
--font-sans: "Bricolage Grotesque", "Google Sans", system-ui, -apple-system,
  BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
```

**Selectable built-in families** (`FONT_OPTIONS`):

Bricolage Grotesque, DM Sans, Figtree, Geist Sans, Google Sans, Inter, JetBrains Mono, Manrope, Noto Sans, Nunito Sans, Outfit, Plus Jakarta Sans, Poppins, Public Sans, Raleway, Roboto, Space Grotesk.

**Custom fonts:** Google Fonts CSS2 URLs only; stored as `custom-{slug}`; loaded via injected `<link>`.

**Mono**

```css
"Google Sans Code", ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco,
Consolas, "Liberation Mono", "Courier New", monospace
```

Used for code, logs, tabular progress numbers (`font-mono tabular-nums`).

**Type scale habits**

- Page titles: `text-lg font-bold tracking-tight`
- Section labels: `text-sm font-medium` / uppercase micro-labels `text-[10px] … tracking-[0.2em]`
- Body: default `text-sm` / `text-base`
- Muted helper: `text-muted-foreground`
- Toasts forced lowercase via `font-mono lowercase` class.

### 2.3 Spacing & density

| Context | Values |
|---------|--------|
| Sidebar width | `3.5rem` (56px) |
| Title bar height | `2.5rem` (40px) |
| Content pad | `1rem` / `2rem` at md |
| Vertical stack | `space-y-6` (1.5rem) |
| Icon button | `h-10 w-10` |
| Sidebar icon | 20 px |
| Menu icon | 16 px |
| Gap in icon columns | `gap-2` (0.5rem) |
| FAB offset | `bottom-6 right-6` |
| Dialog padding | `p-6`, internal `gap-4`–`gap-5` |

### 2.4 Branding & visual language

- **Product mark:** `spotiflac.svg` + service badges (Tidal light/dark, Qobuz, Amazon, Deezer, Songlink, Songstats, MusicBrainz, LRCLIB).
- **Accent identity:** strong primary tint on active nav (`bg-primary/10`), progress bars (`bg-primary` + soft glow `shadow-[0_0_10px_…]`), focus rings.
- **Surfaces:** flat cards, subtle borders, minimal elevation; dialogs use `shadow-lg`.
- **Toasts (Sonner overrides):**
  - Success: green-50 / green-200 / green-900 (icon green-600)
  - Error: red-50 / red-200 / red-900
  - Warning: yellow-50 / yellow-200 / yellow-900
  - Info: blue-50 / blue-200 / blue-900  
  Dark mode keeps saturated icon/description colors rather than inverting fully.
- **SFX:** optional UI sounds on toast levels (`sfxEnabled` setting).
- **Flags:** large SVG set under `/assets/flags/` for IP geolocation badge.

### 2.5 Filename / folder branding presets (UX copy)

Folder presets: none, artist, album, `[year] album`, artist/album trees, album-artist variants, year trees, custom.  
Filename presets: title, title-artist, artist-title, track-number variants, disc-track, custom.  
Template tokens: `{title} {artist} {artists} {album} {album_artist} {track} {total_tracks} {disc} {total_discs} {year} {date} {isrc} {upc} {category} {playlist}`.

---

## 3. MOTION ANIMATIONS & TRANSITIONS

### 3.1 Libraries

- **`motion` (v12)** — primary JS animation (`motion/react`: `motion`, `useAnimation`, `Variants`).
- **`tw-animate-css`** — Tailwind utility classes `animate-in`, `animate-out`, `fade-in-0`, `zoom-in-95`, `slide-in-from-*`.
- **CSS** — `transition-colors`, `transition-all duration-300`, `transition-opacity`, `animate-spin`.
- **Global reduced motion** (`index.css`): when `prefers-reduced-motion: reduce`, all animations forced to ~0.01 ms; `MotionConfig reducedMotion="user"` in `main.tsx`.

### 3.2 Page / shell transitions

- No full-page route transitions; page swap is instant React conditional render.
- Scroll container remains mounted; only inner `renderPage()` switches.
- Scroll-to-top button appears/disappears without explicit enter animation (conditional render).

### 3.3 Overlay / dialog motion

**Dialog overlay**

```
data-[state=open]:animate-in fade-in-0
data-[state=closed]:animate-out fade-out-0
bg-black/50
```

**Dialog content**

```
data-[state=open]:animate-in fade-in-0 zoom-in-95
data-[state=closed]:animate-out fade-out-0 zoom-out-95
duration-200
fixed center translate -50%/-50%
```

**Tooltip content**

```
animate-in fade-in-0 zoom-in-95
data-[state=closed]:animate-out fade-out-0 zoom-out-95
data-[side=…]:slide-in-from-{opposite}-2
```

**Dropdown / menubar / context menus** — Radix + same animate-in/out family (fade + zoom / slide).

### 3.4 Micro-interactions — animated sidebar icons

Pattern shared by `activity`, `audio-lines`, `file-music`, `file-pen`, `file-text`, `coffee`, `bug-report`, `terminal`, `home`, `history`, `settings`, `tool-case`, `blocks`:

```ts
const PATH_VARIANTS: Variants = {
  normal: { pathLength: 1, opacity: 1, pathOffset: 0 },
  animate: {
    pathLength: [0, 1],
    opacity: [0, 1],
    pathOffset: [1, 0],
    transition: { duration: 0.8, ease: "easeInOut" },
  },
};
```

- Hover / focus on menu item or icon → `controls.start("animate")`.
- Leave / blur → `controls.start("normal")`.
- Some icons (`TerminalIcon`, `BugReportIcon`) support `loop={true}` for continuous idle motion.
- Imperative handles (`startAnimation` / `stopAnimation`) used from Sidebar dropdown items.

### 3.5 Control-level transitions

| Element | Behavior |
|---------|----------|
| Buttons / nav | `transition-colors`; active primary tint |
| Progress bars | `transition-all duration-300`; optional primary glow shadow |
| Toast duration | 1000 ms visible |
| Volume slider | live update on drag; persist on commit |
| Chips (recent search) | `transition-colors`; delete badge `opacity-0 → group-hover:opacity-100 transition-all` |
| Clear / paste icons | `transition-colors` on hover |
| FFmpeg install UI | `animate-in fade-in duration-500`; spinner `animate-spin`; bar width transition 300 ms |
| Toggle / switch | Radix built-in state transitions |
| Tabs (search results) | `transition-colors` + border-b-2 active indicator |

### 3.6 Recommended easing vocabulary for a clone

| Use case | Curve | Duration |
|----------|-------|----------|
| Icon path draw | `easeInOut` | 800 ms |
| Dialog open/close | default tw-animate (≈ ease-out) | 200 ms |
| Tooltip | zoom+fade | ~150–200 ms |
| Color / hover | CSS ease | 150–200 ms |
| Progress width | CSS linear/ease | 300 ms |
| Fade-in status panels | `fade-in` | 500 ms |
| Spinner | continuous linear | infinite |

### 3.7 Sound-coupled feedback

`toast-with-sound.ts` maps:

- success → success SFX  
- error → error SFX  
- warning → warning SFX  
- info / message → info SFX  

Gated by `settings.sfxEnabled`. Clone should keep optional audio feedback on the same events.

### 3.8 Hover / focus affordances checklist

- Sidebar: primary-tinted background on hover even when inactive.
- Tooltips: zero delay for navigation density.
- Inputs: focus ring `ring-[3px] ring-ring/50` + border-ring.
- Destructive actions: dedicated variant + confirmation dialogs for destructive navigation (unsaved settings).
- Disabled: `opacity-50 pointer-events-none`.

---

## 4. FILE-BY-FILE VISUAL REFERENCE INDEX

| Path | Role in UI clone |
|------|------------------|
| `frontend/src/App.tsx` | Shell layout, page switch, dialogs, scroll, wide/narrow rule |
| `frontend/src/main.tsx` | MotionConfig, Toaster placement |
| `frontend/src/index.css` | Tokens, reduced-motion, toast colors, base layers |
| `frontend/src/lib/themes.ts` | Full theme palette table + `applyTheme` |
| `frontend/src/lib/settings.ts` | Fonts, presets, defaults, theme mode, templates |
| `frontend/src/components/TitleBar.tsx` | Drag region, volume, IP badge, window controls |
| `frontend/src/components/Sidebar.tsx` | Rail layout, nav map, tools menu, animated icons |
| `frontend/src/components/SearchBar.tsx` | Smart search, tabs, recent chips, fetch CTA |
| `frontend/src/components/TrackInfo.tsx` / `AlbumInfo.tsx` / `PlaylistInfo.tsx` / `ArtistInfo.tsx` | Entity presentation cards |
| `frontend/src/components/TrackList.tsx` | List rows, selection, bulk actions |
| `frontend/src/components/SettingsPage.tsx` | Dense settings form sections |
| `frontend/src/components/DownloadQueue.tsx` / `DownloadProgressToast.tsx` | Queue UX |
| `frontend/src/components/SpectrumVisualization.tsx` | Analyzer visual |
| `frontend/src/components/ui/*` | Atomic primitives + motion icons |
| `frontend/src/lib/toast-with-sound.ts` | Toast + SFX coupling |
| `frontend/wails.json` | Window size, frameless, product version |
| `frontend/public/assets/flags/*` | Country flags for IP indicator |

---

## 5. IMPLEMENTATION NOTES FOR A PYTHON UI CLONE

1. **Recreate the chrome first:** fixed left 56 px rail + 40 px top drag bar + content inset. This is the visual signature more than any single page.
2. **Theme engine:** store base OKLCH (or converted hex) + 18 primary accent pairs; toggle `.dark` equivalent and swap only primary tokens.
3. **Typography:** ship at least Google Sans / Inter / Bricolage Grotesque; keep mono for logs and percentages.
4. **Motion budget:** prioritize (a) dialog fade+zoom 200 ms, (b) icon path-draw 800 ms easeInOut on hover, (c) progress width 300 ms. Skip full-page transitions.
5. **Density:** icon-only nav, 40×40 hit targets, tooltips with no delay, lowercase mono toasts at bottom-left 1 s.
6. **Backend independence:** all Wails `go/main/App` calls become your API; keep the same UI event names (fetch, download, queue, progress) so the layout stays identical.
7. **Accessibility:** honor reduced-motion; preserve focus rings; keep tooltip text identical to the table in §1.3.
8. **Assets to port:** service logos (light/dark pairs), product SVG, flag set, donation imagery if Support page is cloned.

---

## 6. QUICK WIREFRAME — HOME (DEFAULT)

```
┌──┬─────────────────────────────────────────────────────────────┐
│  │ ░░░░░░░░░░ TitleBar (blur) ░░░░░░ [⚙ vol] [IP] [−][□][×]   │
│H │                                                             │
│i │   SpotiFLAC header / status                                 │
│s │                                                             │
│t │   ┌───────────────────────────────────────┐ [📋] [Fetch]    │
│o │   │ Smart search / Spotify URL            │                 │
│r │   └───────────────────────────────────────┘                 │
│y │   Recent: [Taylor Swift ×] [Die For You ×] …                │
│  │                                                             │
│S │   (after fetch)                                             │
│e │   ┌──────── cover ────────┐  Title                          │
│t │   │                       │  Artist · Album · year          │
│t │   └───────────────────────┘  [Download] [Lyrics] [Cover]    │
│i │                                                             │
│n │   Track list / selection toolbar / pagination               │
│g │                                                             │
│s │                                                             │
│  │                                              (↑ scroll FAB) │
│… │                                                             │
└──┴─────────────────────────────────────────────────────────────┘
```

This document is intentionally non-code: use it as the visual contract while wiring a separate backend.
