import { useEffect, useState } from 'react';
import { Radio, RefreshCw, Search, Star, Columns2, Server, CheckCircle2, XCircle, Disc3 } from 'lucide-react';
import { api, fmtDate } from '../api.js';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardAction } from '@/components/ui/card.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Badge } from '@/components/ui/badge.jsx';
import { Input } from '@/components/ui/input.jsx';
import { PageHeader, Empty } from '../components/PageHeader.jsx';
import { toast } from '../toast.jsx';

export default function Plex() {
  const [status, setStatus] = useState(null);
  const [stats, setStats] = useState(null);
  const [libStats, setLibStats] = useState(null);
  const [libStatsBusy, setLibStatsBusy] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [dups, setDups] = useState(null);
  const [busy, setBusy] = useState('');
  const [syncStatus, setSyncStatus] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [sections, setSections] = useState(null);
  const [secBusy, setSecBusy] = useState(false);
  const [exporting, setExporting] = useState(false);

  const loadStatus = async () => {
    setBusy('status');
    try { setStatus(await api.plex.status()); } catch (e) { toast.error(e.message); }
    finally { setBusy(''); }
  };

  const loadStats = async () => {
    setBusy('stats');
    try { setStats(await api.plex.stats()); } catch (e) { toast.error(e.message); }
    finally { setBusy(''); }
  };

  const doSearch = async () => {
    if (!query.trim()) return;
    setBusy('search');
    try { setResults(await api.plex.search(query)); } catch (e) { toast.error(e.message); }
    finally { setBusy(''); }
  };

  const loadDups = async () => {
    setBusy('dups');
    try { setDups(await api.plex.duplicates()); toast.success('Duplicate scan complete'); }
    catch (e) { toast.error(e.message); }
    finally { setBusy(''); }
  };

  const loadSyncStatus = async () => {
    try { setSyncStatus(await api.plex.syncStatus()); } catch { /* ignore */ }
  };

  // Per-music-library statistics straight from Plex's database (Stage 4 #13).
  const loadLibStats = async () => {
    setLibStatsBusy(true);
    try { setLibStats(await api.plex.libraryStats()); }
    catch (e) { toast.error(e.message); }
    finally { setLibStatsBusy(false); }
  };

  const runSync = async () => {
    setSyncing(true);
    try {
      const start = await api.plex.syncRatings();
      if (!start?.ok) { toast.error(start?.error || 'Sync failed to start'); return; }
      toast.success('Rating sync started');
      const deadline = Date.now() + 120000;
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 700));
        const hist = await api.get('/api/jobs/history');
        const j = (hist.jobs || []).find(
          (x) => x.operation === 'plex-rating-sync' && x.status !== 'running');
        if (j) {
          if (j.status === 'error') toast.error('Rating sync failed: ' + (j.result?.error || 'error'));
          else toast.success(`Sync done: ${j.result?.written ?? 0} written, ${j.result?.matched ?? 0} matched`);
          loadSyncStatus();
          return;
        }
      }
      toast.info('Sync still running — check Logs.');
    } catch (e) { toast.error(e.message); }
    finally { setSyncing(false); }
  };

  useEffect(() => { loadStatus(); loadStats(); loadLibStats(); loadSyncStatus(); /* eslint-disable-line */ }, []);

  // "Load Plex folders via Plex": enumerate sections + their on-disk locations
  // using the saved server URL + token, then add them as Glacier libraries.
  const loadSections = async () => {
    setSecBusy(true);
    try { setSections(await api.plex.sections()); }
    catch (e) { toast.error(e.message); }
    finally { setSecBusy(false); }
  };

  const addPlexLibrary = async (sec) => {
    const p = (sec.locations || [])[0];
    if (!p) { toast.error(`"${sec.name}" has no on-disk folder location`); return; }
    try { await api.addLibrary(sec.name, p); toast.success(`Added "${sec.name}" (${p})`); }
    catch (e) { toast.error(e.message); }
  };

  const doExport = async () => {
    setExporting(true);
    try {
      const res = await api.plex.exportContent();
      if (!res?.ok) { toast.error(res?.error || 'Export failed'); return; }
      const blob = new Blob([JSON.stringify(res, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      const slug = (res.section || 'Music').replace(/[^a-z0-9]+/gi, '-').toLowerCase();
      a.href = url;
      a.download = `plex-export-${slug}-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(`Exported ${res.count} track(s) from ${res.section}`);
    } catch (e) { toast.error(e.message); }
    finally { setExporting(false); }
  };

  const connected = status?.ok || status?.connected || status?.reachable;

  return (
    <div>
      <PageHeader title="Plex" description="Read-only integration with your Plex Media Server, plus star-rating sync to local tags.">
        <Button variant="outline" onClick={loadStatus} disabled={busy === 'status'}>
          <RefreshCw className={busy === 'status' ? 'size-4 animate-spin' : 'size-4'} /> Refresh status
        </Button>
        <Button disabled={syncing} onClick={runSync} title="Pull Plex star ratings into local FLAC/MP3 tags">
          <RefreshCw className={syncing ? 'size-4 animate-spin' : 'size-4'} /> Sync ratings now
        </Button>
      </PageHeader>

      {syncStatus && (
        <Card className="mb-4">
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2"><Star className="size-4 text-primary" /> Rating sync</CardTitle>
            <CardAction>
              <Badge variant={syncStatus.enabled ? 'success' : 'secondary'}>
                {syncStatus.enabled ? 'Enabled (every ' + (syncStatus.interval_sec / 60) + ' min)' : 'Disabled'}
              </Badge>
            </CardAction>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">5 stars → tag rating</span>
              <span className="font-mono">100</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Overwrite higher local rating</span>
              <span>{syncStatus.overwrite ? 'Yes' : 'No (safer)'}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Last run</span>
              <span className="font-mono text-xs">{syncStatus.last_run ? fmtDate(syncStatus.last_run) : 'never'}</span>
            </div>
            {syncStatus.last_result && (
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Last result</span>
                <span>{syncStatus.last_result.written} written · {syncStatus.last_result.matched} matched · {syncStatus.last_result.missed} unmatched</span>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2"><Server className="size-4 text-primary" /> Server status</CardTitle>
            <CardAction>{status && (connected ? <Badge variant="success">Online</Badge> : <Badge variant="destructive">Offline</Badge>)}</CardAction>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {!status ? <Empty text="Querying server…" /> : (
              <>
                <div className="flex items-center justify-between"><span className="text-muted-foreground">Reachable</span>
                  <span>{connected ? <CheckCircle2 className="size-4 text-ok" /> : <XCircle className="size-4 text-destructive" />}</span>
                </div>
                <div className="flex items-center justify-between"><span className="text-muted-foreground">Version</span><span className="font-mono text-xs">{status.version || status.friendlyName || '—'}</span></div>
                <div className="flex items-center justify-between"><span className="text-muted-foreground">Library sections</span><span className="font-mono text-xs">{status.sections ?? '—'}</span></div>
                <div className="flex items-center justify-between"><span className="text-muted-foreground">Message</span><span className="text-xs">{status.message || status.error || '—'}</span></div>
              </>
            )}
          </CardContent>
        </Card>


        <Card>
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2"><Radio className="size-4 text-primary" /> Library stats</CardTitle>
            <CardAction>
              <Button variant="outline" size="sm" onClick={loadStats} disabled={busy === 'stats'}>
                <RefreshCw className="size-3.5" /> Refresh
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {!stats ? <Empty text="Fetching stats…" /> : (
              <>
                <div className="flex items-center justify-between"><span className="text-muted-foreground">Tracks</span><span className="font-mono font-medium">{stats.tracks ?? '—'}</span></div>
                <div className="flex items-center justify-between"><span className="text-muted-foreground">Artists</span><span className="font-mono font-medium">{stats.artists ?? '—'}</span></div>
                <div className="flex items-center justify-between"><span className="text-muted-foreground">Albums</span><span className="font-mono font-medium">{stats.albums ?? '—'}</span></div>
                <div className="flex items-center justify-between"><span className="text-muted-foreground">Section</span><span className="font-mono text-xs">{stats.section ?? '—'}</span></div>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2"><Search className="size-4 text-primary" /> Search</CardTitle>
            <CardDescription>Find media on the server</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex gap-2">
              <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search Plex…" onKeyDown={(e) => e.key === 'Enter' && doSearch()} />
              <Button variant="outline" onClick={doSearch} disabled={busy === 'search'}><Search className="size-4" /> Search</Button>
            </div>
            {results && (results.items || results.results)?.length === 0 && <Empty text="No results." />}
            {results && (results.items || results.results)?.length > 0 && (
              <div className="max-h-72 space-y-1 overflow-auto font-mono text-xs">
                {(results.items || results.results).map((r, i) => (
                  <div key={i} className="truncate rounded border-b border-border/40 py-1">
                    {r.title || r.name}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2"><Columns2 className="size-4 text-primary" /> Duplicate detection</CardTitle>
            <CardDescription>Find likely duplicate albums on the server</CardDescription>
            <CardAction>
              <Button variant="outline" size="sm" onClick={loadDups} disabled={busy === 'dups'}>
                <RefreshCw className="size-3.5" /> Scan
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent>
            {!dups ? <Empty text="Scan the Plex library for duplicates." /> : (dups.items || dups.duplicates || []).length === 0 ? (
              <Empty text="No duplicates found." />
            ) : (
              <div className="max-h-72 space-y-1 overflow-auto text-sm">
                {(dups.items || dups.duplicates).map((d, i) => (
                  <div key={i} className="flex items-center justify-between border-b border-border/40 py-1">
                    <span className="truncate">{d.title || 'Item'}</span>
                    <Star className="size-3.5 text-muted-foreground" />
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Load Plex folders into Glacier + export */}
      {/* Statistics for every music library, straight from Plex (Stage 4 #13) */}
      <Card className="mb-4">
        <CardHeader className="border-b">
          <CardTitle className="flex items-center gap-2"><Disc3 className="size-4 text-primary" /> Plex music libraries</CardTitle>
          <CardDescription>Per-library counts reported by your Plex server itself.</CardDescription>
          <CardAction>
            <Button variant="outline" size="sm" onClick={loadLibStats} disabled={libStatsBusy}>
              <RefreshCw className={libStatsBusy ? 'size-3.5 animate-spin' : 'size-3.5'} /> Refresh
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent className="pt-4">
          {!libStats ? <Empty text="Fetching Plex library statistics…" /> :
           libStats.error ? <p className="text-sm text-destructive">{libStats.error}</p> :
           (libStats.libraries || []).length === 0 ? <Empty text="No music libraries found on this Plex server." /> : (
            <div className="divide-y divide-border">
              {(libStats.libraries || []).map((l) => (
                <div key={l.name} className="grid grid-cols-2 items-center gap-3 py-2 sm:grid-cols-4">
                  <div className="col-span-2 sm:col-span-1">
                    <div className="text-sm font-semibold">{l.name}</div>
                    {l.approximate && <div className="text-[10px] text-muted-foreground">(approximate for very large libraries)</div>}
                  </div>
                  <div className="text-right"><div className="text-xs text-muted-foreground">Tracks</div><div className="font-mono text-lg font-semibold">{l.tracks?.toLocaleString?.() ?? l.tracks ?? '—'}</div></div>
                  <div className="text-right"><div className="text-xs text-muted-foreground">Albums</div><div className="font-mono text-lg font-semibold">{l.albums?.toLocaleString?.() ?? l.albums ?? '—'}</div></div>
                  <div className="text-right"><div className="text-xs text-muted-foreground">Artists</div><div className="font-mono text-lg font-semibold">{l.artists?.toLocaleString?.() ?? l.artists ?? '—'}</div></div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2"><Server className="size-4 text-primary" /> Load folders from Plex</CardTitle>
            <CardDescription>Token + server URL is enough — list your Plex sections and add their on-disk folders as Glacier libraries.</CardDescription>
            <CardAction>
              <Button variant="outline" size="sm" onClick={loadSections} disabled={secBusy}>
                <RefreshCw className={secBusy ? 'size-3.5 animate-spin' : 'size-3.5'} /> Load sections
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent className="space-y-2">
            {!sections ? (
              <Empty text="Click “Load sections” to pull your Plex library folders." />
            ) : sections.error ? (
              <p className="text-sm text-destructive">{sections.error}</p>
            ) : (sections.sections || []).length === 0 ? (
              <Empty text="No sections returned." />
            ) : (
              <div className="max-h-80 space-y-1.5 overflow-auto">
                {(sections.sections || []).map((sec) => (
                  <div key={sec.key || sec.name} className="flex items-center justify-between gap-2 rounded-lg border bg-muted/20 px-2.5 py-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 text-sm">
                        <span className="truncate font-medium">{sec.name}</span>
                        <Badge variant="secondary" className="capitalize">{sec.type}</Badge>
                        {sec.count != null && <Badge variant="outline">{sec.count} items</Badge>}
                      </div>
                      <p className="mt-0.5 truncate font-mono text-[10px] text-muted-foreground">
                        {(sec.locations || []).join(', ') || 'no folder location'}
                      </p>
                    </div>
                    <Button size="sm" variant="outline" disabled={!(sec.locations || []).length} onClick={() => addPlexLibrary(sec)}>
                      Add to Glacier
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2"><Radio className="size-4 text-primary" /> Export library data</CardTitle>
            <CardDescription>Download your Plex music as JSON — artist / album / title / year / duration / rating / genre. Progress shows in the footer.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p className="text-xs text-muted-foreground">
              Downloads the currently configured music section as a JSON file you can
              open in a spreadsheet or analyse yourself.
            </p>
            <div className="flex items-center justify-between">
              <span className="text-sm">Full music section metadata</span>
              <Button onClick={doExport} disabled={exporting}>
                {exporting ? <RefreshCw className="size-4 animate-spin" /> : <Radio className="size-4" />}
                {exporting ? 'Exporting…' : 'Export JSON'}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

