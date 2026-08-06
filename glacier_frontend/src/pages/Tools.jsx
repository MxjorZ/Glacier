import { useEffect, useState } from 'react';
import {
  RefreshCw, FolderTree, Copy, ShieldAlert, ImageDown, ListMusic, FileText, Play,
  FolderPlus, // <-- ADDED for import
} from 'lucide-react';
import { api, fmtBytes } from '../api.js';
import { useJob } from '../useJob.js';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardAction } from '@/components/ui/card.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Badge } from '@/components/ui/badge.jsx';
import { Input } from '@/components/ui/input.jsx';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select.jsx';
import { PageHeader, Empty } from '../components/PageHeader.jsx';
import { Modal, Confirm } from '../components/dialog-helpers.jsx';
import { toast } from '../toast.jsx';

const POLICIES = [
  { value: 'report_only', label: 'Report only (no changes)' },
  { value: 'keep_best_quality', label: 'Keep best quality copy' },
  { value: 'keep_preferred_library', label: 'Keep preferred library' },
  { value: 'keep_newest', label: 'Keep newest copy' },
  { value: 'move_to_library', label: 'Move extras to library' },
  { value: 'quarantine', label: 'Move extras to quarantine' },
];

// Plain‑English descriptions for each policy
const POLICY_DESCRIPTIONS = {
  report_only: "Scans for duplicates but makes zero changes to your files. Just shows you the list of violations.",
  keep_best_quality: "Keeps the highest quality file (FLAC > ALAC > MP3) in the preferred library if set, otherwise keeps the best quality file. Moves lower quality duplicates to quarantine.",
  keep_preferred_library: "Keeps all copies inside your Preferred Library. Moves every duplicate from other libraries INTO that Preferred Library. Best for consolidation.",
  keep_newest: "Keeps the file with the latest modification date. Moves the older duplicates to quarantine.",
  move_to_library: "Keeps the copy already in the Target Library. Moves all other duplicates (extras) INTO that Target Library. (Requires a Target Library.)",
  quarantine: "Moves EVERY duplicate file out of your libraries into a quarantine folder (~/.glacier_quarantine). Use this to completely remove duplicate copies from all libraries.",
};

