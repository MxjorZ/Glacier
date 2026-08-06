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
      <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
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
                  className={`sidebar-icon h-10 w-10 ${active ? 'active bg-primary/10 text-primary hover:bg-primary/20' : 'hover:bg-primary/10 hover:text-primary'}`}
                  onClick={() => onNavigate(key)}
                >
                  <Icon size={20} />
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