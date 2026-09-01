import { useEffect, useRef, useState, useCallback } from 'react';
import { Search, Music2, LayoutGrid, Wrench, LibraryBig, Radio, ScrollText, Settings, ArrowRight, Loader2 } from 'lucide-react';
import { api } from '../api.js';
import { cn } from '@/lib/utils.js';

// Global command palette (Ctrl+K / Cmd+K): jump between pages, open tools,
// and search tracks across every library — without touching the mouse.
export default function CommandPalette({ open, onClose, onNavigate, onOpenTool, onPlayTrack }) {
  const [query, setQuery] = useState('');
  const [tracks, setTracks] = useState([]);
  const [busy, setBusy] = useState(false);
  const [libs, setLibs] = useState([]);
  const [highlight, setHighlight] = useState(0);
  const rootRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (open) { setQuery(''); setTracks([]); setHighlight(0); setTimeout(() => inputRef.current?.focus(), 30); }
  }, [open]);

  useEffect(() => {
    if (!libs.length) api.settings().then((s) => setLibs(s.libraries || [])).catch(() => {});
  }, [libs.length, open]);

  // Debounced track search once the query is 2+ chars.
  useEffect(() => {
    if (!open || query.trim().length < 2 || !libs.length) { setTracks([]); return; }
    let alive = true;
    setBusy(true);
    const t = setTimeout(async () => {
      try {
        const res = await api.tracks({ library_id: libs[0].id, page: 1, per_page: 8, query });
        if (alive) setTracks(res.items || []);
      } catch { /* ignore */ }
      finally { if (alive) setBusy(false); }
    }, 200);
    return () => { alive = false; clearTimeout(t); };
  }, [query, open, libs]);

  const PAGES = [
    { key: 'dashboard', label: 'Dashboard', Icon: LayoutGrid, kind: 'page' },
    { key: 'libraries', label: 'Libraries', Icon: LibraryBig, kind: 'page' },
    { key: 'tools', label: 'Tools', Icon: Wrench, kind: 'page' },
    { key: 'plex', label: 'Plex', Icon: Radio, kind: 'page' },
    { key: 'logs', label: 'Logs', Icon: ScrollText, kind: 'page' },
    { key: 'settings', label: 'Settings', Icon: Settings, kind: 'page' },
  ];
  const TOOLS = [
    { id: 'organize', label: 'Organize' }, { id: 'duplicates', label: 'Duplicates' },
    { id: 'exclusivity', label: 'Exclusivity' }, { id: 'cleanup', label: 'Cleanup' },
    { id: 'import', label: 'Import Folder' }, { id: 'genres', label: 'Genre Manager' },
    { id: 'tags', label: 'Tags Manager' }, { id: 'audioquality', label: 'Audio Quality Analyzer' },
    { id: 'filemanager', label: 'File Manager' },
  ];

  const items = (() => {
    const q = query.trim().toLowerCase();
    const pages = PAGES.filter((p) => !q || p.label.toLowerCase().includes(q))
      .map((p) => ({ ...p, group: 'Pages' }));
    const tools = (!q ? TOOLS.slice(0, 4) : TOOLS.filter((t) => t.label.toLowerCase().includes(q)))
      .map((t) => ({ ...t, Icon: Wrench, kind: 'tool', group: 'Tools' }));
    const tr = tracks.map((t) => ({
      kind: 'track', label: `${t.title || '?'} — ${t.artist || '?'}`,
      sub: t.album, track: t, Icon: Music2, group: 'Tracks',
    }));
    return [...pages, ...tools, ...tr];
  })();

  const choose = useCallback((item) => {
    if (!item) return;
    onClose();
    if (item.kind === 'page') onNavigate(item.key);
    else if (item.kind === 'tool') { onNavigate('tools'); onOpenTool(item.id); }
    else if (item.kind === 'track') onPlayTrack?.(item.track);
  }, [onClose, onNavigate, onOpenTool, onPlayTrack]);

  const onKeyDown = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setHighlight((h) => Math.min(h + 1, items.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setHighlight((h) => Math.max(h - 1, 0)); }
    else if (e.key === 'Enter') { e.preventDefault(); choose(items[highlight]); }
    else if (e.key === 'Escape') { e.preventDefault(); onClose(); }
  };

  useEffect(() => { setHighlight(0); }, [query]);

  if (!open) return null;

  let lastGroup = '';
  return (
    <div className="fixed inset-0 z-[70] flex items-start justify-center bg-black/40 p-4 pt-[12vh] backdrop-blur-sm anim-fade"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div ref={rootRef} className="glass-surface-strong w-full max-w-xl overflow-hidden rounded-2xl">
        <div className="flex items-center gap-3 border-b border-white/10 px-4 py-3">
          <Search className="size-4 shrink-0 text-muted-foreground" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search pages, tools, tracks…"
            className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            style={{ background: 'transparent', border: 'none', boxShadow: 'none', padding: 0 }}
          />
          {busy && <Loader2 className="size-4 shrink-0 animate-spin text-primary" />}
          <kbd className="glass-surface shrink-0 rounded-md px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">ESC</kbd>
        </div>
        <div className="max-h-[50vh] overflow-auto p-2">
          {items.length === 0 && (
            <p className="p-4 text-center text-xs text-muted-foreground">No matches for “{query}”.</p>
          )}
          {items.map((it, i) => {
            const header = it.group !== lastGroup ? it.group : null;
            lastGroup = it.group;
            return (
              <div key={it.kind + it.label + i}>
                {header && (
                  <p className="px-2 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    {header}
                  </p>
                )}
                <button
                  onMouseEnter={() => setHighlight(i)}
                  onClick={() => choose(it)}
                  className={cn(
                    'flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm transition-all',
                    i === highlight ? 'bg-primary/15 text-primary translate-x-0.5' : 'hover:bg-white/5')}
                >
                  {it.Icon && <it.Icon className="size-4 shrink-0" />}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{it.label}</span>
                    {it.sub && <span className="block truncate text-xs text-muted-foreground">{it.sub}</span>}
                  </span>
                  {i === highlight && <ArrowRight className="size-3.5 shrink-0" />}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
