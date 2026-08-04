import { useEffect, useState } from 'react';
import { FolderOpen, PencilLine, Save, Folder } from 'lucide-react';
import { api } from '../api.js';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Input, Textarea } from '@/components/ui/input.jsx';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select.jsx';
import { PageHeader, Empty } from '../components/PageHeader.jsx';
import { FolderPicker } from './tag-folder-picker.jsx';
import { toast } from '../toast.jsx';

const FIELDS = [
  { value: 'title', label: 'Title' },
  { value: 'artist', label: 'Artist' },
  { value: 'albumartist', label: 'Album artist' },
  { value: 'album', label: 'Album' },
  { value: 'genre', label: 'Genre' },
  { value: 'year', label: 'Year' },
  { value: 'track', label: 'Track number' },
  { value: 'rating', label: 'Rating (0–100)' },
  { value: 'comment', label: 'Comment' },
];

export default function Tags() {
  const [paths, setPaths] = useState('');
  const [items, setItems] = useState([]);
  const [picker, setPicker] = useState(false);
  const [field, setField] = useState('title');
  const [value, setValue] = useState('');
  const [sel, setSel] = useState(new Set());
  const [busy, setBusy] = useState(false);

  const pathList = () => paths.split(/[\r\n]+/).map((s) => s.trim()).filter(Boolean);

  const load = async (p) => {
    setBusy(true);
    try {
      const res = await api.tagRead(p || pathList());
      setItems(res.items || []);
      setSel(new Set((res.items || []).map((_, i) => i)));
      toast.success(`Loaded ${(res.items || []).length} files`);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => { if (items.length === 0) load(); /* eslint-disable-line */ }, []);

  const toggle = (i) => {
    const next = new Set(sel);
    if (next.has(i)) next.delete(i); else next.add(i);
    setSel(next);
  };

  const toggleAll = () => {
    setSel(sel.size === items.length ? new Set() : new Set(items.map((_, i) => i)));
  };

  const apply = async () => {
    const idx = items.map((_, i) => i).filter((i) => sel.has(i));
    const selected = idx.map((i) => items[i].path);
    if (!selected.length) return toast.warn('Select at least one track');
    setBusy(true);
    try {
      const res = await api.tagSave(selected, field, value);
      toast.success(`Updated ${res.applied} file(s)`);
      if (res.errors?.length) toast.error(`${res.errors.length} failed`);
      await load(pathList());
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  const shown = (it, k) => {
    const v = it[k];
    if (v == null || v === '') return '—';
    return String(v);
  };

  return (
    <div>
      <PageHeader title="Tags" description="Read and edit metadata on your files in batch.">
        <Button variant="outline" onClick={() => setPicker(true)}>
          <Folder className="size-4" /> Browse folder
        </Button>
        <Button onClick={() => load()} disabled={busy || pathList().length === 0}>
          <FolderOpen className="size-4" /> Load
        </Button>
      </PageHeader>

      <Card className="mb-4">
        <CardHeader className="border-b">
          <CardTitle>File paths</CardTitle>
          <CardDescription>One file or folder per line. Folder lines are resolved to audio files.</CardDescription>
        </CardHeader>
        <CardContent className="pt-4">
          <Textarea
            value={paths}
            onChange={(e) => setPaths(e.target.value)}
            placeholder={'C:\\Music\\Album A\\\nC:\\Music\\Album B\\track.flac'}
            rows={4}
            className="font-mono text-xs"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="border-b">
          <CardTitle className="flex items-center gap-2"><PencilLine className="size-4 text-primary" /> Editing</CardTitle>
          <CardDescription>{items.length} track(s) loaded · {sel.size} selected</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 pt-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-40 space-y-1.5">
              <label className="text-xs text-muted-foreground">Field</label>
              <Select value={field} onValueChange={setField}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {FIELDS.map((f) => <SelectItem key={f.value} value={f.value}>{f.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="min-w-52 flex-1 space-y-1.5">
              <label className="text-xs text-muted-foreground">New value</label>
              <Input value={value} onChange={(e) => setValue(e.target.value)} placeholder="Value to write to selected tracks" />
            </div>
            <Button onClick={apply} disabled={busy || !field || sel.size === 0}>
              <Save className="size-4" /> Apply to selected
            </Button>
          </div>


          {items.length === 0 ? <Empty text="Load a path to begin editing tags." /> : (
            <div className="overflow-auto rounded-lg border">
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="w-10 px-3 py-2">
                      <input type="checkbox" checked={sel.size === items.length} onChange={toggleAll} />
                    </th>
                    <th className="px-3 py-2">Title</th>
                    <th className="px-3 py-2">Artist</th>
                    <th className="px-3 py-2">Album</th>
                    <th className="px-3 py-2">Path</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {items.map((it, i) => (
                    <tr key={i} className={sel.has(i) ? 'bg-primary/5' : ''}>
                      <td className="px-3 py-2">
                        <input type="checkbox" checked={sel.has(i)} onChange={() => toggle(i)} />
                      </td>
                      <td className="px-3 py-2 font-medium">{shown(it, 'title')}</td>
                      <td className="px-3 py-2">{shown(it, 'artist')}</td>
                      <td className="px-3 py-2">{shown(it, 'album')}</td>
                      <td className="px-3 py-2 font-mono text-xs text-muted-foreground">{it.path}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <FolderPicker open={picker} onClose={() => setPicker(false)} onSelect={(p) => { setPaths((old) => (old ? old + '\n' : '') + p); setPicker(false); }} />
    </div>
  );
}

