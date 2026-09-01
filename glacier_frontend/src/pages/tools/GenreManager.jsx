import { useEffect, useState } from 'react';
import { Music2, RefreshCw, Replace, Merge, Eraser, Save, Search } from 'lucide-react';
import { api } from '../../api.js';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Input } from '@/components/ui/input.jsx';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select.jsx';
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from '@/components/ui/table.jsx';
import { Empty } from '../../components/PageHeader.jsx';
import { Confirm } from '../../components/dialog-helpers.jsx';
import { toast } from '../../toast.jsx';
import { cn } from '@/lib/utils.js';

export default function GenreManager() {
  const [libs, setLibs] = useState([]);
  const [libId, setLibId] = useState('');
  const [genres, setGenres] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sel, setSel] = useState(null);
  const [op, setOp] = useState(null);
  const [mergeSel, setMergeSel] = useState(new Set());
  const [replaceTo, setReplaceTo] = useState('');
  const [mergeTo, setMergeTo] = useState('');
  const [bulkValue, setBulkValue] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [search, setSearch] = useState('');

  useEffect(() => {
    api.settings().then((s) => {
      const l = s.libraries || [];
      setLibs(l);
      if (l.length) setLibId(l[0].id);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!libId) { setGenres([]); return; }
    setLoaded(false);
    api.genres(libId).then((res) => setGenres(res?.genres || []))
      .catch((e) => toast.error(e.message)).finally(() => setLoaded(true));
  }, [libId]);

  const libName = (id) => (libs.find((l) => l.id === id) || {}).name || '—';

  const refresh = async () => {
    try { const res = await api.genres(libId); setGenres(res?.genres || []); }
    catch (e) { toast.error(e.message); }
  };

  const filteredGenres = genres.filter((g) => {
    if (!search.trim()) return true;
    const q = search.trim().toLowerCase();
    const inGenre = g.genre.toLowerCase().includes(q);
    const inRaw = (g.examples || []).some(([raw]) => raw.toLowerCase().includes(q));
    return inGenre || inRaw;
  });

  const confirmRun = async () => {
    setConfirming(false);
    setBusy(true);
    try {
      let res;
      if (op === 'replace') res = await api.runAndAwait('genres/replace', { library_id: libId, from: sel?.genre, to: replaceTo });
      else if (op === 'merge') res = await api.runAndAwait('genres/merge', { library_id: libId, from: [...mergeSel], to: mergeTo });
      else if (op === 'delete') res = await api.runAndAwait('genres/delete', { library_id: libId, genre: sel?.genre });
      else if (op === 'bulk') res = await api.runAndAwait('genres/bulk-set', { library_id: libId, value: bulkValue });
      if (res?.ok) toast.success(`${res.applied} track(s) updated in ${res.library}`);
      else toast.error(res?.error || 'Operation failed');
      await refresh();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setBusy(false); setOp(null); setSel(null); setMergeSel(new Set());
    }
  };

  const summary = genres.reduce((a, g) => ({
    tracks: a.tracks + g.tracks, albums: a.albums + g.albums, artists: a.artists + g.artists,
  }), { tracks: 0, albums: 0, artists: 0 });

  const toggleMerge = (g) => {
    const next = new Set(mergeSel);
    if (next.has(g)) next.delete(g); else next.add(g);
    setMergeSel(next);
  };

  const confirmMsg = () => {
    if (op === 'replace') return `Replace the genre “${sel?.genre}” with “${replaceTo}” in all ${sel?.tracks} matching track(s) of “${libName(libId)}”?`;
    if (op === 'merge') return `Merge ${mergeSel.size} genre(s) into “${mergeTo}” in “${libName(libId)}”?`;
    if (op === 'delete') return `Remove the genre “${sel?.genre}” from its ${sel?.tracks} track(s) in “${libName(libId)}”?`;
    if (op === 'bulk') return `Set the genre of every track in “${libName(libId)}” to “${bulkValue}”?`;
    return 'Continue?';
  };

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Select value={libId} onValueChange={setLibId}>
          <SelectTrigger className="w-52"><SelectValue /></SelectTrigger>
          <SelectContent>
            {libs.map((l) => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <div className="relative min-w-56 flex-1">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search genres (also matches full multi-genre tags)…" className="pl-8" />
        </div>
        <Button variant="outline" onClick={refresh} disabled={!libId || busy}>
          <RefreshCw className={busy ? 'size-4 animate-spin' : 'size-4'} /> Refresh
        </Button>
      </div>

      <div className="mb-4 grid grid-cols-3 gap-4">
        <MiniStat label="Genres" value={filteredGenres.length} />
        <MiniStat label="Tracks" value={summary.tracks} />
        <MiniStat label="Artists" value={summary.artists} />
      </div>

      <Card>
        <CardHeader className="border-b">
          <CardTitle className="flex items-center gap-2"><Music2 className="size-4 text-primary" /> Genres in {libName(libId)}</CardTitle>
          <CardDescription>Tap a genre (or several for merge) then choose an action below.</CardDescription>
        </CardHeader>
        <CardContent className="pt-4">
          <p className="mb-3 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-[11px] leading-relaxed text-muted-foreground">
            Tracks with multiple genres (e.g. <span className="font-mono">Electronic - Deep House; Electronic - House</span>)
            are grouped by their <span className="text-foreground">first (leftmost) genre</span> — here <span className="text-foreground">Electronic</span>.
            Transform actions rewrite the whole genre tag for every matching track.
          </p>
          {!libId ? <Empty text="Add a library first — this page groups the genres found in one library." /> :
           !loaded ? <Empty text="Loading…" /> :
           genres.length === 0 ? <Empty text="No genres found. Run a scan (Dashboard → Scan all) first." /> : (
            <div className="overflow-auto rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8" />
                    <TableHead>Genre</TableHead>
                    <TableHead>Raw tag values grouped here</TableHead>
                    <TableHead className="text-right">Tracks</TableHead>
                    <TableHead className="text-right">Albums</TableHead>
                    <TableHead className="text-right">Artists</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredGenres.map((g) => (
                    <TableRow key={g.genre}
                      className={cn('cursor-pointer', (op === 'merge' && mergeSel.has(g.genre)) ? 'bg-primary/10' : sel?.genre === g.genre ? 'bg-primary/5' : '')}
                      onClick={() => {
                        if (op === 'merge') toggleMerge(g.genre);
                        else setSel(sel?.genre === g.genre ? null : g);
                      }}>
                      <TableCell><input type="checkbox" readOnly checked={op === 'merge' ? mergeSel.has(g.genre) : sel?.genre === g.genre} /></TableCell>
                      <TableCell className="font-medium">{g.genre}</TableCell>
                      <TableCell className="max-w-72">
                        {(g.examples || []).length === 0 ? <span className="text-muted-foreground">—</span> : (
                          <div className="flex flex-wrap gap-1">
                            {g.examples.slice(0, 3).map(([raw, n]) => (
                              <span key={raw} title={`${n} track(s)`}
                                className="truncate rounded-full border border-white/10 bg-white/5 px-2 py-0.5 font-mono text-[10px] text-muted-foreground">
                                {raw}
                              </span>
                            ))}
                            {g.examples.length > 3 && (
                              <span className="text-[10px] text-muted-foreground">+{g.examples.length - 3} more</span>
                            )}
                          </div>
                        )}
                      </TableCell>
                      <TableCell className="text-right font-mono">{g.tracks}</TableCell>
                      <TableCell className="text-right font-mono">{g.albums}</TableCell>
                      <TableCell className="text-right font-mono">{g.artists}</TableCell>
                    </TableRow>
                  ))}
                  {filteredGenres.length === 0 && (
                    <TableRow><TableCell colSpan={6} className="p-4 text-center text-muted-foreground">No genres match “{search}”.</TableCell></TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
      {/* Actions */}
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="border-b"><CardTitle className="text-sm">Replace or Remove</CardTitle><CardDescription>Change one genre into another, or strip it entirely.</CardDescription></CardHeader>
          <CardContent className="space-y-3 pt-4">
            <div className="flex items-end gap-2">
              <div className="flex-1 space-y-1.5">
                <label className="text-xs text-muted-foreground">Replace “{sel?.genre || '…'}” with</label>
                <Input value={replaceTo} onChange={(e) => { setOp('replace'); setReplaceTo(e.target.value); }} placeholder="New genre name" disabled={!sel} />
              </div>
              <Button disabled={!sel || !replaceTo.trim() || busy} onClick={() => setConfirming(true)}><Replace className="size-4" /> Replace</Button>
            </div>
            <div className="flex items-center justify-between rounded-lg border bg-muted/30 px-3 py-2 text-sm">
              <span>Remove “{sel?.genre || '…'}” from its tracks</span>
              <Button variant="outline" size="sm" disabled={!sel || busy} onClick={() => { setOp('delete'); setConfirming(true); }}><Eraser className="size-4" /> Delete</Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b"><CardTitle className="text-sm">Merge or set all</CardTitle><CardDescription>Combine genres into one, or set every track to a single genre.</CardDescription></CardHeader>
          <CardContent className="space-y-3 pt-4">
            <div className="flex items-end gap-2">
              <div className="flex-1 space-y-1.5">
                <label className="text-xs text-muted-foreground">Merge {mergeSel.size ? `${mergeSel.size} selected` : '(select genres…)'} into</label>
                <Input value={mergeTo} onChange={(e) => { setOp('merge'); setMergeTo(e.target.value); }} placeholder="Merge destination genre" />
              </div>
              <Button disabled={mergeSel.size === 0 || !mergeTo.trim() || busy} onClick={() => setConfirming(true)}><Merge className="size-4" /> Merge</Button>
            </div>
            <div className="flex items-end gap-2 border-t pt-3">
              <div className="flex-1 space-y-1.5">
                <label className="text-xs text-muted-foreground">Set genre for every track in library</label>
                <Input value={bulkValue} onChange={(e) => { setOp('bulk'); setBulkValue(e.target.value); }} placeholder="e.g. Electronic" />
              </div>
              <Button disabled={!bulkValue.trim() || busy} onClick={() => setConfirming(true)}><Save className="size-4" /> Set all</Button>
            </div>
          </CardContent>
        </Card>
      </div>

      <Confirm
        open={confirming}
        onCancel={() => setConfirming(false)}
        onConfirm={confirmRun}
        title="Apply genre change?"
        message={confirmMsg()}
        confirmLabel="Apply"
      />
    </div>
  );
}

function MiniStat({ label, value }) {
  return (
    <div className="rounded-xl border bg-card p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 font-mono text-2xl font-semibold">{value}</div>
    </div>
  );
}