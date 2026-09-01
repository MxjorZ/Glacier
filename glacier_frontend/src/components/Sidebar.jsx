import {
  LayoutDashboard, LibraryBig, Wrench, Radio, ScrollText, Settings, Info, ShieldAlert,
} from 'lucide-react';
import { Button } from '@/components/ui/button.jsx';
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip.jsx';

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

export default function Sidebar({ page, onNavigate }) {
  return (
    <div className="sidebar-container">
      <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-primary/15 text-primary ring-1 ring-primary/30 transition-all duration-300 hover:scale-110 hover:shadow-[0_0_16px_var(--primary)]">
        <span className="text-lg font-bold">G</span>
      </div>
      <div className="flex flex-1 flex-col gap-2">
        {NAV.map(({ key, label, Icon }) => {
          const active = page === key;
          return (
            <Tooltip key={key} delayDuration={0}>
              <TooltipTrigger asChild>
                <Button
                  variant={active ? 'secondary' : 'ghost'}
                  size="icon"
                  className={`nav-icon group relative h-10 w-10 ${active ? 'active' : ''}`}
                  onClick={() => onNavigate(key)}
                  aria-label={label}
                >
                  <span className="nav-icon-glow" aria-hidden="true" />
                  <Icon size={20} className="relative z-10 transition-all duration-300 group-hover:scale-110 group-active:scale-90" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right" className="sidebar-label">
                <p>{label}</p>
              </TooltipContent>
            </Tooltip>
          );
        })}
      </div>
    </div>
  );
}