import { useEffect, useState } from 'react';
import { FolderOpen, PencilLine, Save, Folder, ListMusic, ArrowUpDown } from 'lucide-react';
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

  // Stage 4 #10: large-scale library browser with pagination.
  const [libs, setLibs] = useState([]);
  const [libId, setLibId] = useState('');
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(50);
  const [total, setTotal] = useState(0);
  const [sort, setSort] = useState('title');
  const [order, setOrder] = useState('asc');
  const [q, setQ] = useState('');
  const [loadedLib, setLoadedLib] = useState(false);

  useEffect(() => {
    api.settings().then((s) => { setLibs(s.libraries || []); }).catch(() => {});
  }, []);

  const pathList = () => paths.split(/[\r\n]+/).map((s) => s.trim()).filter(Boolean);

  const load = async (p) => {
    setBusy(true);
    try {
      const res = await api.tagRead(p || pathList());
      setItems(res.items || []);
      setSel(new Set((res.items || []).map((_, i) => i)));
      setLoadedLib(false);
      toast.success(`Loaded ${(res.items || []).length} files`);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  // Load a page of tracks from a library (Stage 4 #10).
  const browse = async () => {
    if (!libId) return;
    setBusy(true);
    try {
      const res = await api.tracks({ library_id: libId, page, per_page: perPage, sort, order, query: q });
      setItems(res.items || []);
      setTotal(res.total || 0);
      setSel(new Set((res.items || []).map((_, i) => i)));
      setLoadedLib(true);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    if (libId) browse(); // eslint-disable-line react-hooks/exhaustive-deps
  }, [libId, page, perPage, sort, order, q]);

  const refreshCurrent = async () => {
    if (loadedLib) await browse();
    else await load(pathList());
  };

  useEffect(() => { if (items.length === 0 && !libId) load(); /* eslint-disable-line */ }, []);

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
      await refreshCurrent();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  const shown = (it, k) => {
    const v = (it.tags && it.tags[k] !== undefined) ? it.tags[k] : it[k];
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

      {/* Stage 4 #10: browse a whole library with pagination */}
      <Card className="mb-4">
        <CardHeader className="border-b">
          <CardTitle className="flex items-center gap-2"><ListMusic className="size-4 text-primary" /> Browse a library</CardTitle>
          <CardDescription>Work through an entire library in pages — perfect for large collections.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3 pt-4">
          <div className="min-w-44 space-y-1.5">
            <label className="text-xs text-muted-foreground">Library</label>
            <Select value={libId} onValueChange={(v) => { setLibId(v); setPage(1); }}>
              <SelectTrigger className="w-full"><SelectValue placeholder="None (manual paths)" /></SelectTrigger>
              <SelectContent>
                {libs.map((l) => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="min-w-40 flex-1 space-y-1.5">
            <label className="text-xs text-muted-foreground">Search ({total.toLocaleString?.() || total} tracks)</label>
            <Input value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder="Title / artist / album / genre…" />
          </div>
          <div className="min-w-32 space-y-1.5">
            <label className="text-xs text-muted-foreground">Sort by</label>
            <Select value={sort} onValueChange={(v) => { setSort(v); setPage(1); }}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                {['title', 'artist', 'album', 'genre'].map((s) => <SelectItem key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <Button size="icon" variant="outline" onClick={() => setOrder((o) => (o === 'asc' ? 'desc' : 'asc'))} title="Toggle order">
            <ArrowUpDown className="size-4" />
          </Button>
          <div className="min-w-32 space-y-1.5">
            <label className="text-xs text-muted-foreground">Per page</label>
            <Select value={String(perPage)} onValueChange={(v) => { setPerPage(Number(v)); setPage(1); }}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                {[20, 50, 100].map((n) => <SelectItem key={n} value={String(n)}>{n}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-1 pb-1">
            <Button size="sm" variant="outline" disabled={page <= 1 || !libId} onClick={() => setPage((p) => Math.max(1, p - 1))}>Prev</Button>
            <span className="px-2 text-sm">Page {page}</span>
            <Button size="sm" variant="outline" disabled={!libId || page * perPage >= total} onClick={() => setPage((p) => p + 1)}>Next</Button>
          </div>
        </CardContent>
      </Card>

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
            rows={2}
            className="font-mono text-xs"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="border-b">
          <CardTitle className="flex items-center gap-2"><PencilLine className="size-4 text-primary" /> Editing</CardTitle>
          <CardDescription>{items.length} track(s) on this page{libId ? ` of ${total}` : ''} · {sel.size} selected</CardDescription>
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
                    <th className="px-3 py-2">Genre</th>
                    <th className="px-3 py-2">Year</th>
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
                      <td className="px-3 py-2">{shown(it, 'genre')}</td>
                      <td className="px-3 py-2">{shown(it, 'year')}</td>
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

