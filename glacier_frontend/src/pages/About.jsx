import { Server, FolderTree, FileCog, Boxes } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card.jsx';
import { PageHeader } from '../components/PageHeader.jsx';

export default function About({ sys }) {
  const rows = [
    { Icon: Server, label: 'Server', value: sys ? `${sys.ip}:${sys.port}` : '—' },
    { Icon: FolderTree, label: 'Settings', value: sys?.settings_path || '—' },
    { Icon: FileCog, label: 'Cache dir', value: sys?.cache_dir || '—' },
  ];
  return (
    <div>
      <PageHeader title="About" description="Glacier — self-hosted music library manager." />
      <Card className="mx-auto max-w-xl">
        <CardHeader className="border-b">
          <CardTitle className="text-lg">Glacier</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm text-muted-foreground">
          <p>
            Glacier manages large local FLAC/MP3 libraries: it scans, organizes,
            cleans, tags, and reports on collections, and guarantees that the same
            track does not exist in multiple managed libraries (library exclusivity).
          </p>
          <div className="space-y-2 border-t pt-3">
            {rows.map(({ Icon, label, value }) => (
              <div key={label} className="flex items-center justify-between">
                <span className="flex items-center gap-2"><Icon className="size-4" /> {label}</span>
                <span className="font-mono text-xs text-foreground">{value}</span>
              </div>
            ))}
          </div>
          <div className="flex items-start gap-2 border-t pt-3 text-xs">
            <Boxes className="mt-0.5 size-4 shrink-0" />
            <p>Backend: Python · Flask · mutagen · plexapi. Frontend: React · Tailwind v4 · shadcn/ui. Visual language inspired by SpotiFLAC; Glacier is an independent product.</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
