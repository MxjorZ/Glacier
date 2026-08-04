import { useEffect, useState } from 'react';
import { Folder, HardDrive, ChevronLeft } from 'lucide-react';
import { api } from './api.js';
import { Modal } from './components/dialog-helpers.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Input } from '@/components/ui/input.jsx';
import { DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog.jsx';

// Folder browser modal used by the library picker.
export default function FolderPicker({ open, onClose, onSelect }) {
  const [path, setPath] = useState('');
  const [entries, setEntries] = useState(null);
  const [error, setError] = useState('');

  const load = (p) => {
    setError('');
    api.listDir(p)
      .then((d) => { setPath(d.path || ''); setEntries(d); })
      .catch((e) => setError(e.message));
  };

  useEffect(() => { if (open) load(''); }, [open]);

  const dirs = entries?.dirs || [];
  const isRoot = entries?.path === null;

  return (
    <Modal open={open} onClose={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Browse folders</DialogTitle>
          <DialogDescription>Navigate to a music library folder, then choose it.</DialogDescription>
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
          {dirs.map((d) => (
            <button key={d.path} onClick={() => load(d.path)} className="flex w-full items-center gap-2 border-b border-border/50 px-3 py-2 text-left text-sm hover:bg-accent">
              {isRoot ? <HardDrive className="size-4 text-muted-foreground" /> : <Folder className="size-4 text-primary" />}
              <span className="truncate">{d.name}</span>
              {isRoot && <span className="ml-auto truncate font-mono text-xs text-muted-foreground">{d.path}</span>}
            </button>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => load('')}>Root</Button>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={() => { onSelect(path); onClose(); }}>Use this folder</Button>
        </DialogFooter>
      </DialogContent>
    </Modal>
  );
}
