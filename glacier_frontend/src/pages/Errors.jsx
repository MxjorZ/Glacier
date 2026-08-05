import { useEffect, useState } from 'react';
import { AlertTriangle, Copy, Eraser, Download, ChevronDown, ChevronRight, CircleAlert, Info, ShieldAlert } from 'lucide-react';
import { api, fmtDateTime, fmtRelative } from '../api.js';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardAction } from '@/components/ui/card.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Badge } from '@/components/ui/badge.jsx';
import { PageHeader, Empty } from '../components/PageHeader.jsx';
import { toast } from '../toast.jsx';
import { cn } from '@/lib/utils.js';

const SEVERITY = {
  error: { label: 'Error', cls: 'bg-destructive/15 text-destructive', Icon: CircleAlert },
  warning: { label: 'Warning', cls: 'bg-warn/15 text-warn', Icon: AlertTriangle },
  info: { label: 'Info', cls: 'bg-info/15 text-info', Icon: Info },
};

export default function Errors({ liveErrors = [] }) {
  const [errors, setErrors] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [expanded, setExpanded] = useState(new Set());
  const [filter, setFilter] = useState('all');

  const load = async () => {
    try {
      const res = await api.errors();
      setErrors(res?.errors || []);
    } catch { /* keep what we have */ }
    finally { setLoaded(true); }
  };
  useEffect(() => { load(); }, []);

  // Persistent backend errors; live (in-session) errors are shown first.
  const all = [...(liveErrors || []), ...errors];

  const toggle = (id) => {
    const n = new Set(expanded);
    if (n.has(id)) n.delete(id); else n.add(id);
    setExpanded(n);
  };
  const clear = async () => {
    try {
      await api.clearErrors();
      setErrors([]);
      toast.success('Errors cleared');
    } catch (e) { toast.error(e.message); }
  };

  const copyEntry = async (e) => {
    const text = `[${fmtDateTime(e.ts)}] ${e.title}\n${e.message || ''}\nModule: ${e.module || '—'}\n${e.traceback || ''}`;
    try { await navigator.clipboard.writeText(text); toast.success('Copied'); }
    catch { toast.error('Clipboard unavailable'); }
  };

  const download = () => {
    const text = all.map((e) => `[${fmtDateTime(e.ts)}] ${e.title}\n${e.message || ''}\n${e.traceback || ''}\n---`).join('\n\n');
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'glacier-errors.txt'; a.click();
    URL.revokeObjectURL(url);
    toast.success('Errors exported');
  };

  const shown = all.filter((e) => filter === 'all' || (e.severity || 'error') === filter);
  return (
    <div>
      <PageHeader title="Error Center" description="Every error Glacier has encountered, kept until you clear it.">
        <Button variant="outline" size="sm" onClick={download} disabled={!all.length}><Download className="size-3.5" /> Export</Button>
        <Button variant="outline" size="sm" onClick={clear} disabled={!all.length} className="text-destructive"><Eraser className="size-3.5" /> Clear</Button>
      </PageHeader>

      <Card>
        <CardHeader className="border-b">
          <CardTitle className="flex items-center gap-2"><ShieldAlert className="size-4 text-primary" /> Errors <Badge variant="secondary">{all.length}</Badge></CardTitle>
          <CardDescription>Errors stay here until you manually clear them — no need to dig through server logs.</CardDescription>
          <CardAction>
            <div className="flex gap-1">
              {['all', 'error', 'warning', 'info'].map((s) => (
                <button key={s} onClick={() => setFilter(s)}
                  className={cn('rounded-md px-2 py-1 text-xs font-medium capitalize',
                    filter === s ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent')}>
                  {s}
                </button>
              ))}
            </div>
          </CardAction>
        </CardHeader>
        <CardContent className="pt-0">
          {!loaded ? <Empty text="Loading…" /> : shown.length === 0 ? (
            <Empty text={all.length ? 'No errors match this filter.' : 'No errors recorded yet. 🎉'} />
          ) : (
            <div className="space-y-2">
              {shown.slice().reverse().map((e) => {
                const sev = SEVERITY[e.severity] || SEVERITY.error;
                const open = expanded.has(e.id);
                return (
                  <div key={e.id} className="rounded-lg border bg-card/50">
                    <div className="flex items-start gap-2 px-3 py-2">
                      <sev.Icon className={cn('mt-0.5 size-4 shrink-0', sev.cls.split(' ')[1])} />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-semibold">{e.title}</span>
                          <Badge variant="outline" className={cn('font-mono text-[10px]', sev.cls)}>{sev.label}</Badge>
                          {e.module && <span className="font-mono text-[10px] text-muted-foreground">· {e.module}</span>}
                        </div>
                        {e.message && <p className="mt-0.5 whitespace-pre-wrap break-words text-xs text-muted-foreground">{e.message}</p>}
                        <span className="mt-1 block text-[10px] font-mono text-muted-foreground">{fmtRelative(e.ts)} · {fmtDateTime(e.ts)}</span>
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        <Button size="icon" variant="ghost" className="size-7" onClick={() => copyEntry(e)} title="Copy error"><Copy className="size-3.5" /></Button>
                        {e.traceback && (
                          <Button size="icon" variant="ghost" className="size-7" onClick={() => toggle(e.id)} title="Toggle stack trace">
                            {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
                          </Button>
                        )}
                      </div>
                    </div>
                    {open && e.traceback && (
                      <pre className="mx-3 mb-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-lg border bg-muted/40 p-2 font-mono text-[10px]">{e.traceback}</pre>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}