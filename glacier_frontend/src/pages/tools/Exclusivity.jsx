import { useState, useEffect } from 'react';
import { ShieldAlert, UserCheck, RefreshCw, Play } from 'lucide-react';
import { api } from '../../api.js';
import { useJob } from '../../useJob.js';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardAction } from '@/components/ui/card.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select.jsx';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs.jsx';
import { Empty } from '../../components/PageHeader.jsx';
import { Confirm } from '../../components/dialog-helpers.jsx';
import { toast } from '../../toast.jsx';

const POLICIES = [
  { value: 'report_only', label: 'Report only (no changes)' },
  { value: 'keep_best_quality', label: 'Keep best quality copy' },
  { value: 'keep_preferred_library', label: 'Keep preferred library' },
  { value: 'keep_newest', label: 'Keep newest copy' },
  { value: 'move_to_library', label: 'Move extras to library' },
  { value: 'quarantine', label: 'Move extras to quarantine' },
];

const POLICY_DESCRIPTIONS = {
  report_only: "Scans for duplicates but makes zero changes to your files. Just shows you the list of violations.",
  keep_best_quality: "Keeps the highest quality file (FLAC > ALAC > MP3) in the preferred library if set, otherwise keeps the best quality file. Moves lower quality duplicates to quarantine.",
  keep_preferred_library: "Keeps all copies inside your Preferred Library. Moves every duplicate from other libraries INTO that Preferred Library. Best for consolidation.",
  keep_newest: "Keeps the file with the latest modification date. Moves the older duplicates to quarantine.",
  move_to_library: "Keeps the copy already in the Target Library. Moves all other duplicates (extras) INTO that Target Library. (Requires a Target Library.)",
  quarantine: "Moves EVERY duplicate file out of your libraries into a quarantine folder (~/.glacier_quarantine). Use this to completely remove duplicate copies from all libraries.",
};

const ARTIST_POLICIES = [
  { value: "report_only", label: "Report only" },
  { value: "keep_preferred_library", label: "Keep preferred library" },
];
const ARTIST_POLICY_DESCRIPTIONS = {
  report_only: "Scans for artists that appear in more than one library, but makes zero changes. Just shows you the list.",
  keep_preferred_library: "Keeps all tracks of the artist in your Preferred Library. Moves every track from other libraries INTO that Preferred Library. Best for consolidating an artist into one library.",
};

