import { useEffect, useRef, useState } from 'react';
import { ScrollText, RefreshCw, Trash2, Search, Download, Copy } from 'lucide-react';
import { api, fmtDateTime } from '../api.js';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardAction } from '@/components/ui/card.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Badge } from '@/components/ui/badge.jsx';
import { Input } from '@/components/ui/input.jsx';
import { useSSE } from '../useSSE.js';
import { PageHeader, Empty } from '../components/PageHeader.jsx';
import { toast } from '../toast.jsx';
import { cn } from '@/lib/utils.js';

const LEVEL_MAP = { info: 'secondary', success: 'success', warning: 'warning', warn: 'warning', error: 'destructive', debug: 'outline', verbose: 'outline' };

export default function Logs() {
  const [logs, setLogs] = useState([]);
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [autoScroll, setAutoScroll] = useState(true);
  const { events } = useSSE();

  const refresh = (limit = 400) => api.logs(limit).then((l) => setLogs(l.list || l.logs || l || [])).catch(() => {});
  useEffect(() => { refresh(); }, []);

  // Re-append live events of type log as they arrive.
  useEffect(() => {
    const last = events[events.length - 1];
    if (last && last.type === 'log') {
      setLogs((cur) => [...cur.slice(-399), { id: Math.random().toString(36).slice(2), ...last }]);
    }
  }, [events]);

  const shown = logs
    .filter((l) => filter === 'all' || (l.level || l.type) === filter || (filter === 'errors' && ((l.level || l.type) === 'error')))
    .filter((l) => {
      if (!query.trim()) return true;
      const q = query.toLowerCase();
      return [l.message, l.msg, l.label, l.level, l.type, JSON.stringify(l.result || '')].join(' ').toLowerCase().includes(q);
    });
  const levelOf = (l) => l.level || l.type || 'info';
  const msgOf = (l) => l.message || l.msg || l.label || JSON.stringify(l);
  const tsOf = (l) => fmtDateTime(l.ts || l.time || l.timestamp);

  const download = () => {
    const text = shown.map((l) => `[${tsOf(l)}] ${levelOf(l)}: ${msgOf(l)}`).join('\n');
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'glacier-logs.txt'; a.click();
    URL.revokeObjectURL(url);
    toast.success('Logs downloaded');
  };

  const copyAll = async () => {
    const text = shown.map((l) => `[${tsOf(l)}] ${levelOf(l)}: ${msgOf(l)}`).join('\n');
    try { await navigator.clipboard.writeText(text); toast.success('Copied to clipboard'); }
    catch { toast.error('Clipboard unavailable'); }
  };

  return (
    <div>
      <PageHeader title="Logs" description="Backend event stream and operation history.">
        <Button variant="outline" size="sm" onClick={() => refresh()}><RefreshCw className="size-3.5" /> Refresh</Button>
      </PageHeader>

      <Card>
        <CardHeader className="border-b">
          <CardTitle className="flex items-center gap-2"><ScrollText className="size-4 text-primary" /> Event log</CardTitle>
          <CardDescription>{shown.length} entries{query.trim() ? ` matching “${query}”` : ''}</CardDescription>
          <CardAction>
            <div className="flex items-center gap-1">
              {['all', 'info', 'success', 'warning', 'errors', 'verbose'].map((lvl) => (
                <button
                  key={lvl}
                  onClick={() => setFilter(lvl)}
                  className={`rounded-md px-2 py-1 text-xs font-medium capitalize ${filter === lvl ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent'}`}
                >{lvl === 'all' ? 'All' : lvl === 'verbose' ? 'Files' : lvl === 'errors' ? 'Errors' : lvl}</button>
              ))}
            </div>
          </CardAction>
        </CardHeader>
        <CardContent className="space-y-2 pt-0">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-52 flex-1">
              <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search logs…" className="pl-7 text-xs" />
            </div>
            <Button variant="outline" size="sm" onClick={copyAll}><Copy className="size-3.5" /> Copy</Button>
            <Button variant="outline" size="sm" onClick={download}><Download className="size-3.5" /> Download</Button>
          </div>

          {shown.length === 0 ? <Empty text="No log entries yet." /> : (
            <div className="divide-y divide-border overflow-auto rounded-lg border font-mono text-xs">
              {shown.slice().reverse().map((l, i) => (
                <div key={l.id || i} className="flex items-start gap-3 py-1.5 px-2">
                  <span className="w-44 shrink-0 text-muted-foreground">{tsOf(l)}</span>
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
