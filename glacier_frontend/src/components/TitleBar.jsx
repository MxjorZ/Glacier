import { Loader2, Server } from 'lucide-react';
import { Badge } from '@/components/ui/badge.jsx';

// Top bar (40px). Left: Glacier status. Right: server IP + job status.
export default function TitleBar({ sys, job, progress }) {
  const running = job?.running;
  return (
    <header className="fixed left-14 right-0 top-0 z-20 flex h-10 items-center justify-between border-b bg-background/80 px-4 backdrop-blur">
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${running ? 'bg-warn' : 'bg-ok'}`} />
        <span className="text-sm font-semibold">Glacier</span>
        {sys?.version && <Badge variant="secondary" className="font-mono">v{sys.version}</Badge>}
      </div>
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        {running && (
          <span className="flex items-center gap-1.5 text-warn">
            <Loader2 className="size-3.5 animate-spin" />
            <span className="font-mono">{job?.job?.operation}…</span>
          </span>
        )}
        {sys && (
          <span className="flex items-center gap-1 font-mono">
            <Server className="size-3.5" /> {sys.ip}:{sys.port}
          </span>
        )}
      </div>
    </header>
  );
}
