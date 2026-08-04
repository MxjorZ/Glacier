import {
  LayoutDashboard, LibraryBig, Wrench, Trash2, Tag, Radio, ScrollText, Settings, Info,
} from 'lucide-react';
import { Button } from '@/components/ui/button.jsx';
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip.jsx';

const NAV = [
  { key: 'dashboard', label: 'Dashboard', Icon: LayoutDashboard },
  { key: 'libraries', label: 'Libraries', Icon: LibraryBig },
  { key: 'tools', label: 'Tools', Icon: Wrench },
  { key: 'cleanup', label: 'Cleanup', Icon: Trash2 },
  { key: 'tags', label: 'Tags', Icon: Tag },
  { key: 'plex', label: 'Plex', Icon: Radio },
  { key: 'logs', label: 'Logs', Icon: ScrollText },
  { key: 'settings', label: 'Settings', Icon: Settings },
  { key: 'about', label: 'About', Icon: Info },
];

export default function Sidebar({ page, onNavigate }) {
  return (
    <div className="fixed left-0 top-0 z-30 flex h-full w-14 flex-col items-center border-r bg-card py-3">
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
                  className={`h-10 w-10 ${active ? 'bg-primary/10 text-primary hover:bg-primary/20' : 'hover:bg-primary/10 hover:text-primary'}`}
                  onClick={() => onNavigate(key)}
                >
                  <Icon size={20} />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">
                <p>{label}</p>
              </TooltipContent>
            </Tooltip>
          );
        })}
      </div>
    </div>
  );
}
