import { useEffect, useState } from 'react';
import { Search, Trash2, AlertTriangle, FileX, CheckCircle } from 'lucide-react';
import { api } from '../../api.js';
import { useJob } from '../../useJob.js';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select.jsx';
import { Empty } from '../../components/PageHeader.jsx';
import { Confirm } from '../../components/dialog-helpers.jsx';
import { toast } from '../../toast.jsx';

const KINDS = [
  { value: 'empty', label: 'Empty Folders' },
  { value: 'dup_fold', label: 'Duplicate Folder Shells' },
  { value: 'missing_tags', label: 'Missing Required Tags' },
  { value: 'corrupt', label: 'Corrupt / Unreadable Files' },
];

export default function Cleanup() {
  const [libs, setLibs] = useState([]);
  const [kind, setKind] = useState('empty');
  const [id, setId] = useState('');
  const [result, setResult] = useState(null);
  const [confirm, setConfirm] = useState(false);
  const { running, run } = useJob();

  useEffect(() => {
    api.libraries().then((l) => { setLibs(l); if (l[0]) setId(l[0].id); }).catch(() => {});
  }, []);

  const scan = async () => {
    setResult(null);
    const res = await run('cleanup', { library_id: id, kind });
    if (res?.ok) { setResult(res); toast.info(`Found ${res.count} item(s)`); }
    else if (res?.error) toast.error(res.error);
  };

  const paths = result ? (result.folders || result.items || []) : [];

  const apply = async () => {
    const list = paths.map((p) => (typeof p === 'string' ? p : p.path));
    const res = await run('cleanup-apply', { library_id: id, kind, paths: list, confirm: true });
    setConfirm(false);
    setResult(null);
    if (res?.ok) toast.success(`Removed ${res.removed} item(s)`);
    else if (res?.error) toast.error(res.error);
  };

  return (
    <div>
      <Card>
        <CardHeader>
          <CardTitle>Cleanup Configuration</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-center gap-3">
            <div className="w-56">
              <Select value={kind} onValueChange={setKind}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {KINDS.map((k) => <SelectItem key={k.value} value={k.value}>{k.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="w-56">
              <Select value={id} onValueChange={setId}>
                <SelectTrigger><SelectValue placeholder="Select library" /></SelectTrigger>
                <SelectContent>
                  {libs.map((l) => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <Button onClick={scan} disabled={running || !id}>
              <Search className="size-4" /> Scan
            </Button>
            {result && paths.length > 0 && kind !== 'missing_tags' && kind !== 'corrupt' && (
              <Button variant="destructive" onClick={() => setConfirm(true)}>
                <Trash2 className="size-4" /> Delete {paths.length} items
              </Button>
            )}
          </div>

          {kind === 'missing_tags' && result && (
            <p className="mt-3 text-xs text-muted-foreground">Missing tag issues are informational. Use the Tags tab to correct metadata.</p>
          )}
          {kind === 'corrupt' && result && (
            <p className="mt-3 text-xs text-muted-foreground">Corrupt audio files cannot be auto-deleted. Inspect files manually.</p>
          )}
        </CardContent>
      </Card>

      {result && (
        <Card className="mt-6">
          <CardHeader className="border-b">
            <CardTitle>Results ({paths.length})</CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            {paths.length === 0 ? (
              <div className="flex items-center gap-2 text-sm text-ok">
                <CheckCircle className="size-4" /> Clean! No issues detected.
              </div>
            ) : (
              <ul className="max-h-96 overflow-auto space-y-1 font-mono text-xs">
                {paths.map((p, i) => (
                  <li key={i} className="rounded border bg-muted/30 px-3 py-2 text-muted-foreground">
                    {typeof p === 'string' ? p : `${p.path} (missing: ${p.missing?.join(', ')})`}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      )}

      <Confirm
        open={confirm}
        onCancel={() => setConfirm(false)}
        onConfirm={apply}
        title="Confirm File Purge"
        message={`Permanently remove ${paths.length} item(s) from disk? This operation cannot be undone.`}
        confirmLabel="Purge Items"
        danger
      />
    </div>
  );
}