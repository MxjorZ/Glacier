import { Loader2, Server, AlertTriangle } from 'lucide-react';
import { Badge } from '@/components/ui/badge.jsx';

// Top bar (40px). Left: Glacier status + running jobs. Right: error bell +
// server IP. Clicking the error bell opens the Error Center.
export default function TitleBar({ sys, jobsCount, errorCount, onErrors, onLogs }) {
  const running = jobsCount > 0;
  return (
    <header className="fixed left-14 right-0 top-0 z-20 flex h-10 items-center justify-between border-b bg-background/80 px-4 backdrop-blur">
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${running ? 'bg-warn' : 'bg-ok'}`} />
        <span className="text-sm font-semibold">Glacier</span>
        {sys?.version && <Badge variant="secondary" className="font-mono">v{sys.version}</Badge>}
        {running && (
          <Badge variant="warning" className="gap-1 font-mono text-[11px]">
            <Loader2 className="size-3 animate-spin" /> {jobsCount} running
          </Badge>
        )}
      </div>
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        {errorCount > 0 && (
          <button onClick={onErrors} title="Open Error Center" className="flex items-center gap-1 rounded-full bg-destructive/15 px-2 py-0.5 font-semibold text-destructive hover:bg-destructive/25">
            <AlertTriangle className="size-3.5" /> {errorCount} error{errorCount === 1 ? '' : 's'}
          </button>
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

