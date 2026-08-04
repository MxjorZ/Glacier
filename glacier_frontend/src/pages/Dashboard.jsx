import { useEffect, useState } from 'react';
import { RefreshCw, LibraryBig, HardDrive, User, Disc3, Clock } from 'lucide-react';
import { api, fmtBytes, fmtDur } from '../api.js';
import { useJob } from '../useJob.js';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardAction } from '@/components/ui/card.jsx';
import { Button } from '@/components/ui/button.jsx';
import { PageHeader, StatCard, Empty } from '../components/PageHeader.jsx';
import { toast } from '../toast.jsx';

export default function Dashboard({ onNavigate }) {
  const [settings, setSettings] = useState(null);
  const [total, setTotal] = useState(null);
  const [history, setHistory] = useState([]);
  const { running, run } = useJob();

  useEffect(() => {
    api.settings().then(setSettings).catch(() => {});
    api.get('/api/jobs/history').then((h) => setHistory(h.jobs || [])).catch(() => {});
  }, []);

  const analyze = async () => {
    const res = await run('analyze', {});
    if (res?.ok) { setTotal(res.total); toast.success(`Analysis complete: ${res.total.tracks} tracks`); }
    else if (res?.error) toast.error(res.error);
  };

  useEffect(() => { if (!total) analyze(); /* eslint-disable-line */ }, []);

  const libs = settings?.libraries || [];
  return (
    <div>
      <PageHeader title="Dashboard" description="Library overview and quick actions.">
        <Button onClick={analyze} disabled={running}>
          <RefreshCw className={running ? 'size-4 animate-spin' : 'size-4'} /> Scan all
        </Button>
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
            <CardDescription>Job history</CardDescription>
          </CardHeader>
          <CardContent>
            {history.length === 0 ? <Empty text="No operations yet." /> : (
              <ul className="divide-y divide-border font-mono text-xs">
                {history.slice().reverse().slice(0, 8).map((h) => (
                  <li key={h.id} className="flex items-center justify-between py-2">
                    <span>{h.operation}</span>
                    <span className={h.status === 'error' ? 'text-destructive' : 'text-ok'}>{h.status}</span>
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
