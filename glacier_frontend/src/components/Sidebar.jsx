import { useEffect, useState } from 'react';
import {
  LayoutDashboard, LibraryBig, Wrench, Radio, ScrollText, Settings, Info, ShieldAlert,
  ChevronsLeft, ChevronsRight,
} from 'lucide-react';
import { Button } from '@/components/ui/button.jsx';

const NAV = [
  { key: 'dashboard', label: 'Dashboard', Icon: LayoutDashboard },
  { key: 'libraries', label: 'Libraries', Icon: LibraryBig },
  { key: 'tools', label: 'Tools', Icon: Wrench },
  { key: 'plex', label: 'Plex', Icon: Radio },
  { key: 'logs', label: 'Logs', Icon: ScrollText },
  { key: 'errors', label: 'Error Center', Icon: ShieldAlert },
  { key: 'settings', label: 'Settings', Icon: Settings },
  { key: 'about', label: 'About', Icon: Info },
];

// Expandable glass rail. Collapsed it's an icon strip; expanding slides it
// out (left -> right) and fades in the page labels next to each icon. The
// choice persists per browser; the main content follows the rail's width so
// nothing ever sits underneath it.
export default function Sidebar({ page, onNavigate }) {
  const [expanded, setExpanded] = useState(() => {
    try { return localStorage.getItem('glacier-sidebar') === 'expanded'; }
    catch { return false; }
  });

  useEffect(() => {
    try { localStorage.setItem('glacier-sidebar', expanded ? 'expanded' : 'collapsed'); }
    catch { /* private mode */ }
    document.documentElement.style.setProperty('--rail-w', expanded ? '12rem' : '4rem');
  }, [expanded]);

  return (
    <div className={`sidebar-container ${expanded ? 'expanded' : ''}`}>
      <div className="mb-3 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary ring-1 ring-primary/30 transition-all duration-300 hover:scale-110 hover:shadow-[0_0_16px_var(--primary)]">
        <span className="text-lg font-bold">G</span>
      </div>

      <nav className="flex flex-1 flex-col gap-1.5">
        {NAV.map(({ key, label, Icon }) => {
          const active = page === key;
          return (
            <button
              key={key}
              onClick={() => onNavigate(key)}
              aria-label={label}
              className={`nav-item group ${active ? 'active' : ''}`}
            >
              <span className="nav-icon-glow" aria-hidden="true" />
              <Icon size={20} className="relative z-10 shrink-0 transition-all duration-300 group-hover:scale-110 group-active:scale-90" />
              <span className={`nav-item-label ${expanded ? 'shown' : ''}`}>{label}</span>
            </button>
          );
        })}
      </nav>

      <button
        onClick={() => setExpanded((v) => !v)}
        className="nav-item mt-2"
        aria-label={expanded ? 'Collapse sidebar' : 'Expand sidebar'}
        title={expanded ? 'Collapse' : 'Expand'}
      >
        {expanded
          ? <ChevronsLeft size={18} className="relative z-10 transition-all duration-300 group-hover:scale-110" />
          : <ChevronsRight size={18} className="relative z-10 transition-all duration-300 group-hover:scale-110" />}
        <span className={`nav-item-label ${expanded ? 'shown' : ''}`}>Collapse</span>
      </button>
    </div>
  );
}
