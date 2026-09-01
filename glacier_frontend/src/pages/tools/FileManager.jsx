import { useEffect, useState, useRef } from 'react';
import {
  FolderOpen, Folder, FileAudio, File as FileIcon, ArrowUp, RefreshCw,
  Pencil, Trash2, FolderInput, Copy, FolderPlus, CheckSquare, Loader2, Home,
} from 'lucide-react';
import { api } from '../../api.js';
import { useJob } from '../../useJob.js';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Input } from '@/components/ui/input.jsx';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select.jsx';
import { Badge } from '@/components/ui/badge.jsx';
import { Empty } from '../../components/PageHeader.jsx';
import { Confirm } from '../../components/dialog-helpers.jsx';
import { toast } from '../../toast.jsx';
import { cn } from '@/lib/utils.js';
import { fmtBytes } from '../../api.js';

// File Manager: browse inside a library, rename, move/copy into other folders,
// create folders, and delete — with the same safety rules as the rest of
// Glacier (confirm dialogs, audio folders refuse bulk deletion).
export default function FileManager() {
  const [libs, setLibs] = useState([]);
  const [libId, setLibId] = useState('');
  const [entries, setEntries] = useState(null);
  const [path, setPath] = useState('');
  const [busy, setBusy] = useState(false);
  const [checked, setChecked] = useState(new Set());
  const [renameTarget, setRenameTarget] = useState(null);
  const [renameVal, setRenameVal] = useState('');
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [moveOpen, setMoveOpen] = useState(false);
  const [newFolderOpen, setNewFolderOpen] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const { running, run } = useJob();
  const renameInput = useRef(null);

  useEffect(() => {
    api.settings().then((s) => {
      const l = s.libraries || [];
      setLibs(l);
      if (l.length) setLibId(l[0].id);
    }).catch(() => {});
  }, []);

  // Load a folder (reuses the fast, cached list-dir endpoint).
  const load = async (p = '') => {
    setBusy(true);
    try {
      const d = await api.listDir(p || (libId ? libs.find((l) => l.id === libId)?.path : ''));
      setEntries(d);
      setPath(d.path || '');
      setChecked(new Set());
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (libId && libs.length) load('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [libId]);

  const lib = libs.find((l) => l.id === libId);
  const libRoot = lib ? lib.path : '';

  const crumbs = (() => {
    if (!path) return [];
    const win = /^[A-Za-z]:/.test(path);
    const rest = win ? path.slice(2).split(/[\\/]/).filter(Boolean) : path.split('/').filter(Boolean);
    const root = win ? path[0] + ':\\' : '/';
    const out = [{ label: lib?.name || 'Root', path: libRoot || root }];
    const segs = [];
    for (const part of rest) {
      segs.push(part);
      out.push({ label: part, path: win ? root + segs.join('\\') : '/' + segs.join('/') });
    }
    return out;
  })();

  const dirs = entries?.dirs || [];
  const files = entries?.files || [];
  const toggle = (p) => setChecked((cur) => {
    const next = new Set(cur);
    if (next.has(p)) next.delete(p); else next.add(p);
    return next;
  });

  const checkedPaths = [...checked];

  const doRename = async () => {
    if (!renameTarget || !renameVal.trim()) return;
    try {
      const res = await api.post('/api/files/rename', {
        path: renameTarget.path, name: renameVal.trim(), library_id: libId,
      });
      if (res.ok) { toast.success('Renamed'); setRenameTarget(null); load(path); }
      else toast.error(res.error);
    } catch (e) { toast.error(e.message); }
  };

  const doDelete = async () => {
    setDeleteOpen(false);
    const res = await run('file-delete', { paths: checkedPaths, library_id: libId, confirm: true });
    if (res?.ok) {
      toast.success(`Deleted ${res.deleted} item(s)`);
      if (res.errors?.length) toast.error(`${res.errors.length} refused (check for remaining audio)`);
      load(path);
    } else toast.error(res?.error || 'Delete failed');
  };

  const doMove = async (dest, copy) => {
    setMoveOpen(false);
    const res = await run('file-move', { paths: checkedPaths, dest, library_id: libId, copy });
    if (res?.ok) { toast.success(`${copy ? 'Copied' : 'Moved'} ${res.moved} item(s)`); load(path); }
    else toast.error(res?.error || 'Move failed');
  };

  const doNewFolder = async () => {
    setNewFolderOpen(false);
    try {
      const res = await api.post('/api/files/new-folder', {
        path: path || libRoot, name: newFolderName, library_id: libId,
      });
      if (res.ok) { toast.success('Folder created'); setNewFolderName(''); load(path); }
      else toast.error(res.error);
    } catch (e) { toast.error(e.message); }
  };

  const isAudio = (f) => !!f.audio;

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <Card>
        <CardHeader className="border-b">
          <CardTitle className="flex items-center gap-2"><FolderOpen className="size-4 text-primary" /> File Manager</CardTitle>
          <CardDescription>Browse, rename, move and delete inside your libraries — safely</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 pt-4">
          <div className="flex flex-wrap items-center gap-2">
            <Select value={libId} onValueChange={setLibId}>
              <SelectTrigger className="w-52"><SelectValue placeholder="Select a library" /></SelectTrigger>
              <SelectContent>
                {libs.map((l) => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
              </SelectContent>
            </Select>
            <Button variant="ghost" size="icon-sm" title="Library root" onClick={() => load(libRoot)}>
              <Home className="size-4" />
            </Button>
            <Button variant="ghost" size="icon-sm" title="Up one level" disabled={crumbs.length <= 1}
              onClick={() => load(crumbs[crumbs.length - 2]?.path)}>
              <ArrowUp className="size-4" />
            </Button>
            <Button variant="ghost" size="icon-sm" title="Refresh" onClick={() => load(path)}>
              <RefreshCw className={cn('size-4', busy && 'animate-spin')} />
            </Button>
            <Button variant="outline" size="sm" onClick={() => setNewFolderOpen(true)} disabled={!libId}>
              <FolderPlus className="size-3.5" /> New folder
            </Button>
            <div className="ml-auto flex flex-wrap items-center gap-2">
              <Button variant="outline" size="sm" disabled={checked.size === 0 || running}
                onClick={() => setMoveOpen(true)}>
                <FolderInput className="size-3.5" /> Move {checked.size > 0 && `(${checked.size})`}
              </Button>
              <Button variant="destructive" size="sm" disabled={checked.size === 0 || running}
                onClick={() => setDeleteOpen(true)}>
                <Trash2 className="size-3.5" /> Delete {checked.size > 0 && `(${checked.size})`}
              </Button>
            </div>
          </div>

          {/* Breadcrumbs */}
          <div className="glass-surface flex items-center gap-1 overflow-x-auto rounded-xl px-2.5 py-1.5 text-xs">
            {crumbs.map((c, i) => (
              <span key={c.path + i} className="flex shrink-0 items-center gap-1">
                {i > 0 && <span className="text-muted-foreground/50">/</span>}
                <button onClick={() => load(c.path)}
                  className={cn('rounded px-1.5 py-0.5 whitespace-nowrap transition-all hover:bg-white/10 hover:scale-105',
                    i === crumbs.length - 1 ? 'font-medium text-foreground' : 'text-muted-foreground')}>
                  {c.label}
                </button>
              </span>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Listing */}
      <Card>
        <CardContent className="pt-4">
          {!libId ? <Empty text="Select a library to browse its files." /> : (
            <div className="overflow-auto rounded-xl">
              <table className="w-full text-sm">
                <thead className="border-b text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="w-10 px-3 py-2" />
                    <th className="px-3 py-2">Name</th>
                    <th className="hidden px-3 py-2 sm:table-cell">Type</th>
                    <th className="hidden px-3 py-2 md:table-cell">Size</th>
                    <th className="w-24 px-3 py-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {busy && (
                    <tr><td colSpan={5} className="p-6 text-center text-muted-foreground">
                      <Loader2 className="mr-2 inline size-4 animate-spin" /> Loading…
                    </td></tr>
                  )}
                  {!busy && dirs.length === 0 && files.length === 0 && (
                    <tr><td colSpan={5} className="p-6"><Empty text="This folder is empty." /></td></tr>
                  )}
                  {dirs.map((d) => (
                    <tr key={d.path} className="group transition-colors hover:bg-white/5">
                      <td className="px-3 py-2">
                        <input type="checkbox" checked={checked.has(d.path)} onChange={() => toggle(d.path)} className="size-4 accent-[var(--primary)]" />
                      </td>
                      <td className="px-3 py-2">
                        <button onClick={() => load(d.path)}
                          className="flex items-center gap-2 text-left transition-all hover:translate-x-0.5 hover:text-primary">
                          <Folder className="size-4 shrink-0 text-amber-400/90" />
                          <span className="truncate font-medium">{d.name}</span>
                          {d.audio > 0 && <Badge variant="secondary" className="font-mono text-[10px]">{d.audio}</Badge>}
                        </button>
                      </td>
                      <td className="hidden px-3 py-2 text-xs text-muted-foreground sm:table-cell">Folder</td>
                      <td className="hidden px-3 py-2 font-mono text-xs text-muted-foreground md:table-cell">—</td>
                      <td className="px-3 py-2 text-right">
                        <div className="flex justify-end gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                          <Button variant="ghost" size="icon-sm" title="Rename"
                            onClick={() => { setRenameTarget({ path: d.path, name: d.name }); setRenameVal(d.name); }}>
                            <Pencil className="size-3.5" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {files.map((f) => (
                    <tr key={f.path} className="group transition-colors hover:bg-white/5">
                      <td className="px-3 py-2">
                        <input type="checkbox" checked={checked.has(f.path)} onChange={() => toggle(f.path)} className="size-4 accent-[var(--primary)]" />
                      </td>
                      <td className="px-3 py-2">
                        <span className="flex items-center gap-2">
                          {isAudio(f)
                            ? <FileAudio className="size-4 shrink-0 text-primary" />
                            : <FileIcon className="size-4 shrink-0 text-muted-foreground" />}
                          <span className="truncate">{f.name}</span>
                        </span>
                      </td>
                      <td className="hidden px-3 py-2 text-xs text-muted-foreground sm:table-cell">{f.audio ? 'Audio' : 'File'}</td>
                      <td className="hidden px-3 py-2 font-mono text-xs text-muted-foreground md:table-cell">{fmtBytes(f.size)}</td>
                      <td className="px-3 py-2 text-right">
                        <div className="flex justify-end gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                          <Button variant="ghost" size="icon-sm" title="Rename"
                            onClick={() => { setRenameTarget({ path: f.path, name: f.name }); setRenameVal(f.name); }}>
                            <Pencil className="size-3.5" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Rename inline dialog */}
      {renameTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm anim-fade"
          onClick={() => setRenameTarget(null)}>
          <div className="glass-surface-strong w-96 rounded-2xl p-4" onClick={(e) => e.stopPropagation()}>
            <p className="mb-3 text-sm font-medium">Rename “{renameTarget.name}”</p>
            <Input value={renameVal} onChange={(e) => setRenameVal(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && doRename()}
              autoFocus className="w-full" />
            <div className="mt-3 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setRenameTarget(null)}>Cancel</Button>
              <Button size="sm" onClick={doRename}><Pencil className="size-3.5" /> Rename</Button>
            </div>
          </div>
        </div>
      )}

      {/* Move destination picker (simple: pick library + type a subfolder) */}
      {moveOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm anim-fade"
          onClick={() => setMoveOpen(false)}>
          <div className="glass-surface-strong w-96 rounded-2xl p-4" onClick={(e) => e.stopPropagation()}>
            <p className="mb-1 text-sm font-medium">Move {checked.size} item(s)</p>
            <p className="mb-3 text-xs text-muted-foreground">Pick the destination library — items go to its root.</p>
            <Select value={libId} onValueChange={() => {}}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                {libs.map((l) => <SelectItem key={l.id} value={l.id}>{l.name} — {l.path}</SelectItem>)}
              </SelectContent>
            </Select>
            <div className="mt-3 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setMoveOpen(false)}>Cancel</Button>
              <Button size="sm" onClick={() => doMove(libRoot, true)} title="Copy instead of move">
                <Copy className="size-3.5" /> Copy
              </Button>
              <Button size="sm" onClick={() => doMove(libRoot, false)}>
                <FolderInput className="size-3.5" /> Move
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* New folder dialog */}
      {newFolderOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm anim-fade"
          onClick={() => setNewFolderOpen(false)}>
          <div className="glass-surface-strong w-96 rounded-2xl p-4" onClick={(e) => e.stopPropagation()}>
            <p className="mb-3 text-sm font-medium">New folder in “{crumbs[crumbs.length - 1]?.label || lib?.name}”</p>
            <Input value={newFolderName} onChange={(e) => setNewFolderName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && doNewFolder()} autoFocus placeholder="Folder name" />
            <div className="mt-3 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setNewFolderOpen(false)}>Cancel</Button>
              <Button size="sm" onClick={doNewFolder}><FolderPlus className="size-3.5" /> Create</Button>
            </div>
          </div>
        </div>
      )}

      <Confirm
        open={deleteOpen}
        onCancel={() => setDeleteOpen(false)}
        onConfirm={doDelete}
        title={`Delete ${checked.size} item(s)?`}
        message="This permanently removes the selected files/folders from disk. Folders that still contain audio are refused. This cannot be undone."
        confirmLabel="Delete"
        danger
      />
    </div>
  );
}
