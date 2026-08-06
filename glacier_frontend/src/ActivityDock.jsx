import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronUp, ChevronDown, Loader2, AlertTriangle, Search, Copy, Download, GripHorizontal, Filter, Square } from 'lucide-react';
import { api } from './api.js';
import { toast } from './toast.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Progress } from '@/components/ui/progress.jsx';
import { Badge } from '@/components/ui/badge.jsx';
import { Input } from '@/components/ui/input.jsx';
import { cn } from '@/lib/utils.js';

function fmtDur(sec) {
  if (!Number.isFinite(sec) || sec < 0) return '–';
  sec = Math.round(sec);
  const s = sec % 60, m = Math.floor(sec / 60) % 60, h = Math.floor(sec / 3600);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function fmtSpeed(rate) {
  if (!Number.isFinite(rate) || rate <= 0) return null;
  if (rate >= 1) return `${Math.round(rate).toLocaleString()}/s`;
  return `${(Math.round(rate * 10) / 10).toFixed(1)}/s`;
}

// Category -> label + colour for the floating log console (Stage 4 #14).
const CATEGORIES = [
  { key: 'all', label: 'All', cls: 'text-foreground' },
  { key: 'info', label: 'Info', cls: 'text-muted-foreground' },
  { key: 'success', label: 'Success', cls: 'text-ok' },
  { key: 'warning', label: 'Warning', cls: 'text-warn' },
  { key: 'error', label: 'Error', cls: 'text-destructive' },
  { key: 'connected', label: 'Connected', cls: 'text-ok' },
  { key: 'disconnected', label: 'Disconnected', cls: 'text-destructive' },
  { key: 'progress', label: 'Progress', cls: 'text-warn' },
];

const catOf = (l) => {
  const t = l.type || l.level;
  if (t === 'connected') return 'connected';
  if (t === 'disconnected') return 'disconnected';
  if (t === 'progress') return 'progress';
  if (t === 'success') return 'success';
  if (t === 'warning' || t === 'warn') return 'warning';
  if (t === 'error') return 'error';
  return 'info';
};

// Floating footer bar shown on every page: per-job progress with ETA + speed, and
// a live, searchable, colour-coded log console.
export default function ActivityDock({ jobs, progress, logs, errors, onDismissError, onClearErrors }) {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [autoScroll, setAutoScroll] = useState(true);
  const [opacity, setOpacity] = useState(96);
  const [height, setHeight] = useState(340);
  const [, tick] = useState(0);
  const logRef = useRef(null);

  // Right-click context menu for a running job (Stage 4 fix): lets the user
  // terminate the job.
  const [jobMenu, setJobMenu] = useState(null);
  useEffect(() => {
    const close = () => setJobMenu(null);
    window.addEventListener('click', close);
    window.addEventListener('scroll', close, true);
    window.addEventListener('resize', close);
    return () => {
      window.removeEventListener('click', close);
      window.removeEventListener('scroll', close, true);
      window.removeEventListener('resize', close);
    };
  }, []);

  const terminateJob = async () => {
    if (!jobMenu) return;
    try {
      const res = await api.terminateJob(jobMenu.id);
      if (res?.cancelled) toast.success('Terminate requested — stopping job…');
      else toast.error(res?.error || 'Job is no longer running');
    } catch (e) {
      toast.error(e.message);
    }
    setJobMenu(null);
  };

  // Smooth per-job processing speed from progress event timestamps.
  const [rates, setRates] = useState({});
  const samplesRef = useRef({});
  useEffect(() => {
    const updates = {};
    Object.values(progress).forEach((p) => {
      const prev = samplesRef.current[p.job_id];
      if (prev && p.ts > prev.ts) {
        const dt = p.ts - prev.ts;
        const dc = p.current - prev.current;
        if (dt > 0 && dc >= 0) {
          const inst = dc / dt;
          const prevRate = rates[p.job_id];
          updates[p.job_id] = prevRate ? 0.6 * prevRate + 0.4 * inst : inst;
        }
      }
      samplesRef.current[p.job_id] = { ts: p.ts, current: p.current };
    });
    if (Object.keys(updates).length) setRates((r) => ({ ...r, ...updates }));
  }, [progress]); // eslint-disable-line react-hooks/exhaustive-deps

  // Re-render every second so elapsed/ETA stay live.
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const jobList = useMemo(() => {
    const now = Date.now() / 1000;
    return Object.values(jobs).map((j) => {
      const p = progress[j.id];
      const elapsed = now - (j.start || now);
      let eta = null;
      let pct = null;
      if (p && p.total > 0) {
        pct = Math.round((p.current / p.total) * 100);
        if (p.current > 0 && p.current < p.total) eta = (elapsed / p.current) * p.total - elapsed;
        else if (p.current >= p.total) eta = 0;
      }
      return { ...j, p, elapsed, eta, pct, speed: p ? (rates[j.id] || 0) : 0 };
    });
  }, [jobs, progress, tick, rates]);

  const runningCount = jobList.length;
  const errorCount = errors.length;

  const visibleLogs = useMemo(() => {
    let list = logs;
    if (filter !== 'all') list = list.filter((l) => catOf(l) === filter);
    if (query.trim()) {
      const q = query.toLowerCase();
      list = list.filter((l) => `${l.message || ''} ${l.label || ''}`.toLowerCase().includes(q));
    }
    return list.slice(-400);
  }, [logs, filter, query]);

  useEffect(() => {
    if (autoScroll && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [visibleLogs.length, autoScroll]);

  const copyLogs = async () => {
    const text = visibleLogs.map((l) => `${new Date((l.ts || 0) * 1000).toLocaleString()} [${catOf(l)}] ${l.message || l.label || ''}`).join('\n');
    try { await navigator.clipboard.writeText(text); } catch { /* ignore */ }
  };

  const downloadLogs = () => {
    const text = visibleLogs.map((l) => `${new Date((l.ts || 0) * 1000).toLocaleString()} [${catOf(l)}] ${l.message || l.label || ''}`).join('\n');
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'glacier-console.txt'; a.click();
    URL.revokeObjectURL(url);
  };

  const aggCurrent = jobList.reduce((s, j) => s + (j.p?.current || 0), 0);
  const aggTotal = jobList.reduce((s, j) => s + (j.p?.total || 0), 0);

  // Resize by dragging the top handle of the expanded panel.
  const onDrag = (e) => {
    e.preventDefault();
    const startY = e.clientY;
    const startH = height;
    const move = (ev) => setHeight(Math.max(160, Math.min(600, startH + (startY - ev.clientY))));
    const up = () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
    };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
  };

  return (
    <div className="fixed bottom-0 left-14 right-0 z-50 flex flex-col border-t bg-background shadow-[0_-6px_24px_rgba(0,0,0,0.16)]" style={{ opacity: opacity / 100 }}>
      {open && (
        <div role="button" tabIndex={-1} onMouseDown={onDrag}
          className="flex h-2 cursor-row-resize items-center justify-center text-muted-foreground/60 hover:text-primary">
          <GripHorizontal className="size-3" />
        </div>
      )}

      {/* Collapsed summary bar */}
      <button onClick={() => setOpen((o) => !o)}
        className="flex h-9 w-full shrink-0 items-center gap-3 px-3 text-xs text-muted-foreground hover:bg-accent/40">
        {runningCount > 0
          ? <><Loader2 className="size-3.5 animate-spin text-warn" /><span className="font-medium text-warn">{runningCount} job{runningCount === 1 ? '' : 's'} running</span></>
          : <><span className="flex h-2 w-2 rounded-full bg-ok" /><span>Idle</span></>}
        {runningCount > 0 && aggTotal > 0 && <span className="font-mono">{aggCurrent}/{aggTotal}</span>}
        {runningCount > 0 && (
          <span className="min-w-24 flex-1"><Progress value={aggCurrent} max={aggTotal || 1} className="h-1.5" /></span>
        )}
        {errorCount > 0 && (
          <span onClick={(e) => { e.stopPropagation(); setOpen(true); setFilter('error'); }}
            className="ml-auto flex cursor-pointer items-center gap-1 text-warn hover:underline">
            <AlertTriangle className="size-3.5" /> {errorCount} error{errorCount === 1 ? '' : 's'}
          </span>
        )}
        {runningCount === 0 && errorCount === 0 && <span className="ml-auto">No activity</span>}
        {open ? <ChevronDown className="size-4" /> : <ChevronUp className="size-4" />}
      </button>
      {/* Expanded panel */}
      {open && (
        <div className="flex min-h-0 flex-col border-t px-3 py-3" style={{ height }}>
          <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
            <div className="relative min-w-44 flex-1">
              <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search logs…" className="pl-7 text-xs" />
            </div>
            <div className="flex flex-wrap items-center gap-1">
              {CATEGORIES.map((c) => (
                <button key={c.key} onClick={() => setFilter(c.key)}
                  className={cn('rounded-full px-2 py-0.5 text-[11px] capitalize',
                    filter === c.key ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground hover:bg-accent')}>
                  {c.label}
                </button>
              ))}
            </div>
            <div className="ml-auto flex items-center gap-1">
              <Button size="sm" variant="ghost" className="h-7 px-2" onClick={copyLogs} title="Copy logs"><Copy className="size-3.5" /></Button>
              <Button size="sm" variant="ghost" className="h-7 px-2" onClick={downloadLogs} title="Download logs"><Download className="size-3.5" /></Button>
              <div className="flex items-center gap-1">
                <span className="text-[10px] text-muted-foreground">Auto</span>
                <button onClick={() => setAutoScroll((v) => !v)} title="Toggle auto-scroll"
                  className={cn('relative h-4 w-7 rounded-full transition-colors', autoScroll ? 'bg-primary' : 'bg-muted')}>
                  <span className={cn('absolute top-0.5 size-3 rounded-full bg-white transition-all', autoScroll ? 'left-3.5' : 'left-0.5')} />
                </button>
              </div>
              <input type="range" min={40} max={100} value={opacity}
                onChange={(e) => setOpacity(Number(e.target.value))}
                className="ml-1 w-16" title="Console opacity" />
            </div>
          </div>

          <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
            <div className="min-h-0 space-y-2 overflow-auto">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <Loader2 className={cn('size-3.5', runningCount ? 'animate-spin text-warn' : '')} /> Activity
                <Badge variant="secondary" className="ml-auto">{runningCount}</Badge>
              </div>
              {jobList.length === 0 && <p className="text-xs text-muted-foreground">No jobs running.</p>}
              {jobList.map((j) => (
                <div key={j.id} onContextMenu={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setJobMenu({ id: j.id, x: e.clientX, y: e.clientY });
                }} className="cursor-context-menu rounded-lg border bg-card/40 p-2 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="flex-1 truncate font-medium">{j.operation}</span>
                    <span className="flex items-center gap-1.5 font-mono text-muted-foreground">
                      {j.eta != null
                        ? <span className="text-primary">~{fmtDur(j.eta)} left</span>
                        : j.p ? <span className="text-muted-foreground">waiting…</span> : <span className="text-muted-foreground">–</span>}
                      <span>{fmtDur(j.elapsed)}</span>
                    </span>
                  </div>
                  {j.p ? (
                    <>
                      <Progress value={j.p.current} max={j.p.total || 1} className="mt-1.5 h-1.5" />
                      <div className="mt-1 flex items-center justify-between gap-2 font-mono text-[10px] text-muted-foreground">
                        <span className="min-w-0 flex-1 truncate">{j.p.label || 'Working…'}</span>
                        <span className="shrink-0">{j.pct != null ? `${j.pct}%` : ''} · {j.p.current}/{j.p.total}</span>
                        {j.speed > 0 && <span className="shrink-0 text-ok">{fmtSpeed(j.speed)}</span>}
                      </div>
                    </>
                  ) : (
                    <div className="mt-1 flex items-center gap-1 font-mono text-[10px] text-muted-foreground">
                      <Loader2 className="size-3 animate-spin" /> working…
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Log console */}
            <div className="flex min-h-0 flex-col">
              <div ref={logRef} className="min-h-0 flex-1 overflow-auto rounded-lg border bg-card/50 p-1.5 font-mono text-[11px] leading-relaxed">
                {visibleLogs.length === 0 && <p className="p-2 text-muted-foreground">No log entries match.</p>}
                {visibleLogs.map((l) => {
                  const cat = catOf(l);
                  const cls = CATEGORIES.find((c) => c.key === cat)?.cls || 'text-foreground';
                  return (
                    <div key={l.id} className={cn('flex items-start gap-1.5 px-1 py-0.5 break-all', cls)}>
                      <span className="min-w-0">{l.message || l.label || ''}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Running-job context menu */}
      {jobMenu && (
        <div style={{ top: jobMenu.y, left: jobMenu.x }} className="fixed z-[60] w-48 overflow-hidden rounded-lg border bg-popover p-1 shadow-xl"
          onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); }}>
          <button onClick={terminateJob}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm font-medium text-destructive hover:bg-accent">
            <Square className="size-4" /> Terminate job
          </button>
        </div>
      )}
    </div>
  );
}