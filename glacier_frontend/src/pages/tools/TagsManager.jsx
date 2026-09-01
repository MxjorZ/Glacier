import { useEffect, useState } from 'react';
import { PencilLine, Save, ListMusic, ArrowUpDown, Search } from 'lucide-react';
import { api } from '../../api.js';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Input } from '@/components/ui/input.jsx';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select.jsx';
import { PageHeader, Empty } from '../../components/PageHeader.jsx';
import { toast } from '../../toast.jsx';

const FIELDS = [
  { value: 'title', label: 'Title' },
  { value: 'artist', label: 'Artist' },
  { value: 'albumartist', label: 'Album artist' },
  { value: 'album', label: 'Album' },
  { value: 'genre', label: 'Genre' },
  { value: 'date', label: 'Year / Date' },
  { value: 'track', label: 'Track number' },
  { value: 'rating', label: 'Rating (0–100)' },
  { value: 'isrc', label: 'ISRC' },
];

// Tags editor: library-first like the Genre Manager. Pick a library, search
// (server-side), page through it, check tracks, write one field to the
// selection. Large batches run as background jobs with progress/ETA.
export default function Tags() {
  const [items, setItems] = useState([]);
  const [field, setField] = useState('title');
  const [value, setValue] = useState('');
  const [sel, setSel] = useState(new Set());
  const [busy, setBusy] = useState(false);

  const [libs, setLibs] = useState([]);
  const [libId, setLibId] = useState('');
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(50);
  const [total, setTotal] = useState(0);
  const [sort, setSort] = useState('title');
  const [order, setOrder] = useState('asc');
  const [q, setQ] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    api.settings().then((s) => {
      const l = s.libraries || [];
      setLibs(l);
      if (l.length) setLibId(l[0].id);
    }).catch(() => {});
  }, []);

  const browse = async () => {
    if (!libId) return;
    setBusy(true);
    try {
      const res = await api.tracks({ library_id: libId, page, per_page: perPage, sort, order, query: q });
      setItems(res.items || []);
      setTotal(res.total || 0);
      setSel(new Set((res.items || []).map((_, i) => i)));
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    if (libId) browse(); // eslint-disable-line react-hooks/exhaustive-deps
  }, [libId, page, perPage, sort, order, q]);

  const toggle = (i) => {
    const next = new Set(sel);
    if (next.has(i)) next.delete(i); else next.add(i);
    setSel(next);
  };

  const toggleAll = () => {
    setSel(sel.size === items.length ? new Set() : new Set(items.map((_, i) => i)));
  };

  const apply = async () => {
    const selected = items.map((_, i) => i).filter((i) => sel.has(i)).map((i) => items[i].path);
    if (!selected.length) return toast.warn('Select at least one track');
    setBusy(true);
    try {
      const res = await api.tagSave(selected, field, value);
      if (res?.applied != null) {
        toast.success(`Updated ${res.applied} file(s)`);
        if (res.errors?.length) toast.error(`${res.errors.length} failed`);
      } else if (res?.job) {
        toast.info('Tagging started — watch the Activity Dock for progress');
      }
      await browse();
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

  const filteredItems = items.filter((it) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.trim().toLowerCase();
    const fields = ['title', 'artist', 'albumartist', 'album', 'genre', 'year'];
    return fields.some((f) => {
      const val = (it.tags && it.tags[f] !== undefined) ? it.tags[f] : it[f];
      return val && String(val).toLowerCase().includes(q);
    });
  });

  return (
    <div>
      <PageHeader title="Tags" description="Edit metadata across an entire library — search, page, select, apply." />

      <Card className="mb-4">
        <CardHeader className="border-b">
          <CardTitle className="flex items-center gap-2"><ListMusic className="size-4 text-primary" /> Browse a library</CardTitle>
          <CardDescription>Pick a library, search anything, edit tags in pages.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3 pt-4">
          <div className="min-w-44 space-y-1.5">
            <label className="text-xs text-muted-foreground">Library</label>
            <Select value={libId} onValueChange={(v) => { setLibId(v); setPage(1); }}>
              <SelectTrigger className="w-full"><SelectValue placeholder="Select a library" /></SelectTrigger>
              <SelectContent>
                {libs.map((l) => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="min-w-40 flex-1 space-y-1.5">
            <label className="text-xs text-muted-foreground">Search ({(total || 0).toLocaleString()} tracks)</label>
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

      <Card>
        <CardHeader className="border-b">
          <CardTitle className="flex items-center gap-2"><PencilLine className="size-4 text-primary" /> Editing</CardTitle>
          <CardDescription>{items.length} track(s) on this page{libId ? ` of ${(total || 0).toLocaleString()}` : ''} · {sel.size} selected</CardDescription>
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

          <div className="flex items-center gap-2">
            <Search className="size-4 text-muted-foreground" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filter the loaded page by title, artist, album, or genre…"
              className="max-w-md"
            />
          </div>

          {items.length === 0 ? <Empty text="Pick a library above to start editing tags." /> : (
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
                  {filteredItems.map((it) => {
                    const originalIndex = items.indexOf(it);
                    return (
                      <tr key={it.path} className={sel.has(originalIndex) ? 'bg-primary/5' : ''}>
                        <td className="px-3 py-2">
                          <input type="checkbox" checked={sel.has(originalIndex)} onChange={() => toggle(originalIndex)} />
                        </td>
                        <td className="px-3 py-2 font-medium">{shown(it, 'title')}</td>
                        <td className="px-3 py-2">{shown(it, 'artist')}</td>
                        <td className="px-3 py-2">{shown(it, 'album')}</td>
                        <td className="px-3 py-2">{shown(it, 'genre')}</td>
                        <td className="px-3 py-2">{shown(it, 'year')}</td>
                        <td className="px-3 py-2 font-mono text-xs text-muted-foreground">{it.path}</td>
                      </tr>
                    );
                  })}
                  {filteredItems.length === 0 && (
                    <tr><td colSpan="7" className="p-4 text-center text-muted-foreground">No tracks match your filter.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
