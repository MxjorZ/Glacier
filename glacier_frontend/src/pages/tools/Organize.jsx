import { useEffect, useState } from 'react';
import { RefreshCw, Play, FolderTree } from 'lucide-react';
import { api } from '../../api.js';
import { useJob } from '../../useJob.js';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardAction } from '@/components/ui/card.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Badge } from '@/components/ui/badge.jsx';
import { Input } from '@/components/ui/input.jsx';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select.jsx';
import { Empty } from '../../components/PageHeader.jsx';
import { Confirm } from '../../components/dialog-helpers.jsx';
import { toast } from '../../toast.jsx';

export default function Organize() {
  const [libs, setLibs] = useState([]);
  const [libId, setLibId] = useState('');
  const { running, run } = useJob();
  const [folderPattern, setFolderPattern] = useState('');
  const [namingPattern, setNamingPattern] = useState('');
  const [preview, setPreview] = useState(null);
  const [orgPlan, setOrgPlan] = useState([]);
  const [orgApply, setOrgApply] = useState(false);

  useEffect(() => {
    api.settings().then((s) => {
      const l = s.libraries || [];
      setLibs(l);
      if (l.length) setLibId(l[0].id);
      setFolderPattern(s.folder_pattern || '');
      setNamingPattern(s.naming_pattern || '');
    }).catch(() => {});
  }, []);

  // Live preview
  useEffect(() => {
    if (!folderPattern && !namingPattern) return;
    const t = setTimeout(async () => {
      try {
        const res = await api.previewPath({
          folder_pattern: folderPattern,
          naming_pattern: namingPattern,
          library_id: libId || undefined,
          ext: '.flac',
          sample_tags: {
            artist: 'Singer Name', albumartist: 'Band Name', album: 'Album Title',
            title: 'Song Title', track: '1/12', date: '1999',
          },
        });
        setPreview(res);
      } catch { /* ignored */ }
    }, 150);
    return () => clearTimeout(t);
  }, [folderPattern, namingPattern, libId]);

  const organize = async (dryRun) => {
    const res = await run('organize', { library_id: libId, dry_run: dryRun, confirm: !dryRun });
    if (dryRun) {
      if (res?.ok) { setOrgPlan(res.plan || []); toast.success(`${res.count} files would be moved`); }
      else toast.error(res.error || 'Dry-run failed');
    } else if (res?.ok) {
      toast.success(`Moved ${res.moved} files`); setOrgApply(false); setOrgPlan([]);
    } else toast.error(res.error || 'Apply failed');
  };

  const libName = (id) => (libs.find((l) => l.id === id) || {}).name || '—';

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <Select value={libId} onValueChange={setLibId}>
          <SelectTrigger className="w-56"><SelectValue placeholder="Select a library" /></SelectTrigger>
          <SelectContent>
            {libs.map((l) => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" disabled={running || !libId} onClick={() => organize(true)}>
          <RefreshCw className="size-3.5" /> Dry run
        </Button>
        <Button size="sm" disabled={running || !libId} onClick={() => setOrgApply(true)}>
          <Play className="size-3.5" /> Apply
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><FolderTree className="size-4 text-primary" /> Organize</CardTitle>
          <CardDescription>Apply folder &amp; naming patterns</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">Folder pattern</label>
              <Input value={folderPattern} onChange={(e) => setFolderPattern(e.target.value)} className="font-mono text-xs" />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">Filename pattern</label>
              <Input value={namingPattern} onChange={(e) => setNamingPattern(e.target.value)} className="font-mono text-xs" />
            </div>
          </div>

          {preview && (
            <div className="rounded-lg border bg-muted/30 p-3 font-mono text-xs">
              <div className="mb-1 flex items-center justify-between">
                <span className="text-muted-foreground">Live preview (sample track)</span>
                {preview.unknown_tokens?.length > 0 && (
                  <Badge variant="destructive">Unknown tokens: {preview.unknown_tokens.join(', ')}</Badge>
                )}
              </div>
              <div className="text-foreground">{preview.relative_path}</div>
              <div className="break-all text-muted-foreground">{preview.full_path || 'select a library to show full path'}</div>
              {preview.unknown_tokens?.length > 0 && (
                <p className="mt-1 text-destructive">Invalid/unknown tokens highlighted — fix them before organizing.</p>
              )}
            </div>
          )}

          {orgPlan.length === 0 ? <Empty text="Run a dry run to preview the move plan." /> : (
            <div className="max-h-64 space-y-1 overflow-auto font-mono text-xs">
              {orgPlan.slice(0, 200).map((p, i) => (
                <div key={i} className="flex items-baseline justify-between gap-2 border-b border-border/50 py-1">
                  <span className="truncate">{p.from || p.src}</span>
                  <span className="ml-auto shrink-0 text-muted-foreground">{p.to || p.dst}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Confirm
        open={orgApply}
        title="Apply folder organization?"
        message={`This will move ${orgPlan.length || 'files'} according to the configured patterns in "${libName(libId)}".`}
        onCancel={() => setOrgApply(false)}
        onConfirm={() => organize(false)}
        confirmLabel="Apply"
      />
    </div>
  );
}