export default function Tools() {
  const [libs, setLibs] = useState([]);
  const [libId, setLibId] = useState('');
  const { running, run } = useJob();

  // organize
  const [orgPlan, setOrgPlan] = useState([]);
  const [orgApply, setOrgApply] = useState(false);

  // live path/filename preview (Stage 2)
  const [folderPattern, setFolderPattern] = useState('');
  const [namingPattern, setNamingPattern] = useState('');
  const [preview, setPreview] = useState(null);

  // duplicates
  const [dupGroups, setDupGroups] = useState(null);

  // exclusivity
  const [violations, setViolations] = useState([]);
  const [policy, setPolicy] = useState('report_only');
  const [prefId, setPrefId] = useState('');
  const [targetId, setTargetId] = useState('');
  const [exclPlans, setExclPlans] = useState([]);
  const [exclApply, setExclApply] = useState(false);

  // covers / playlists / report
  const [coverRes, setCoverRes] = useState(null);
  const [playlistRes, setPlaylistRes] = useState(null);
  const [report, setReport] = useState(null);

  // -------- NEW: import folder state --------
  const [importSource, setImportSource] = useState('');
  const [importDestLib, setImportDestLib] = useState('');
  const [importPreserve, setImportPreserve] = useState(true);
  const [importMove, setImportMove] = useState(true);

  const runImport = async () => {
    const res = await run('import-folder', {
      source_path: importSource,
      dest_library_id: importDestLib,
      preserve_structure: importPreserve,
      move: importMove,
    });
    if (res?.ok) {
      toast.success(`Imported ${res.moved} files, ${res.errors?.length || 0} errors`);
      setImportSource('');
    } else {
      toast.error(res?.error || 'Import failed');
    }
  };
  // -------- END NEW --------

  useEffect(() => {
    api.settings().then((s) => {
      const l = s.libraries || [];
      setLibs(l);
      if (l.length) { setLibId(l[0].id); setPrefId(l[0].id); setTargetId(l[0].id); setImportDestLib(l[0].id); }
      setFolderPattern(s.folder_pattern || '');
      setNamingPattern(s.naming_pattern || '');
    }).catch(() => {});
  }, []);

  // Live preview updates on every keystroke (debounced <= 150ms), no Apply needed.
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
      } catch { /* preview is best-effort */ }
    }, 150);
    return () => clearTimeout(t);
  }, [folderPattern, namingPattern, libId]);

  const libName = (id) => (libs.find((l) => l.id === id) || {}).name || '—';

  // ---- Organize ----
  const organize = async (dryRun) => {
    const res = await run('organize', { library_id: libId, dry_run: dryRun, confirm: !dryRun });
    if (dryRun) {
      if (res?.ok) { setOrgPlan(res.plan || []); toast.success(`${res.count} files would be moved`); }
      else toast.error(res.error || 'Dry-run failed');
    } else if (res?.ok) {
      toast.success(`Moved ${res.moved} files`); setOrgApply(false); setOrgPlan([]);
    } else toast.error(res.error || 'Apply failed');
  };

  // ---- Duplicates ----
  const scanDup = async () => {
    const res = await run('duplicates', { library_id: libId });
    if (res?.ok) { setDupGroups(res.groups || []); toast.success(`${res.count} duplicate groups`); }
    else toast.error(res.error || 'Scan failed');
  };

  // ---- Exclusivity ----
  const scanExcl = async () => {
    const res = await run('exclusivity', {});
    if (res?.ok) { setViolations(res.violations || []); toast.success(`${res.count} violations`); }
    else toast.error(res.error || 'Scan failed');
  };
  const resolveExcl = async (dryRun) => {
    const res = await run('resolve-exclusivity', {
      policy, preferred_library_id: prefId, move_target_library_id: targetId, dry_run: dryRun, confirm: !dryRun,
    });
    if (dryRun) {
      if (res?.ok) { setExclPlans(res.plans || []); toast.success(`${res.count} groups would be resolved`); }
      else toast.error(res.error || 'Dry-run failed');
    } else if (res?.ok) {
      toast.success(`${res.acted} files processed, ${res.skipped} skipped`); setExclApply(false); setExclPlans([]);
    } else toast.error(res.error || 'Apply failed');
  };

  // ---- Covers / playlists / report ----
  const covers = async (force) => {
    const res = await run(force ? 'rebuild-covers' : 'covers', { library_id: libId });
    if (res?.ok) { setCoverRes(res); toast.success(force ? `Rebuilt ${res.created} covers` : `Extracted ${res.created} covers`); }
    else toast.error(res.error || 'Covers failed');
  };
  const playlists = async () => {
    const res = await run('playlists', { library_id: libId });
    if (res?.ok) { setPlaylistRes(res); toast.success(`Generated ${res.created} playlists`); }
    else toast.error(res.error || 'Playlists failed');
  };
  const generateReport = async () => {
    const res = await run('report', { library_id: libId });
    if (res?.ok) { setReport(res); toast.success('Report generated'); }
    else toast.error(res.error || 'Report failed');
  };

  return (
    <div>
      <PageHeader title="Tools" description="Organize, de-duplicate, enforce exclusivity and export assets.">
        <Select value={libId} onValueChange={setLibId}>
          <SelectTrigger className="w-56"><SelectValue placeholder="Select a library" /></SelectTrigger>
          <SelectContent>
            {libs.map((l) => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
          </SelectContent>
        </Select>
      </PageHeader>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Organize */}
        <Card>
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2"><FolderTree className="size-4 text-primary" /> Organize</CardTitle>
            <CardDescription>Apply folder &amp; naming patterns</CardDescription>
            <CardAction>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" disabled={running || !libId} onClick={() => organize(true)}>
                  <RefreshCw className="size-3.5" /> Dry run
                </Button>
                <Button size="sm" disabled={running || !libId} onClick={() => setOrgApply(true)}>
                  <Play className="size-3.5" /> Apply
                </Button>
              </div>
            </CardAction>
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

        {/* Duplicates */}
        <Card>
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2"><Copy className="size-4 text-primary" /> In-library duplicates</CardTitle>
            <CardDescription>Find repeated tracks within the selected library</CardDescription>
            <CardAction>
              <Button variant="outline" size="sm" disabled={running || !libId} onClick={scanDup}>
                <RefreshCw className="size-3.5" /> Scan
              </Button>
            </CardAction>
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


        {/* Exclusivity */}
        <Card>
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2"><ShieldAlert className="size-4 text-primary" /> Library exclusivity</CardTitle>
            <CardDescription>Ensure each track exists in only one library</CardDescription>
            <CardAction>
              <Button variant="outline" size="sm" disabled={running} onClick={scanExcl}>
                <RefreshCw className="size-3.5" /> Scan
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground">Policy</label>
                <Select value={policy} onValueChange={setPolicy}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {POLICIES.map((p) => (
                      <SelectItem key={p.value} value={p.value} title={POLICY_DESCRIPTIONS[p.value]}>
                        {p.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {/* Description box */}
                {POLICY_DESCRIPTIONS[policy] && (
                  <div className="mt-1 rounded-lg border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                    <strong>What this does:</strong> {POLICY_DESCRIPTIONS[policy]}
                  </div>
                )}
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground">Preferred library</label>
                <Select value={prefId} onValueChange={setPrefId}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {libs.map((l) => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground">Move target</label>
                <Select value={targetId} onValueChange={setTargetId}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {libs.map((l) => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {violations.length > 0 && (
              <div className="max-h-40 space-y-1 overflow-auto rounded-lg border bg-muted/30 p-2 font-mono text-xs">
                {violations.slice(0, 120).map((v, i) => (
                  <div key={i} className="truncate border-b border-border/40 py-0.5">
                    {v.title || v.path} — {v.libraries ? v.libraries.join(', ') : 'duplicate'}
                  </div>
                ))}
              </div>
            )}
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={running} onClick={() => resolveExcl(true)}>
                <RefreshCw className="size-3.5" /> Resolve dry run
              </Button>
              <Button size="sm" disabled={running} onClick={() => setExclApply(true)}>
                <Play className="size-3.5" /> Apply
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* -------- NEW: Import folder card -------- */}
        <Card>
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2"><FolderPlus className="size-4 text-primary" /> Import folder</CardTitle>
            <CardDescription>Move or copy all audio files from a source folder into a library</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">Source folder</label>
              <Input
                value={importSource}
                onChange={(e) => setImportSource(e.target.value)}
                placeholder="C:\Downloads\New Music"
                className="font-mono text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">Destination library</label>
              <Select value={importDestLib} onValueChange={setImportDestLib}>
                <SelectTrigger className="w-full"><SelectValue placeholder="Select a library" /></SelectTrigger>
                <SelectContent>
                  {libs.map((l) => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={importPreserve} onChange={(e) => setImportPreserve(e.target.checked)} />
                Preserve folder structure
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={importMove} onChange={(e) => setImportMove(e.target.checked)} />
                Move (instead of copy)
              </label>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={running || !importSource || !importDestLib} onClick={runImport}>
                <RefreshCw className="size-3.5" /> Import
              </Button>
            </div>
          </CardContent>
        </Card>
        {/* -------- END NEW -------- */}

        {/* Export assets */}
        <Card>
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2"><ListMusic className="size-4 text-primary" /> Export assets</CardTitle>
            <CardDescription>Covers, playlists and library report</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between rounded-lg border bg-muted/30 px-3 py-2 text-sm">
              <span className="flex items-center gap-2"><ImageDown className="size-4 text-muted-foreground" /> Extract album covers</span>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" disabled={running || !libId} onClick={() => covers(false)}>Extract</Button>
                <Button variant="outline" size="sm" disabled={running || !libId} onClick={() => covers(true)}>Rebuild</Button>
              </div>
            </div>
            <div className="flex items-center justify-between rounded-lg border bg-muted/30 px-3 py-2 text-sm">
              <span className="flex items-center gap-2"><ListMusic className="size-4 text-muted-foreground" /> Generate playlists</span>
              <Button variant="outline" size="sm" disabled={running || !libId} onClick={playlists}>Generate</Button>
            </div>
            <div className="flex items-center justify-between rounded-lg border bg-muted/30 px-3 py-2 text-sm">
              <span className="flex items-center gap-2"><FileText className="size-4 text-muted-foreground" /> Generate library report</span>
              <Button variant="outline" size="sm" disabled={running || !libId} onClick={generateReport}>Report</Button>
            </div>
            {coverRes && (
              <div className="text-xs text-muted-foreground">{coverRes.created} covers written{coverRes.errors?.length ? `, ${coverRes.errors.length} errors` : ''} · {libName(libId)}</div>
            )}
            {playlistRes && (
              <div className="text-xs text-muted-foreground">{playlistRes.created} playlists written · {libName(libId)}</div>
            )}
          </CardContent>
        </Card>
      </div>


      {report && (
        <Modal open onClose={() => setReport(null)} title="Library report" width="max-w-4xl">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Badge>{report.total.tracks} tracks</Badge>
            <Badge variant="secondary">{report.total.artists} artists</Badge>
            <Badge variant="secondary">{report.total.albums} albums</Badge>
            <Badge variant="secondary">{fmtBytes(report.total.size)}</Badge>
          </div>
          <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-lg border bg-muted/40 p-3 font-mono text-xs">{report.text || report.json_text || JSON.stringify(report.json, null, 2)}</pre>
          <div className="mt-3 flex justify-end">
            <Button variant="outline" onClick={() => {
              const blob = new Blob([report.json_text || ''], { type: 'application/json' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a'); a.href = url; a.download = 'glacier-report.json'; a.click();
              URL.revokeObjectURL(url);
            }}>Download JSON</Button>
          </div>
        </Modal>
      )}

      <Confirm
        open={orgApply}
        title="Apply folder organization?"
        message={`This will move ${orgPlan.length || 'files'} according to the configured patterns in "${libName(libId)}".`}
        onCancel={() => setOrgApply(false)}
        onConfirm={() => organize(false)}
        confirmLabel="Apply"
      />
      <Confirm
        open={exclApply}
        title="Apply exclusivity resolution?"
        message="Glacier will act on violations according to the selected policy. Consider a dry run first."
        onCancel={() => setExclApply(false)}
        onConfirm={() => resolveExcl(false)}
        confirmLabel="Apply"
      />
    </div>
  );
}