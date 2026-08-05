import { useEffect, useState } from 'react';
import { RefreshCw, LibraryBig, Clock, Zap } from 'lucide-react';
import { api, fmtBytes, fmtDur, fmtRelative } from '../api.js';
import { useJob } from '../useJob.js';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardAction } from '@/components/ui/card.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select.jsx';
import { PageHeader, StatCard, Empty } from '../components/PageHeader.jsx';
import { toast } from '../toast.jsx';

const OP_LABELS = {
  analyze: 'Library scan', quick_scan: 'Quick scan', organize: 'Organize', duplicates: 'Duplicate scan',
  exclusivity: 'Exclusivity scan', 'artist-exclusivity': 'Artist exclusivity', cleanup: 'Cleanup',
  covers: 'Album covers', rebuild_covers: 'Rebuild covers', playlists: 'Playlists', report: 'Library report',
  'plex-rating-sync': 'Plex rating sync', 'plex-export': 'Plex export', genres: 'Genre change',
  'library_extract_move': 'Create library & move',
};

export default function Dashboard({ onNavigate }) {
  const [settings, setSettings] = useState(null);
  const [total, setTotal] = useState(null);
  const [ops, setOps] = useState([]);
  const [libId, setLibId] = useState('__all__');
  const { running, run } = useJob();

  useEffect(() => {
    api.settings().then(setSettings).catch(() => {});
    api.operations(20).then((o) => setOps(o.operations || [])).catch(() => {});
  }, []);

  const refreshOps = () => api.operations(20).then((o) => setOps(o.operations || [])).catch(() => {});

  const analyze = async (quick = false) => {
    const ids = libId === '__all__' ? undefined : (libId ? [libId] : undefined);
    const op = quick ? 'quick-scan' : 'analyze';
    const res = await run(op, ids ? { library_ids: ids } : {});
    if (res?.ok) toast.success(quick ? 'Quick scan complete' : `Analysis complete: ${res.total?.tracks ?? 0} tracks`);
    else if (res?.error) toast.error(res.error);
    refreshOps();
  };

  useEffect(() => { if (!total) analyze(false); /* eslint-disable-line */ }, []);
  useEffect(() => { if (total) refreshOps(); }, [running]);

  const libs = settings?.libraries || [];
//__DASH_A__
  return (
    <div>
      <PageHeader title="Dashboard" description="Library overview and quick actions.">
        <div className="flex items-center gap-2">
          {libs.length > 0 && (
            <Select value={libId} onValueChange={setLibId}>
              <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">All libraries</SelectItem>
                {libs.map((l) => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
              </SelectContent>
            </Select>
          )}
          <Button variant="outline" onClick={() => analyze(true)} disabled={running}>
            <Zap className="size-4" /> Quick scan
          </Button>
          <Button onClick={() => analyze(false)} disabled={running}>
            <RefreshCw className={running ? 'size-4 animate-spin' : 'size-4'} /> Scan
          </Button>
        </div>
      </PageHeader>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Tracks" value={total ? total.tracks : '—'} />
        <StatCard label="Artists" value={total ? total.artists : '—'} />
        <StatCard label="Albums" value={total ? total.albums : '—'} />
        <StatCard label="Storage" value={total ? fmtBytes(total.size) : '—'} sub={total ? `${fmtDur(total.duration_seconds)} audio` : ''} />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="border-b">
            <CardTitle>Libraries</CardTitle>
            <CardDescription>Managed music folders</CardDescription>
            <CardAction>
              <Button variant="outline" size="sm" onClick={() => onNavigate('libraries')}>
                <LibraryBig className="size-4" /> Manage
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent>
            {libs.length === 0 ? <Empty text="No libraries configured yet." /> : (
              <ul className="divide-y divide-border">
                {libs.map((l) => (
                  <li key={l.id} className="flex items-center justify-between py-2">
                    <div>
                      <div className="text-sm font-medium">{l.name}</div>
                      <div className="font-mono text-xs text-muted-foreground">{l.path}</div>
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {l.scan ? `${l.scan.tracks} tracks` : 'not scanned'}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b">
            <CardTitle>Recent operations</CardTitle>
            <CardDescription>Latest activity across all libraries</CardDescription>
          </CardHeader>
          <CardContent>
            {ops.length === 0 ? <Empty text="No operations yet." /> : (
              <ul className="divide-y divide-border text-sm">
                {ops.slice().reverse().map((o, i) => (
                  <li key={i} className="flex items-start justify-between gap-3 py-2">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{OP_LABELS[o.operation] || o.operation}</span>
                        {o.library && <span className="text-xs text-muted-foreground">· {o.library}</span>}
                      </div>
                      <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                        <span className="flex items-center gap-1"><Clock className="size-3" /> {fmtRelative(o.ts)}</span>
                        {o.duration != null && <span>· {Number(o.duration).toFixed(1)}s</span>}
                      </div>
                    </div>
                    <span className={o.status === 'error' ? 'shrink-0 text-destructive' : 'shrink-0 text-ok'}>
                      {o.status === 'error' ? 'Failed' : 'Done'}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
