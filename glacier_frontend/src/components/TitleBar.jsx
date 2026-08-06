import { Loader2, Server, AlertTriangle } from 'lucide-react';
import { Badge } from '@/components/ui/badge.jsx';

export default function TitleBar({ sys, jobsCount, errorCount, onErrors, onLogs }) {
  const running = jobsCount > 0;
  return (
    <header className="fixed left-14 right-0 top-0 z-20 flex h-10 items-center justify-between border-b bg-background/80 px-4 backdrop-blur md:px-6">
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${running ? 'bg-warn animate-pulse' : 'bg-ok'}`} />
        <span className="text-sm font-semibold">Glacier</span>
        {sys?.version && <Badge variant="secondary" className="font-mono">v{sys.version}</Badge>}
        {running && (
          <Badge variant="warning" className="gap-1 font-mono text-[11px]">
            <Loader2 className="size-3 animate-spin" /> {jobsCount} running
          </Badge>
        )}
      </div>
      <div className="flex items-center gap-2 text-xs text-muted-foreground md:gap-3">
        {errorCount > 0 && (
          <button
            onClick={onErrors}
            title="Open Error Center"
            className="flex items-center gap-1 rounded-full bg-destructive/15 px-2 py-0.5 font-semibold text-destructive hover:bg-destructive/25 transition-all hover:scale-105"
          >
            <AlertTriangle className="size-3.5" /> <span className="hidden sm:inline">{errorCount} error{errorCount === 1 ? '' : 's'}</span>
            <span className="sm:hidden">{errorCount}</span>
          </button>
        )}
        {sys && (
          <span className="flex items-center gap-1 font-mono">
            <Server className="size-3.5" /> <span className="hidden sm:inline">{sys.ip}:{sys.port}</span>
            <span className="sm:hidden">{sys.port}</span>
          </span>
        )}
      </div>
    </header>
  );
}