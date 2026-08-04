import { useEffect, useState } from 'react';
import { ScrollText, RefreshCw, Trash2 } from 'lucide-react';
import { api } from '../api.js';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardAction } from '@/components/ui/card.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Badge } from '@/components/ui/badge.jsx';
import { useSSE } from '../useSSE.js';
import { PageHeader, Empty } from '../components/PageHeader.jsx';

const LEVEL_MAP = { info: 'secondary', success: 'success', warning: 'warning', warn: 'warning', error: 'destructive', debug: 'outline' };

export default function Logs() {
  const [logs, setLogs] = useState([]);
  const [filter, setFilter] = useState('all');
  const { events } = useSSE();

  const refresh = (limit = 400) => api.logs(limit).then((l) => setLogs(l.list || l.logs || l || [])).catch(() => {});
  useEffect(() => { refresh(); }, []);

  // Re-append live events of type log as they arrive.
  useEffect(() => {
    const last = events[events.length - 1];
    if (last && last.type === 'log') {
      setLogs((cur) => [...cur.slice(-399), last]);
    }
  }, [events]);

  const shown = logs.filter((l) => filter === 'all' || (l.level || l.type) === filter);
  const levelOf = (l) => l.level || l.type || 'info';
  const msgOf = (l) => l.message || l.msg || JSON.stringify(l);
  const tsOf = (l) => {
    if (l.ts || l.time || l.timestamp) return new Date((l.ts || l.time || l.timestamp) * 1000).toLocaleTimeString();
    return '';
  };

  return (
    <div>
      <PageHeader title="Logs" description="Backend event stream and operation history.">
        <Button variant="outline" size="sm" onClick={() => refresh()}><RefreshCw className="size-3.5" /> Refresh</Button>
      </PageHeader>

      <Card>
        <CardHeader className="border-b">
          <CardTitle className="flex items-center gap-2"><ScrollText className="size-4 text-primary" /> Event log</CardTitle>
          <CardDescription>{logs.length} entries</CardDescription>
          <CardAction>
            <div className="flex gap-1">
              {['all', 'info', 'success', 'warning', 'error'].map((lvl) => (
                <button
                  key={lvl}
                  onClick={() => setFilter(lvl)}
                  className={`rounded-md px-2 py-1 text-xs font-medium capitalize ${filter === lvl ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent'}`}
                >{lvl === 'all' ? 'All' : lvl}</button>
              ))}
            </div>
          </CardAction>
        </CardHeader>
        <CardContent className="pt-0">
          {shown.length === 0 ? <Empty text="No log entries yet." /> : (
            <div className="divide-y divide-border font-mono text-xs">
              {shown.slice().reverse().map((l, i) => (
                <div key={i} className="flex items-start gap-3 py-1.5">
                  <span className="w-16 shrink-0 text-muted-foreground">{tsOf(l)}</span>
                  <Badge variant={LEVEL_MAP[levelOf(l)] || 'outline'} className="w-16 justify-center shrink-0 capitalize">{levelOf(l)}</Badge>
                  <span className="whitespace-pre-wrap break-words">{msgOf(l)}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
