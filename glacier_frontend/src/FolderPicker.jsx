import { useEffect, useMemo, useState } from 'react';
import { Folder, FolderOpen, HardDrive, ChevronRight, ChevronLeft, Music2, FileText, Search, Home, Loader2 } from 'lucide-react';
import { api, fmtBytes } from './api.js';
import { Modal } from './components/dialog-helpers.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Input } from '@/components/ui/input.jsx';
import { Checkbox } from '@/components/ui/checkbox.jsx';
import { DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog.jsx';

// Build clickable breadcrumb segments from an absolute path.
// Handles Linux (/, /home/user/...) and Windows drives (C:\...).
function buildCrumbs(p) {
  if (!p) return [];
  const win = /^[A-Za-z]:/.test(p);
  const sep = p.includes('/') ? '/' : '\\';
  const rest = win
    ? p.slice(2).split(/[\\/]/).filter(Boolean)
    : p.split(sep).filter(Boolean);
  const driveRoot = win ? p[0] + ':\\' : sep;
  const roots = win ? [{ label: p[0] + ':', path: driveRoot }]
                    : [{ label: '/', path: sep }];
  const segs = [];
  let acc = sep;
  for (const part of rest) {
    segs.push(part);
    acc = win ? driveRoot + segs.join('\\') : sep + segs.join(sep);
    roots.push({ label: part, path: acc });
  }
  return roots;
}

const FILE_PAGE = 300;

// Full file-explorer folder browser: breadcrumb hierarchy, every folder and
// every file, song counts, a name filter, and load-more pagination, so you can
// find the correct folder to use as a library.
export default function FolderPicker({ open, onClose, onSelect }) {
  const [path, setPath] = useState('');
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [audioOnly, setAudioOnly] = useState(false); // show ALL files by default
  const [query, setQuery] = useState('');
  const [filePage, setFilePage] = useState(FILE_PAGE);

  const load = (p) => {
    setBusy(true);
    setError('');
    setFilePage(FILE_PAGE);
    api.listDir(p)
      .then((d) => { setPath(d.path || ''); setEntries(d); })
      .catch((e) => setError(e.message))
      .finally(() => setBusy(false));
  };

  useEffect(() => { if (open) { setQuery(''); load(''); } }, [open]);

  const crumbs = buildCrumbs(path);
  const dirs = entries?.dirs || [];
  const allFiles = entries?.files || [];
  const audioTotal = entries?.audio_total;
  const isRoot = entries?.path === null;

  // Apply the audio filter and the text search together.
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    const wantFile = (f) => (audioOnly ? f.audio : true) && (!q || f.name.toLowerCase().includes(q));
    const wantDir = (d) => !q || d.name.toLowerCase().includes(q);
    return { dirs: dirs.filter(wantDir), files: allFiles.filter(wantFile) };
  }, [dirs, allFiles, audioOnly, query]);

  const filesShown = visible.files.slice(0, filePage);
  const hasMoreFiles = filePage < visible.files.length;

  return (
    <Modal open={open} onClose={onClose}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle><span className="inline-flex items-center gap-2"><FolderOpen className="size-4 text-primary" /> Browse folders</span></DialogTitle>
          <DialogDescription>
            Explore your files like a file explorer. Use the breadcrumbs to jump
            between folders, then choose the folder to use as a library.
          </DialogDescription>
        </DialogHeader>

        {/* Breadcrumb hierarchy — always see where you are and every parent */}
        <div className="flex items-center gap-1 overflow-x-auto rounded-lg border bg-card/40 px-2 py-1.5 text-sm">
          {crumbs.length === 0 ? (
            <span className="px-2 text-muted-foreground">Browse</span>
          ) : (
            crumbs.map((c, i) => {
              const last = i === crumbs.length - 1;
              return (
                <span key={c.path} className="flex shrink-0 items-center">
                  {i > 0 && <ChevronRight className="size-3.5 text-muted-foreground" />}
                  {last ? (
                    <span className="cursor-default truncate rounded px-2 py-0.5 font-medium text-primary">{c.label}</span>
                  ) : (
                    <button onClick={() => load(c.path)} className="truncate rounded px-2 py-0.5 text-muted-foreground hover:bg-accent hover:text-foreground">
                      {c.label}
                    </button>
                  )}
                </span>
              );
            })
          )}
        </div>

        {/* Actions + search */}
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => load('')}><Home className="size-4" /> Browse roots</Button>
          {entries?.parent && (
            <Button variant="ghost" size="sm" onClick={() => load(entries.parent)}>
              <ChevronLeft className="size-4" /> Up
            </Button>
          )}
          <div className="relative min-w-40 flex-1">
            <Search className="absolute left-2 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter by name…" className="pl-8" />
          </div>
        </div>

        {error && <p className="text-destructive text-xs">{error}</p>}
        {busy && <p className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="size-3.5 animate-spin" /> Loading…</p>}

        <div className="max-h-96 overflow-auto rounded-lg border bg-card/40">
          {visible.dirs.map((d) => (
            <button key={d.path} onClick={() => load(d.path)} className="flex w-full items-center gap-2 border-b border-border/50 px-3 py-2 text-left text-sm hover:bg-accent">
              {isRoot ? <HardDrive className="size-4 shrink-0 text-muted-foreground" /> : <Folder className="size-4 shrink-0 text-primary" />}
              <span className="truncate">{d.name}</span>
              {d.audio != null && (
                <span className="ml-auto shrink-0 rounded-full bg-muted px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
                  {d.audio > 0 ? `${d.audio} song${d.audio === 1 ? '' : 's'}` : 'no songs'}{d.audio_estimate ? '+' : ''}
                </span>
              )}
            </button>
          ))}

          {visible.files.length > 0 && (
            <div className="sticky top-0 border-b border-border/40 bg-card px-3 py-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Files {audioOnly ? '(audio)' : '(all)'} · {visible.files.length}
              {entries?.files_total != null && visible.files.length !== entries.files_total && ` of ${entries.files_total}`}
            </div>
          )}
          {filesShown.map((f) => (
            <div key={f.path} className="flex w-full items-center gap-2 border-b border-border/30 px-3 py-1.5 text-left text-sm">
              {f.audio ? <Music2 className="size-4 shrink-0 text-primary" /> : <FileText className="size-4 shrink-0 text-muted-foreground" />}
              <span className="truncate">{f.name}</span>
              <span className="ml-auto shrink-0 font-mono text-xs text-muted-foreground">{fmtBytes(f.size)}</span>
            </div>
          ))}

          {visible.dirs.length === 0 && visible.files.length === 0 && (
            <div className="px-3 py-8 text-center text-sm text-muted-foreground">
              {query ? 'No matches for your filter.' : (isRoot ? 'No drives/mounts found.' : 'This folder is empty.')}
            </div>
          )}

          {hasMoreFiles && (
            <button onClick={() => setFilePage((n) => n + FILE_PAGE)} className="w-full px-3 py-2 text-center text-xs font-medium text-muted-foreground hover:bg-accent">
              Load more files (showing {filesShown.length} of {visible.files.length})
            </button>
          )}
        </div>

        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <Checkbox checked={audioOnly} onCheckedChange={setAudioOnly} />
          Show only audio files
        </label>

        <DialogFooter>
          <div className="mr-auto text-xs text-muted-foreground">
            {audioTotal != null && (
              <span className="font-medium text-primary">{audioTotal} song{audioTotal === 1 ? '' : 's'}</span>
            )}
            {audioTotal != null && <span> in this folder{audioTotal && entries?.audio_total_estimate ? ' (estimate)' : ''}</span>}
            {path && <span className="ml-1 font-mono truncate">{path}</span>}
          </div>
          <Button variant="outline" onClick={() => load('')}>Root</Button>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={() => { onSelect(path); onClose(); }}>Use this folder</Button>
        </DialogFooter>
      </DialogContent>
    </Modal>
  );
}

