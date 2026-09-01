import { useState, useEffect } from 'react';
import { RefreshCw, Copy, ShieldCheck, Play, AlertTriangle } from 'lucide-react';
import { api } from '../../api.js';
import { useJob } from '../../useJob.js';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select.jsx';
import { Empty } from '../../components/PageHeader.jsx';
import { Confirm } from '../../components/dialog-helpers.jsx';
import { toast } from '../../toast.jsx';

const RESOLVE_POLICIES = [
  { value: 'keep_best_quality', label: 'Keep best quality copy' },
  { value: 'keep_newest', label: 'Keep newest copy' },
];

// In-library duplicate scanner + resolver. Extras are quarantined
// (never deleted): dry-run previews exactly what will move, apply requires
// explicit confirmation.
export default function Duplicates() {
  const [libs, setLibs] = useState([]);
  const [libId, setLibId] = useState('');
  const { running, run } = useJob();
  const [dupGroups, setDupGroups] = useState(null);
  const [resolvePolicy, setResolvePolicy] = useState('keep_best_quality');
  const [resolvePlan, setResolvePlan] = useState([]);
  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => {
    api.settings().then((s) => {
      const l = s.libraries || [];
      setLibs(l);
      if (l.length) setLibId(l[0].id);
    }).catch(() => {});
  }, []);

  const scanDup = async () => {
    setDupGroups(null);
    setResolvePlan([]);
    const res = await run('duplicates', { library_id: libId });
    if (res?.ok) { setDupGroups(res.groups || []); toast.success(`${res.count} duplicate groups`); }
    else toast.error(res.error || 'Scan failed');
  };

  const dryRunResolve = async () => {
    setResolvePlan([]);
    const res = await run('duplicates-resolve', {
      library_id: libId, policy: resolvePolicy, dry_run: true,
    });
    if (res?.ok) {
      setResolvePlan(res.plan || []);
      toast.success(`${res.count} extra copy${res.count === 1 ? '' : 'ies'} would be quarantined`);
    } else toast.error(res.error || 'Dry-run failed');
  };

  const applyResolve = async () => {
    setConfirmOpen(false);
    const res = await run('duplicates-resolve', {
      library_id: libId, policy: resolvePolicy, dry_run: false, confirm: true,
    });
    if (res?.ok) {
      toast.success(`Quarantined ${res.acted} extra cop${res.acted === 1 ? 'y' : 'ies'}`);
      setResolvePlan([]);
      scanDup();
    } else toast.error(res.error || 'Apply failed');
  };

  const groupLabel = (g) => {
    const tr = (g.tracks || [])[0] || {};
    return tr.tags ? `${tr.tags.artist || '?'} – ${tr.tags.title || '?'}`
      : (g.identity || 'Track');
  };

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Select value={libId} onValueChange={setLibId}>
          <SelectTrigger className="w-56"><SelectValue placeholder="Select a library" /></SelectTrigger>
          <SelectContent>
            {libs.map((l) => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" disabled={running || !libId} onClick={scanDup}>
          <RefreshCw className="size-3.5" /> Scan
        </Button>
        {dupGroups && dupGroups.length > 0 && (
          <div className="flex items-center gap-2">
            <Select value={resolvePolicy} onValueChange={setResolvePolicy}>
              <SelectTrigger className="w-56"><SelectValue /></SelectTrigger>
              <SelectContent>
                {RESOLVE_POLICIES.map((p) => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
              </SelectContent>
            </Select>
            <Button variant="outline" size="sm" disabled={running} onClick={dryRunResolve}>
              <ShieldCheck className="size-3.5" /> Resolve dry run
            </Button>
            <Button size="sm" disabled={running || resolvePlan.length === 0} onClick={() => setConfirmOpen(true)}>
              <Play className="size-3.5" /> Quarantine {resolvePlan.length || ''} extras
            </Button>
          </div>
        )}
      </div>

      {resolvePlan.length > 0 && (
        <Card className="mb-4 border-warn/40">
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2 text-warn">
              <AlertTriangle className="size-4" /> Dry run: {resolvePlan.length} file(s) would move to quarantine
            </CardTitle>
            <CardDescription>Nothing has been touched yet — apply to move these out of the library.</CardDescription>
          </CardHeader>
          <CardContent className="pt-4">
            <div className="max-h-48 space-y-0.5 overflow-auto font-mono text-xs">
              {resolvePlan.slice(0, 200).map((p, i) => (
                <div key={i} className="truncate text-muted-foreground">
                  {p.source} <span className="text-foreground">→</span> {p.destination}
                </div>
              ))}
              {resolvePlan.length > 200 && (
                <p className="pt-1 text-muted-foreground">…and {resolvePlan.length - 200} more</p>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Copy className="size-4 text-primary" /> In-library duplicates</CardTitle>
          <CardDescription>Report repeated tracks within the selected library — extras are quarantined, never deleted.</CardDescription>
        </CardHeader>
        <CardContent>
          {!dupGroups ? <Empty text="Scan a library to find duplicates." /> : dupGroups.length === 0 ? (
            <Empty text="No duplicate groups found." />
          ) : (
            <div className="max-h-64 space-y-3 overflow-auto">
              {dupGroups.map((g, i) => (
                <div key={i} className="glass-surface rounded-lg border border-white/10 p-2 text-xs">
                  <div className="font-medium">{groupLabel(g)}</div>
                  <div className="mt-1 space-y-0.5 font-mono text-muted-foreground">
                    {(g.tracks || []).map((f, j) => (
                      <div key={j} className="truncate">{f.path}</div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Confirm
        open={confirmOpen}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={applyResolve}
        title="Quarantine duplicate copies?"
        message={`This moves ${resolvePlan.length} extra copies to the quarantine folder (~/.glacier_quarantine). Nothing is deleted — you can restore them any time.`}
        confirmLabel="Quarantine extras"
        danger
      />
    </div>
  );
}