export default function Exclusivity() {
  const [libs, setLibs] = useState([]);
  const [libId, setLibId] = useState('');
  const { running, run } = useJob();

  // Library exclusivity
  const [violations, setViolations] = useState([]);
  const [policy, setPolicy] = useState('report_only');
  const [prefId, setPrefId] = useState('');
  const [targetId, setTargetId] = useState('');
  const [exclPlans, setExclPlans] = useState([]);
  const [exclApply, setExclApply] = useState(false);

  // Artist exclusivity
  const [artistPolicy, setArtistPolicy] = useState("report_only");
  const [artistPref, setArtistPref] = useState("");
  const [artistGroups, setArtistGroups] = useState([]);
  const [artistPlans, setArtistPlans] = useState([]);
  const [artistApply, setArtistApply] = useState(false);

  useEffect(() => {
    api.settings().then((s) => {
      const l = s.libraries || [];
      setLibs(l);
      if (l.length) {
        setLibId(l[0].id);
        setPrefId(l[0].id);
        setTargetId(l[0].id);
        setArtistPref(l[0].id);
      }
    }).catch(() => {});
  }, []);

  const libName = (id) => (libs.find((l) => l.id === id) || {}).name || '—';

  // ---- Library Exclusivity ----
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
      if (res?.ok) { setExclPlans(res.plan || []); toast.success(`${res.count} file(s) would move`); }
      else toast.error(res.error || 'Dry-run failed');
    } else if (res?.ok) {
      toast.success(`${res.acted} files processed, ${res.skipped} skipped`); setExclApply(false); setExclPlans([]);
    } else toast.error(res.error || 'Apply failed');
  };

  // ---- Artist Exclusivity ----
  const scanArtists = async () => {
    const res = await run('artist-exclusivity', {});
    if (res?.ok) { setArtistGroups(res.groups || []); toast.success(`${res.count} artist violation(s)`); }
    else toast.error(res.error || "Scan failed");
  };
  const resolveArtists = async (dry) => {
    const res = await run('resolve-artist-exclusivity', {
      policy: artistPolicy, preferred_library_id: artistPref,
      dry_run: dry, confirm: !dry,
    });
    if (dry) {
      if (res?.ok) { setArtistPlans(res.plan || []); toast.success(`${res.count} file(s) would move`); }
      else toast.error(res.error || "Dry-run failed");
    } else if (res?.ok) {
      toast.success(`${res.acted} moved, ${res.skipped} skipped`);
      setArtistApply(false); setArtistPlans([]);
    } else toast.error(res.error || "Apply failed");
  };

  return (
    <div>
      <Tabs defaultValue="library" className="w-full">
        <TabsList className="grid w-80 grid-cols-2">
          <TabsTrigger value="library">Library</TabsTrigger>
          <TabsTrigger value="artist">Artist</TabsTrigger>
        </TabsList>

        {/* Library Exclusivity */}
        <TabsContent value="library">
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
                  {violations.slice(0, 120).map((v, i) => {
                    const tr = (v.tracks || [])[0];
                    const label = tr?.tags
                      ? `${tr.tags.artist || '?'} – ${tr.tags.title || '?'}`
                      : v.identity;
                    return (
                      <div key={i} className="truncate border-b border-border/40 py-0.5">
                        {label} — in {v.libraries?.length || 0} libraries ({v.count} copies)
                      </div>
                    );
                  })}
                </div>
              )}
              {exclPlans.length > 0 && (
                <div className="max-h-40 space-y-1 overflow-auto rounded-lg border bg-muted/30 p-2 font-mono text-xs">
                  {exclPlans.slice(0, 120).map((p, i) => (
                    <div key={i} className="truncate border-b border-border/40 py-0.5">
                      {p.source} → {p.destination}
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
          <Confirm
            open={exclApply}
            title="Apply exclusivity resolution?"
            message="Glacier will act on violations according to the selected policy. Consider a dry run first."
            onCancel={() => setExclApply(false)}
            onConfirm={() => resolveExcl(false)}
            confirmLabel="Apply"
          />
        </TabsContent>

        {/* Artist Exclusivity */}
        <TabsContent value="artist">
          <Card>
            <CardHeader className="border-b">
              <CardTitle className="flex items-center gap-2"><UserCheck className="size-4 text-primary" /> Artist exclusivity</CardTitle>
              <CardDescription>Artists that appear in more than one library (one library per artist)</CardDescription>
              <CardAction>
                <Button variant="outline" size="sm" disabled={running} onClick={scanArtists}>
                  <RefreshCw className="size-3.5" /> Scan
                </Button>
              </CardAction>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <label className="text-xs text-muted-foreground">Resolution policy</label>
                  <Select value={artistPolicy} onValueChange={setArtistPolicy}>
                    <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {ARTIST_POLICIES.map((p) => (
                        <SelectItem key={p.value} value={p.value} title={ARTIST_POLICY_DESCRIPTIONS[p.value]}>
                          {p.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {ARTIST_POLICY_DESCRIPTIONS[artistPolicy] && (
                    <div className="mt-1 rounded-lg border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                      <strong>What this does:</strong> {ARTIST_POLICY_DESCRIPTIONS[artistPolicy]}
                    </div>
                  )}
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs text-muted-foreground">Preferred library</label>
                  <Select value={artistPref} onValueChange={setArtistPref}>
                    <SelectTrigger className="w-full"><SelectValue placeholder="None" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="">None</SelectItem>
                      {libs.map((l) => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {artistGroups.length > 0 ? (
                <div className="max-h-40 space-y-1 overflow-auto rounded-lg border bg-muted/30 p-2 text-xs">
                  {artistGroups.map((g) => (
                    <div key={g.artist} className="border-b border-border/40 py-0.5">
                      <span className="font-medium">{g.display}</span>
                      <span className="text-muted-foreground"> - {g.libraries.map((l) => libName(l.library_id) + " (" + l.count + ")").join(", ")}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="rounded-lg border bg-muted/30 p-3 text-xs text-muted-foreground">
                  No artist violations found. Make sure:
                  <ul className="mt-1 list-inside list-disc">
                    <li>You have at least two libraries with music.</li>
                    <li>Your libraries are <strong>enabled</strong> (check the Libraries page).</li>
                    <li>The artists are tagged consistently (case and punctuation are ignored).</li>
                    <li>You have scanned your libraries (Dashboard → Scan).</li>
                  </ul>
                </div>
              )}

              {artistPlans.length > 0 && (
                <div className="max-h-40 space-y-1 overflow-auto rounded-lg border bg-muted/30 p-2 font-mono text-xs">
                  {artistPlans.slice(0, 120).map((p, i) => (
                    <div key={i} className="truncate border-b border-border/40 py-0.5">
                      {p.source} → {p.destination}
                    </div>
                  ))}
                </div>
              )}

              <div className="flex gap-2">
                <Button variant="outline" size="sm" disabled={running} onClick={() => resolveArtists(true)}>
                  <RefreshCw className="size-3.5" /> Resolve dry run
                </Button>
                <Button size="sm" disabled={running} onClick={() => setArtistApply(true)}>
                  <Play className="size-3.5" /> Apply
                </Button>
              </div>
            </CardContent>
          </Card>
          <Confirm
            open={artistApply}
            title="Apply artist exclusivity resolution?"
            message="Glacier will move the artist's files out of all non-preferred libraries, leaving the artist in one library only."
            onCancel={() => setArtistApply(false)}
            onConfirm={() => resolveArtists(false)}
            confirmLabel="Apply"
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}