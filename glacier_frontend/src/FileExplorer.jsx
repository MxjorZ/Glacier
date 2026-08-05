import { useCallback, useEffect, useMemo, useState } from 'react';
import { Folder, FolderOpen, HardDrive, ChevronRight, ChevronUp, Music, File, Home, LayoutGrid, List, Loader2, Check, SlidersHorizontal } from 'lucide-react';
import { api, fmtBytes } from './api.js';
import { Dialog, DialogContent } from '@/components/ui/dialog.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Input } from '@/components/ui/input.jsx';
import { Checkbox } from '@/components/ui/checkbox.jsx';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select.jsx';
import { Badge } from '@/components/ui/badge.jsx';
import { cn } from '@/lib/utils.js';

// Clickable breadcrumb segments from an absolute path (Linux and Windows).
function buildCrumbs(p) {
  if (!p) return [];
  const win = /^[A-Za-z]:/.test(p);
  const sep = p.includes('/') ? '/' : '\\';
  const rest = win ? p.slice(2).split(/[\\/]/).filter(Boolean) : p.split(sep).filter(Boolean);
  const driveRoot = win ? p[0] + ':\\' : sep;
  const roots = win ? [{ label: p[0] + ':', path: driveRoot }] : [{ label: '/', path: sep }];
  const segs = [];
  for (const part of rest) {
    segs.push(part);
    roots.push({ label: part, path: win ? driveRoot + segs.join('\\') : sep + segs.join(sep) });
  }
  return roots;
}

const FILE_PAGE = 400;
const pageStyles = { height: 'calc(100vh - 12rem)', minHeight: '22rem' };

