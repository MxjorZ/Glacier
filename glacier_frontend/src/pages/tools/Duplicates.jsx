import { useState } from 'react';
import { RefreshCw, Copy } from 'lucide-react';
import { api } from '../../api.js';
import { useJob } from '../../useJob.js';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardAction } from '@/components/ui/card.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select.jsx';
import { Empty } from '../../components/PageHeader.jsx';
import { toast } from '../../toast.jsx';
import { useEffect } from 'react';

export default function Duplicates() {
  const [libs, setLibs] = useState([]);
  const [libId, setLibId] = useState('');
  const { running, run } = useJob();
  const [dupGroups, setDupGroups] = useState(null);

  useEffect(() => {
    api.settings().then((s) => {
      const l = s.libraries || [];
      setLibs(l);
      if (l.length) setLibId(l[0].id);
    }).catch(() => {});
  }, []);

  const scanDup = async () => {
    const res = await run('duplicates', { library_id: libId });
    if (res?.ok) { setDupGroups(res.groups || []); toast.success(`${res.count} duplicate groups`); }
    else toast.error(res.error || 'Scan failed');
  };

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <Select value={libId} onValueChange={setLibId}>
          <SelectTrigger className="w-56"><SelectValue placeholder="Select a library" /></SelectTrigger>
          <SelectContent>
            {libs.map((l) => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" disabled={running || !libId} onClick={scanDup}>
          <RefreshCw className="size-3.5" /> Scan
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Copy className="size-4 text-primary" /> In-library duplicates</CardTitle>
          <CardDescription>Find repeated tracks within the selected library</CardDescription>
        </CardHeader>
        <CardContent>
          {!dupGroups ? <Empty text="Scan a library to find duplicates." /> : dupGroups.length === 0 ? (
            <Empty text="No duplicate groups found." />
          ) : (
            <div className="max-h-64 space-y-3 overflow-auto">
              {dupGroups.map((g, i) => (
                <div key={i} className="rounded-lg border bg-muted/30 p-2 text-xs">
                  <div className="font-medium">{g.title || g.artist || 'Track'}</div>
                  <div className="mt-1 space-y-0.5 font-mono text-muted-foreground">
                    {(g.files || g.tracks || []).map((f, j) => <div key={j} className="truncate">{f.path || f}</div>)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}