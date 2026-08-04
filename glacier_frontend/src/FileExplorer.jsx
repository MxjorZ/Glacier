import { useCallback, useEffect, useMemo, useState } from 'react';
import { Folder, HardDrive, ChevronRight, ChevronUp, Music, File, Search, Home, RefreshCw, LayoutGrid, List, Loader2, Check, SlidersHorizontal } from 'lucide-react';
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

// Native-style file explorer for picking a library folder: near-fullscreen
// big-icon grid, breadcrumb hierarchy, song counts, search/sort, list view,
// load-more pagination, and file-manager interaction (select / open / up).
export default function FileExplorer({ open, onClose, onSelect }) {
  const [path, setPath] = useState('');
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState(null);
  const [view, setView] = useState('grid');         // grid | list
  const [sortMode, setSortMode] = useState('name'); // name | size | audio
  const [audioOnly, setAudioOnly] = useState(false);
  const [query, setQuery] = useState('');
  const [filePage, setFilePage] = useState(FILE_PAGE);

  const load = useCallback((p) => {
    setBusy(true);
    setError('');
    setSelected(null);
    setFilePage(FILE_PAGE);
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
  }, [dirs, files, audioOnly, query, sortMode]);

  const gridItems = items.slice(0, filePage);
  const hasMore = filePage < items.length;

  const openDir = (p) => { if (p) load(p); };
  const openSelected = () => { if (selected && selected.kind === 'dir') openDir(selected.path); };
  const goUp = () => { if (entries?.parent) load(entries.parent); };

  // Keyboard navigation like a file manager.
  useEffect(() => {
    const h = (e) => {
      if (!open) return;
      if (e.key === 'Enter' && selected) openSelected();
      else if (e.key === 'Backspace' || e.key === 'ArrowLeft') goUp();
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [open, selected, entries]);

  const pickTarget = selected && selected.kind === 'dir' ? selected.path : path;
  const selectFolder = () => { onSelect(pickTarget); onClose(); };
  const audioCount = entries?.files ? entries.files.filter((f) => f.audio).length : null;

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent showCloseButton={false} className="flex h-[calc(100vh-3rem)] w-[calc(100vw-3rem)] max-h-[calc(100vh-3rem)] max-w-[1500px] flex-col gap-2 p-3">
        {/* Toolbar */}
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => load('')} title="Browse mounts"><Home className="size-4" /> Roots</Button>
          <Button variant="ghost" size="sm" onClick={goUp} disabled={!entries?.parent} title="Up (Backspace)"><ChevronUp className="size-4" /> Up</Button>
          <Button variant="ghost" size="sm" onClick={() => load(path)} disabled={busy} title="Refresh"><RefreshCw className={cn('size-4', busy && 'animate-spin')} /></Button>
          <div className="flex items-center gap-1 rounded-lg border p-0.5">
            <Button variant={view === 'grid' ? 'secondary' : 'ghost'} size="sm" onClick={() => setView('grid')} title="Big icons" className="h-7 px-2"><LayoutGrid className="size-4" /></Button>
            <Button variant={view === 'list' ? 'secondary' : 'ghost'} size="sm" onClick={() => setView('list')} title="List" className="h-7 px-2"><List className="size-4" /></Button>
          </div>
          <div className="relative min-w-36 flex-1">
            <Search className="absolute left-2 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter by name…" className="h-8 pl-8 text-sm" />
          </div>
          <Select value={sortMode} onValueChange={setSortMode}>
            <SelectTrigger className="h-8 w-36 gap-2 text-sm"><SlidersHorizontal className="size-3.5" /><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="name">Name</SelectItem>
              <SelectItem value="size">File size</SelectItem>
              <SelectItem value="audio">Audio first</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Breadcrumb */}
        <div className="flex min-h-9 items-center gap-1 overflow-x-auto rounded-lg border bg-card/40 px-1.5 py-1 text-sm">
          {crumbs.length === 0 ? (
            <span className="px-2 text-muted-foreground">Browse: choose a mount below</span>
          ) : (
            crumbs.map((c, i) => {
              const last = i === crumbs.length - 1;
              return (
                <span key={c.path} className="flex shrink-0 items-center">
                  {i > 0 && <ChevronRight className="size-3.5 text-muted-foreground" />}
                  {last ? (
                    <span className="cursor-default truncate rounded px-2 py-1 font-semibold text-primary">{c.label}</span>
                  ) : (
                    <button onClick={() => load(c.path)} className="truncate rounded px-2 py-1 text-muted-foreground hover:bg-accent hover:text-foreground">{c.label}</button>
                  )}
                </span>
              );
            })
          )}
          {busy && <Loader2 className="ml-auto size-4 shrink-0 animate-spin text-muted-foreground" />}
        </div>

        {error && <div className="rounded-lg border border-warn/60 bg-warn/10 px-3 py-2 text-xs text-warn">{error} — make sure the folder is mounted into the container and readable.</div>}


        {/* File grid / list */}
        <div className="min-h-0 flex-1 overflow-auto rounded-lg border bg-card/40">
          {view === 'grid' ? (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(104px,1fr))] gap-1.5 p-3">
              {gridItems.map((it) => (
                <Tile key={it.path} it={it} selected={selected?.path === it.path}
                  onSelect={() => setSelected(it)}
                  onOpen={() => { if (it.kind === 'dir') openDir(it.path); }} />
              ))}
            </div>
          ) : (
            <div className="divide-y divide-border/40">
              {gridItems.map((it) => (
                <div key={it.path} onClick={() => setSelected(it)}
                  onDoubleClick={() => { if (it.kind === 'dir') openDir(it.path); }}
                  className={cn('flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm', selected?.path === it.path && 'bg-accent')}>
                  {it.kind === 'dir' ? <Folder className="size-4 shrink-0 text-primary" /> : it.audio ? <Music className="size-4 shrink-0 text-primary" /> : <File className="size-4 shrink-0 text-muted-foreground" />}
                  <span className="truncate">{it.name}</span>
                  {it.kind === 'file' && <span className="ml-auto shrink-0 font-mono text-xs text-muted-foreground">{fmtBytes(it.size)}</span>}
                </div>
              ))}
            </div>
          )}

          {items.length === 0 && (
            <div className="px-3 py-12 text-center text-sm text-muted-foreground">
              {query ? 'No items match your filter.' : 'This folder is empty.'}
            </div>
          )}

          {hasMore && (
            <div className="p-2 text-center">
              <Button variant="outline" size="sm" onClick={() => setFilePage((n) => n + FILE_PAGE)}>Load more ({gridItems.length} of {items.length})</Button>
            </div>
          )}
        </div>

        {/* Status + footer */}
        <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <span>{items.length} item{items.length === 1 ? '' : 's'}</span>
          {audioCount != null && <span>· {audioCount} audio</span>}
          {audioTotal != null && <span>· <span className="font-semibold text-primary">{audioTotal}</span> songs in this folder{audioTotal && entries?.audio_total_estimate ? ' (estimate)' : ''}</span>}
          <label className="ml-auto flex items-center gap-1.5">
            <Checkbox checked={audioOnly} onCheckedChange={setAudioOnly} /> Audio only
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t pt-2">
          <span className="truncate font-mono text-xs text-muted-foreground">{entries?.path || ''}</span>
          <div className="ml-auto flex gap-2">
            <Button variant="outline" onClick={onClose}>Cancel</Button>
            <Button onClick={selectFolder}><Check className="size-4" /> Select {selected?.kind === 'dir' ? 'folder' : 'this folder'}</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// A big-icon tile for the grid view (folders and files alike).
function Tile({ it, selected, onSelect, onOpen }) {
  return (
    <button
      onClick={onSelect}
      onDoubleClick={onOpen}
      title={it.path}
      className={cn(
        'relative flex flex-col items-center gap-1 rounded-lg border p-2 pt-3 text-center transition-colors',
        'hover:border-primary/50 hover:bg-accent/60',
        selected && 'border-primary bg-accent'
      )}
    >
      <div className="relative">
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
      </div>
      <span className="w-full truncate text-xs leading-tight">{it.name}</span>
      {it.kind === 'file' && <span className="w-full truncate font-mono text-[10px] text-muted-foreground">{fmtBytes(it.size)}</span>}
      {selected && <Check className="absolute right-1 top-1 size-4 text-primary" />}
    </button>
  );
}