// Native-style file explorer for picking library folder(s): near-fullscreen
// grid + list view, breadcrumb hierarchy, song counts, search/sort, and a
// load-more pagination.
//
// Selection model (deliberate -- no accidental single-click picks):
//   - A single click on an item does NOT select it.
//   - Use the checkbox on the left of each item (a real checklist) to select,
//     or the "Select all" checkbox to select everything in the current listing.
//   - Double-click a FOLDER to open (navigate) into it -- the loading spinner
//     you see is the folder being read.
//   - Press "Confirm selection" to apply the checked folder(s).
//   - onSelect(primaryPath, allPaths): primaryPath is a single path for
//     backward compatibility (Tags uses it); allPaths is the array of selected
//     folder paths (falls back to the current folder when nothing is checked).
export default function FileExplorer({ open, onClose, onSelect }) {
  const [path, setPath] = useState('');
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [checked, setChecked] = useState([]);       // paths (checklist)
  const [view, setView] = useState('grid');          // grid | list
  const [sortMode, setSortMode] = useState('name');  // name | size | audio
  const [audioOnly, setAudioOnly] = useState(false);
  const [query, setQuery] = useState('');
  const [filePage, setFilePage] = useState(FILE_PAGE);
  const [focusIdx, setFocusIdx] = useState(0);

  const load = useCallback((p) => {
    setBusy(true);
    setError('');
    setChecked([]);
    setFilePage(FILE_PAGE);
    setFocusIdx(0);
    api.listDir(p)
      .then((d) => { setPath(d.path || ''); setEntries(d); })
      .catch((e) => setError(e.message || 'Cannot read this folder (permission?)'))
      .finally(() => setBusy(false));
  }, []);

  useEffect(() => { if (open) { setQuery(''); load(''); } }, [open, load]);

  const crumbs = buildCrumbs(path);
  const dirs = entries?.dirs || [];
  const files = entries?.files || [];
  const audioTotal = entries?.audio_total;

  const items = useMemo(() => {
    const q = query.trim().toLowerCase();
    const wantDir = (d) => !q || d.name.toLowerCase().includes(q);
    const wantFile = (f) => (audioOnly ? f.audio : true) && (!q || f.name.toLowerCase().includes(q));
    const ds = dirs.filter(wantDir).map((d) => ({ ...d, kind: 'dir' }));
    const fs = files.filter(wantFile).map((f) => ({ ...f, kind: 'file' }));
    const cmp = (a, b) => {
      if (sortMode === 'size' && a.kind === 'file' && b.kind === 'file') return b.size - a.size;
      if (sortMode === 'audio' && a.kind === 'file' && b.kind === 'file') return Number(b.audio) - Number(a.audio);
      return a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' });
    };
    ds.sort(cmp);
    fs.sort(cmp);
    return [...ds, ...fs];
  }, [dirs, files, query, audioOnly, sortMode]);

  const gridItems = useMemo(() => items.slice(0, filePage), [items, filePage]);

  // --- checklist helpers -------------------------------------------------
  const isChecked = (p) => checked.includes(p);
  const toggle = (p) => setChecked((cur) => (cur.includes(p) ? cur.filter((x) => x !== p) : [...cur, p]));

  const visiblePaths = gridItems.map((it) => it.path);
  const allChecked = visiblePaths.length > 0 && visiblePaths.every((p) => checked.includes(p));
  const someChecked = visiblePaths.some((p) => checked.includes(p));
  const toggleAll = (val) => {
    setChecked((cur) => {
      if (val) return Array.from(new Set([...cur, ...visiblePaths]));
      return cur.filter((p) => !visiblePaths.includes(p));
    });
  };

  // Folders among the current listing that are checked.
  const checkedDirs = useMemo(
    () => items.filter((it) => it.kind === 'dir' && isChecked(it.path)).map((it) => it.path),
    [items, checked], // eslint-disable-line react-hooks/exhaustive-deps
  );

  const openDir = (p) => { if (p && p !== path) load(p); };
  const goUp = () => { if (crumbs.length > 1) load(crumbs[crumbs.length - 2].path); };

  const selectFolder = () => {
    // Confirmation: use the checked folder(s), or the currently-open folder.
    const paths = checkedDirs.length ? checkedDirs : [path];
    const primary = paths[0];
    onSelect(primary, paths);
    onClose();
  };

  // Keyboard navigation inside the file list (click-free folder picking).
  // ArrowUp/Down move a highlight, Enter opens the focused folder, Backspace
  // goes up a level, Escape closes, and Space toggles the focused item.
  const onKeyDown = (e) => {
    if (!gridItems.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setFocusIdx((i) => (i + 1) % gridItems.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setFocusIdx((i) => (i - 1 + gridItems.length) % gridItems.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const it = gridItems[focusIdx];
      if (it && it.kind === 'dir') openDir(it.path);
    } else if (e.key === ' ') {
      e.preventDefault();
      const it = gridItems[focusIdx];
      if (it) toggle(it.path);
    } else if (e.key === 'Backspace') {
      e.preventDefault();
      goUp();
    } else if (e.key === 'Escape') {
      onClose();
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="flex flex-col gap-0 p-0" style={pageStyles} aria-describedby={undefined}>
        {/* Toolbar */}
        <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
          <div className="flex items-center gap-1 text-xs">
            <Button size="sm" variant="ghost" onClick={() => load('')}><Home className="size-4" /></Button>
            <Button size="sm" variant="ghost" onClick={goUp} disabled={crumbs.length <= 1}><ChevronUp className="size-4" /></Button>
          </div>
          <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto rounded-lg border bg-muted/40 px-2 py-1 text-xs">
            {crumbs.map((c, i) => (
              <span key={c.path + i} className="flex shrink-0 items-center gap-1">
                {(i > 0) && <ChevronRight className="size-3 text-muted-foreground/60" />}
                <button onClick={() => load(c.path)}
                  className={cn('rounded px-1.5 py-0.5 whitespace-nowrap hover:bg-accent',
                    i === crumbs.length - 1 ? 'font-medium' : 'text-muted-foreground')}>
                  {c.label}
                </button>
              </span>
            ))}
          </div>
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search this folder…"
            className="h-8 w-44 shrink-0" />
          <Select value={sortMode} onValueChange={setSortMode}>
            <SelectTrigger className="h-8 w-32 shrink-0"><SlidersHorizontal className="size-3.5" /><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="name">Name</SelectItem>
              <SelectItem value="size">Size</SelectItem>
              <SelectItem value="audio">Songs</SelectItem>
            </SelectContent>
          </Select>
          <button onClick={() => setAudioOnly((v) => !v)}
            className={cn('flex h-8 shrink-0 items-center gap-1.5 rounded-lg border px-2.5 text-xs',
              audioOnly ? 'border-primary bg-primary/15 text-primary' : 'text-muted-foreground hover:bg-accent')}>
            <Music className="size-3.5" /> Audio only
          </button>
          <div className="flex shrink-0 rounded-lg border p-0.5">
            <button onClick={() => setView('grid')} title="Grid"
              className={cn('rounded p-1.5', view === 'grid' ? 'bg-accent' : 'text-muted-foreground')}>
              <LayoutGrid className="size-4" />
            </button>
            <button onClick={() => setView('list')} title="List"
              className={cn('rounded p-1.5', view === 'list' ? 'bg-accent' : 'text-muted-foreground')}>
              <List className="size-4" />
            </button>
          </div>
        </div>

        <div className="flex min-h-0 flex-1">
          <div className="flex min-h-0 flex-1 flex-col">
            {/* Select-all checklist header */}
            <div className="flex items-center gap-2 border-b px-3 py-1.5 text-xs text-muted-foreground">
              <label className="flex items-center gap-1.5">
                <Checkbox checked={allChecked}
                  onCheckedChange={toggleAll}
                  aria-label="Select all" />
                <span className="font-medium">{allChecked ? 'Deselect all' : 'Select all'}</span>
              </label>
              {someChecked && !allChecked && <span className="text-warn">Mixed selection</span>}
              <span className="ml-auto">{checked.length} selected</span>
            </div>

            <div className="min-h-0 flex-1 overflow-auto p-3" tabIndex={0} onKeyDown={onKeyDown}>
              {busy ? (
                <div className="flex h-full items-center justify-center gap-2 text-muted-foreground">
                  <Loader2 className="size-5 animate-spin" /> Loading…
                </div>
              ) : error ? (
                <p className="p-4 text-sm text-destructive">{error}</p>
              ) : gridItems.length === 0 ? (
                <p className="p-4 text-sm text-muted-foreground">Empty folder.</p>
              ) : view === 'grid' ? (
                <div className="grid grid-cols-[repeat(auto-fill,minmax(7.5rem,1fr))] gap-2">
                  {gridItems.map((it) => (
                    <Tile key={it.path} it={it} checked={isChecked(it.path)}
                      focused={gridItems.indexOf(it) === focusIdx}
                      onToggle={() => toggle(it.path)}
                      onOpen={() => { if (it.kind === 'dir') openDir(it.path); }} />
                  ))}
                  {gridItems.length === items.length
                    ? <span className="col-span-full py-2 text-center text-xs text-muted-foreground">All {items.length} items shown.</span>
                    : <button onClick={() => setFilePage((p) => p + FILE_PAGE)} className="col-span-full rounded-lg border py-2 text-xs text-muted-foreground hover:bg-accent">Load more…</button>}
                </div>
              ) : (
                <div className="divide-y divide-border/60">
                  {gridItems.map((it) => (
                    <Row key={it.path} it={it} checked={isChecked(it.path)}
                      focused={gridItems.indexOf(it) === focusIdx}
                      onToggle={() => toggle(it.path)}
                      onOpen={() => { if (it.kind === 'dir') openDir(it.path); }} />
                  ))}
                  {gridItems.length === items.length
                    ? <p className="py-2 text-center text-xs text-muted-foreground">All {items.length} items shown.</p>
                    : <button onClick={() => setFilePage((p) => p + FILE_PAGE)} className="w-full rounded-lg border py-2 text-xs text-muted-foreground hover:bg-accent">Load more…</button>}
                </div>
              )}
            </div>
          </div>

          {/* Selection / details box on the side */}
          <DetailsPanel currentPath={path} audioTotal={audioTotal}
            checkedCount={checked.length} checkedDirs={checkedDirs}
            onOpen={() => openDir(path)} onSelectFolder={selectFolder} />
        </div>
      </DialogContent>
    </Dialog>
  );
}

// Big-icon tile for the grid. A single click does nothing; the checkbox on the
// top-left selects, and double-clicking opens a folder.
function Tile({ it, checked, focused, onToggle, onOpen }) {
  return (
    <div className={cn('group relative flex select-none flex-col items-center rounded-lg border p-2 pt-3 hover:bg-accent/50',
      focused && 'ring-2 ring-primary/60')}
      onDoubleClick={onOpen} title={it.path}>
      <button
        className="absolute left-1.5 top-1.5 z-10 rounded p-0.5 hover:bg-muted"
        onClick={(e) => { e.stopPropagation(); onToggle(); }}
        aria-label={checked ? 'Deselect' : 'Select'}
        tabIndex={-1}
      >
        <Checkbox checked={checked} className="pointer-events-none size-3.5" />
      </button>
      <div className={cn('relative', checked && 'opacity-40')}>
        {it.kind === 'dir' && it.audio != null && it.audio > 0 && (
          <Badge variant="secondary" className="absolute -right-1 -top-1 z-10 rounded-full px-1.5 py-0 text-[10px]">{it.audio}</Badge>
        )}
        {it.kind === 'dir'
          ? (it.audio == null
              ? <HardDrive className="size-14 text-muted-foreground/80" strokeWidth={1.4} />
              : <Folder className="size-14 text-amber-400/90" strokeWidth={1.4} />)
          : it.audio
            ? <Music className="size-14 text-primary" strokeWidth={1.4} />
            : <File className="size-14 text-muted-foreground/70" strokeWidth={1.4} />}
        {checked && <Check className="absolute -bottom-1 -right-1 size-4 rounded-full bg-primary p-0.5 text-primary-foreground" />}
      </div>
      <span className="mt-1 w-full truncate text-center text-xs leading-tight">{it.name}</span>
      {it.kind === 'file' && <span className="w-full truncate text-center font-mono text-[10px] text-muted-foreground">{fmtBytes(it.size)}</span>}
    </div>
  );
}

// Compact list row. Same interaction rules as the grid tile.
function Row({ it, checked, focused, onToggle, onOpen }) {
  return (
    <div className={cn('group flex items-center gap-2 rounded px-1.5 py-1.5 hover:bg-accent/40',
      focused && 'ring-1 ring-primary/50 bg-accent/30')}
      onDoubleClick={onOpen} title={it.path}>
      <button className="rounded p-0.5 hover:bg-muted" onClick={(e) => { e.stopPropagation(); onToggle(); }} aria-label={checked ? 'Deselect' : 'Select'} tabIndex={-1}>
        <Checkbox checked={checked} className="pointer-events-none size-3.5" />
      </button>
      {it.kind === 'dir'
        ? <Folder className="size-4 shrink-0 text-amber-400/90" />
        : it.audio ? <Music className="size-4 shrink-0 text-primary" /> : <File className="size-4 shrink-0 text-muted-foreground/70" />}
      <span className="min-w-0 flex-1 truncate text-xs">{it.name}</span>
      {it.kind === 'dir' && it.audio != null && (
        <span className="shrink-0 font-mono text-[10px] text-muted-foreground">{it.audio} songs</span>
      )}
      {it.kind === 'file' && <span className="shrink-0 font-mono text-[10px] text-muted-foreground">{fmtBytes(it.size)}</span>}
      {checked && <Check className="size-3.5 shrink-0 text-primary" />}
    </div>
  );
}

// Right-hand selection/details box. It reflects the checklist state and is
// where you confirm the selected folder(s).
function DetailsPanel({ currentPath, audioTotal, checkedCount, checkedDirs, onOpen, onSelectFolder }) {
  const label = checkedDirs.length > 0
    ? `${checkedDirs.length} folder${checkedDirs.length === 1 ? '' : 's'} selected`
    : (checkedCount > 0 ? `${checkedCount} item(s) selected` : 'No folder selected — current folder will be used');
  return (
    <div className="flex w-64 shrink-0 flex-col rounded-lg border bg-card/40 p-3 text-xs">
      <div className="mb-2 font-semibold uppercase tracking-wide text-muted-foreground">Selection</div>
      <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed p-3">
        <Folder className="size-14 text-amber-400/90" strokeWidth={1.2} />
        <span className="w-full truncate text-center font-medium">{currentPath || '…'}</span>
      </div>

      <div className="mt-3 space-y-1.5">
        <div className="flex justify-between gap-2"><span className="text-muted-foreground">Checked</span><span className="font-mono">{checkedCount}</span></div>
        {audioTotal != null && <div className="flex justify-between gap-2"><span className="text-muted-foreground">Songs here</span><span className="font-mono">{audioTotal}</span></div>}
        <p className={cn('rounded bg-muted/50 p-1.5 text-[10px] leading-relaxed', checkedDirs.length ? 'text-primary' : 'text-muted-foreground')}>
          {label}
        </p>
      </div>

      <div className="mt-3 flex flex-col gap-2">
        <Button size="sm" variant="outline" onClick={onOpen} className="w-full">
          <FolderOpen className="size-4" /> Open current folder
        </Button>
        <Button size="sm" onClick={onSelectFolder} className="w-full">
          <Check className="size-4" /> Confirm selection
        </Button>
      </div>
      <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground">
        Single-click does nothing — check folders with the box, double-click a folder to open it, then confirm.
      </p>
    </div>
  );
}
