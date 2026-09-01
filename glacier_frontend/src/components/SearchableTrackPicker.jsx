import { useEffect, useMemo, useRef, useState } from 'react';
import { Search, Music2, Loader2, X } from 'lucide-react';
import { api } from '../api.js';
import { Input } from '@/components/ui/input.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Badge } from '@/components/ui/badge.jsx';
import { cn } from '@/lib/utils.js';

// Shared searchable song picker — every tool that needs "pick any track from
// the library" uses this. Searches server-side across artist / album artist /
// album / title / genre (so a huge library never loads fully into the page).
//
// Props:
//   libraries        — [{id, name}] (falls back to fetching settings itself)
//   libraryId        — selected library id (controlled optional)
//   onLibraryChange  — called when the user switches library
//   value            — currently selected track path
//   onChange         — called with the selected track object
//   placeholder      — search placeholder
//   compact          — tighter layout for embedding in toolbars
export default function SearchableTrackPicker({
  libraries = null,
  libraryId = '',
  onLibraryChange = () => {},
  value = '',
  onChange = () => {},
  placeholder = 'Search songs — title, artist, album, genre…',
  compact = false,
}) {
  const [libs, setLibs] = useState(libraries);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [sel, setSel] = useState(null);
  const [highlight, setHighlight] = useState(0);
  const rootRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (libraries) return;
    let alive = true;
    api.settings().then((s) => { if (alive) setLibs(s.libraries || []); }).catch(() => {});
    return () => { alive = false; };
  }, [libraries]);

  // The controlled libraryId is authoritative when provided; the fallback only
  // kicks in for uncontrolled usage.
  const effectiveLib = libraryId || libs?.[0]?.id || '';

  // Server-side search (debounced).
  useEffect(() => {
    if (!effectiveLib) { setResults([]); setTotal(0); return; }
    let alive = true;
    setBusy(true);
    const t = setTimeout(async () => {
      try {
        const res = await api.tracks({ library_id: effectiveLib, page: 1, per_page: 50,
                                       sort: 'title', order: 'asc', query });
        if (alive) { setResults(res.items || []); setTotal(res.total || 0); }
      } catch { if (alive) setResults([]); }
      finally { if (alive) setBusy(false); }
    }, 220);
    return () => { alive = false; clearTimeout(t); };
  }, [query, effectiveLib]);

  // Reset selection when the library changes out from under us.
  useEffect(() => {
    setSel(null);
    setResults([]);
    setTotal(0);
  }, [effectiveLib]);

  // Track click-outside / Escape.
  useEffect(() => {
    const onDown = (e) => { if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('mousedown', onDown);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('mousedown', onDown);
      window.removeEventListener('keydown', onKey);
    };
  }, []);

  const pick = (t) => {
    setSel(t);
    onChange(t);
    setOpen(false);
  };

  const onKeyDown = (e) => {
    if (!open && (e.key === 'ArrowDown' || e.key === 'Enter')) { setOpen(true); e.preventDefault(); return; }
    if (!open) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); setHighlight((h) => Math.min(h + 1, results.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setHighlight((h) => Math.max(h - 1, 0)); }
    else if (e.key === 'Enter') { e.preventDefault(); if (results[highlight]) pick(results[highlight]); }
  };

  const label = sel
    ? `${sel.artist || '?'} — ${sel.title || sel.path?.split(/[\\/]/).pop()}`
    : (value ? value.split(/[\\/]/).pop() : '');

  return (
    <div ref={rootRef} className={cn('relative', compact ? 'w-full' : 'w-full max-w-3xl')}>
      <div className="glass-surface flex items-center gap-2 rounded-xl border border-white/10 px-3 py-2 shadow-glass transition-all focus-within:border-primary/50 focus-within:shadow-glass-lg">
        <Search className="size-4 shrink-0 text-muted-foreground" />
        <input
          ref={inputRef}
          value={open ? query : label}
          onFocus={() => { setOpen(true); setQuery(''); }}
          onChange={(e) => { setOpen(true); setQuery(e.target.value); setHighlight(0); }}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        />
        {(label || query) && (
          <button
            onClick={() => { setSel(null); setQuery(''); onChange(null); inputRef.current?.focus(); }}
            className="rounded p-0.5 text-muted-foreground transition-all hover:scale-110 hover:text-foreground"
            aria-label="Clear selection"
          >
            <X className="size-3.5" />
          </button>
        )}
        {busy && <Loader2 className="size-4 shrink-0 animate-spin text-primary" />}
        {!busy && total > 0 && (
          <Badge variant="secondary" className="shrink-0 font-mono text-[10px]">{total.toLocaleString()}</Badge>
        )}
        {libs && libs.length > 0 && (
          <select
            value={effectiveLib}
            onChange={(e) => { onLibraryChange(e.target.value); setSel(null); onChange(null); }}
            className="glass-select max-w-36 shrink-0 rounded-lg border border-white/10 bg-transparent px-2 py-1 text-xs text-foreground outline-none"
            aria-label="Library"
          >
            {libs.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        )}
      </div>

      {open && (
        <div className="glass-surface-strong absolute z-50 mt-2 max-h-80 w-full overflow-auto rounded-xl border border-white/10 p-1.5 shadow-glass-lg anim-fade">
          {results.length === 0 && !busy && (
            <p className="p-3 text-center text-xs text-muted-foreground">
              {query ? `No songs match “${query}”.` : 'Start typing to search the library.'}
            </p>
          )}
          {results.map((t, i) => (
            <button
              key={t.path}
              onMouseEnter={() => setHighlight(i)}
              onClick={() => pick(t)}
              className={cn(
                'flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-all',
                i === highlight ? 'bg-primary/15 text-primary' : 'hover:bg-white/5')}
            >
              <Music2 className={cn('size-4 shrink-0', i === highlight ? 'text-primary' : 'text-muted-foreground')} />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{t.title || t.path?.split(/[\\/]/).pop()}</span>
                <span className="block truncate text-xs text-muted-foreground">
                  {t.artist || '?'}{t.album ? ` · ${t.album}` : ''}{t.genre ? ` · ${t.genre}` : ''}
                </span>
              </span>
              {t.format && <Badge variant="outline" className="shrink-0 font-mono text-[9px] uppercase">{t.format}</Badge>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
