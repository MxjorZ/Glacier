import { useEffect, useMemo, useState } from 'react';
import { Folder, HardDrive, ChevronLeft, Music2, FileText } from 'lucide-react';
import { api, fmtBytes } from './api.js';
import { Modal } from './components/dialog-helpers.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Input } from '@/components/ui/input.jsx';
import { Checkbox } from '@/components/ui/checkbox.jsx';
import { DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog.jsx';

// Folder browser modal used by the library picker.
// Lists folders (with recursive song counts) AND the files inside a folder
// (audio flagged), so you can confirm a folder actually contains music before
// choosing it as a library.
export default function FolderPicker({ open, onClose, onSelect }) {
  const [path, setPath] = useState('');
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState('');
  const [audioOnly, setAudioOnly] = useState(true);

  const load = (p) => {
    setError('');
    api.listDir(p)
      .then((d) => { setPath(d.path || ''); setEntries(d); })
      .catch((e) => setError(e.message));
  };

  useEffect(() => { if (open) load(''); }, [open]);

  const dirs = entries?.dirs || [];
  const allFiles = entries?.files || [];
  const audioTotal = entries?.audio_total;
  const isRoot = entries?.path === null;

  const files = useMemo(
    () => (audioOnly ? allFiles.filter((f) => f.audio) : allFiles),
    [allFiles, audioOnly],
  );

  return (
    <Modal open={open} onClose={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Browse folders</DialogTitle>
          <DialogDescription>
            Navigate to a music folder and choose it. Song counts help you find
            the folder that actually holds your music.
          </DialogDescription>
        </DialogHeader>

        <div className="flex gap-2">
          <Input value={path} onChange={(e) => setPath(e.target.value)} placeholder="Enter a path…"
            onKeyDown={(e) => e.key === 'Enter' && load(path)} />
          <Button variant="outline" onClick={() => load(path)}>Go</Button>
        </div>

        {error && <p className="text-destructive text-xs">{error}</p>}

        <div className="max-h-80 overflow-auto rounded-lg border bg-card/40">
          {entries?.parent && (
            <button onClick={() => load(entries.parent)} className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-muted-foreground hover:bg-accent">
              <ChevronLeft className="size-4" /> Up
            </button>
          )}

          {dirs.length === 0 && files.length === 0 && !entries?.parent && (
            <div className="px-3 py-8 text-center text-sm text-muted-foreground">
              {isRoot ? 'No drives/mounts found.' : 'This folder is empty.'}
            </div>
          )}

          {dirs.map((d) => (
            <button key={d.path} onClick={() => load(d.path)} className="flex w-full items-center gap-2 border-b border-border/50 px-3 py-2 text-left text-sm hover:bg-accent">
              {isRoot ? <HardDrive className="size-4 shrink-0 text-muted-foreground" /> : <Folder className="size-4 shrink-0 text-primary" />}
              <span className="truncate">{d.name}</span>
              {d.audio != null && (
                <span className="ml-auto shrink-0 rounded-full bg-muted px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
                  {d.audio > 0 ? `${d.audio} song${d.audio === 1 ? '' : 's'}` : 'no songs'}
                  {d.audio_estimate ? '+' : ''}
                </span>
              )}
              {isRoot && <span className="ml-2 hidden truncate font-mono text-xs text-muted-foreground sm:inline">{d.path}</span>}
            </button>
          ))}

          {files.length > 0 && (
            <div className="border-t border-border/40 px-2 py-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Files {audioOnly ? '(audio)' : '(all)'}
            </div>
          )}
          {files.map((f) => (
            <div key={f.path} className="flex w-full items-center gap-2 border-b border-border/30 px-3 py-1.5 text-left text-sm">
              {f.audio ? <Music2 className="size-4 shrink-0 text-primary" /> : <FileText className="size-4 shrink-0 text-muted-foreground" />}
              <span className="truncate">{f.name}</span>
              <span className="ml-auto shrink-0 font-mono text-xs text-muted-foreground">{fmtBytes(f.size)}</span>
            </div>
          ))}
        </div>

        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <Checkbox checked={audioOnly} onCheckedChange={setAudioOnly} />
          Show only audio files
        </label>

        <DialogFooter>
          <div className="mr-auto text-xs text-muted-foreground">
            {audioTotal != null
              ? <span className="font-medium text-primary">{audioTotal} song{audioTotal === 1 ? '' : 's'}</span>
              : null}
            {audioTotal != null && <span> in this folder{audioTotal && entries?.audio_total_estimate ? ' (estimate)' : ''}</span>}
            {path && <span className="ml-1 font-mono">· {path}</span>}
          </div>
          <Button variant="outline" onClick={() => load('')}>Root</Button>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={() => { onSelect(path); onClose(); }}>Use this folder</Button>
        </DialogFooter>
      </DialogContent>
    </Modal>
  );
}
