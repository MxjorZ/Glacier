import { useEffect, useState } from 'react';
import { Radio, RefreshCw, Search, Star, Columns2, Server, CheckCircle2, XCircle } from 'lucide-react';
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
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [dups, setDups] = useState(null);
  const [busy, setBusy] = useState('');
  const [syncStatus, setSyncStatus] = useState(null);
  const [syncing, setSyncing] = useState(false);

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

  useEffect(() => { loadStatus(); loadStats(); loadSyncStatus(); /* eslint-disable-line */ }, []);

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
    </div>
  );
}

