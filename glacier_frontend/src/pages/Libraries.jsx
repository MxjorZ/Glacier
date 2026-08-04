import { useEffect, useState } from "react";
import { Plus, RefreshCw, Pencil, Trash2, Folder, HardDrive, UserCheck, MoveRight, CheckCircle2, CircleOff, AlertTriangle, Loader2, ServerOff } from "lucide-react";
import { api, fmtBytes, fmtDate } from "../api.js";
import FileExplorer from "../FileExplorer.jsx";
import { useJob } from "../useJob.js";
import { Card, CardHeader, CardTitle, CardContent, CardAction, CardDescription } from "@/components/ui/card.jsx";
import { Button } from "@/components/ui/button.jsx";
import { Input } from "@/components/ui/input.jsx";
import { Checkbox } from "@/components/ui/checkbox.jsx";
import { Badge } from "@/components/ui/badge.jsx";
import { Switch } from "@/components/ui/switch.jsx";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select.jsx";

import { PageHeader, Empty } from "../components/PageHeader.jsx";
import { Modal, Confirm } from "../components/dialog-helpers.jsx";
import { toast } from "../toast.jsx";

export default function Libraries() {
  // ---- Server connection + load state ----
  const [conn, setConn] = useState("loading"); // 'loading' | 'ok' | 'error'
  const [connError, setConnError] = useState("");
  const [loadBusy, setLoadBusy] = useState(false);
  const [libs, setLibs] = useState([]);
  const [picker, setPicker] = useState(false);
  const [newPath, setNewPath] = useState("");
  const [rename, setRename] = useState(null);
  const [renameVal, setRenameVal] = useState("");
  const [removeId, setRemoveId] = useState(null);

  // ---- Artist exclusivity (Stage 2) ----
  const ARTIST_POLICIES = [
    { value: "report_only", label: "Report only" },
    { value: "keep_preferred_library", label: "Keep preferred library" },
  ];
  const [artistPolicy, setArtistPolicy] = useState("report_only");
  const [artistPref, setArtistPref] = useState("");
  const [artistGroups, setArtistGroups] = useState([]);
  const [artistPlans, setArtistPlans] = useState([]);
  const [artistApply, setArtistApply] = useState(false);

  const scanArtists = async () => {
    const res = await api.artistExclusivity();
    if (res?.ok) { setArtistGroups(res.groups || []); toast.success(`${res.count} artist violation(s)`); }
    else toast.error(res.error || "Scan failed");
  };
  const resolveArtists = async (dry) => {
    const res = await api.resolveArtistExclusivity({
      policy: artistPolicy, preferred_library_id: artistPref,
      dry_run: dry, confirm: !dry,
    });
    if (dry) {
      if (res?.ok) { setArtistPlans(res.plans || []); toast.success(`${res.count} artist(s) would be moved`); }
      else toast.error(res.error || "Dry-run failed");
    } else if (res?.ok) {
      toast.success(`${res.acted} moved, ${res.skipped} skipped`);
      setArtistApply(false); setArtistPlans([]); refresh();
    } else toast.error(res.error || "Apply failed");
  };

  // ---- Create library & move (Stage 2) ----
  const [extOpen, setExtOpen] = useState(false);
  const [extName, setExtName] = useState("");
  const [extPath, setExtPath] = useState("");
  const [extScript, setExtScript] = useState("");
  const [extGenre, setExtGenre] = useState("");
  const [extArtists, setExtArtists] = useState("");
  const [extPathRegex, setExtPathRegex] = useState("");
  const [extSources, setExtSources] = useState([]);
  const [extPreview, setExtPreview] = useState(null);
  const [extApply, setExtApply] = useState(false);

  const buildFilters = () => ({
    script: extScript || undefined,
    genre_contains: extGenre || undefined,
    artists: extArtists.split(",").map((s) => s.trim()).filter(Boolean),
    path_regex: extPathRegex || undefined,
  });
  const toggleSource = (id) =>
    setExtSources((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const dryExtract = async () => {
    if (!extPath) return toast.error("Destination path is required");
    if (extSources.length === 0) return toast.error("Select at least one source library");
    const res = await api.extractMove({
      name: extName, path: extPath, filters: buildFilters(),
      source_library_ids: extSources, dry_run: true,
    });
    if (res?.ok) { setExtPreview(res); toast.success(`${res.count} file(s) would move (${fmtBytes(res.bytes)})`); }
    else toast.error(res.error || "Dry-run failed");
  };
  const applyExtract = async () => {
    const res = await api.extractMove({
      name: extName, path: extPath, filters: buildFilters(),
      source_library_ids: extSources, dry_run: false, confirm: true,
    });
    if (res?.ok) {
      toast.success(`Created "${res.library?.name}" and moved ${res.moved} files`);
      setExtOpen(false); setExtApply(false); setExtPreview(null); refresh();
    } else toast.error(res.error || "Apply failed");
  };

  const libName = (id) => (libs.find((l) => l.id === id) || {}).name || id;

  const { running, run } = useJob();

  const refresh = async (silent = false) => {
    if (!silent) setConn("loading");
    setLoadBusy(true);
    try {
      const res = await api.libraryStatus();
      setLibs(res?.libraries || []);
      setConn("ok");
      setConnError("");
    } catch (e) {
      setConn("error");
      setConnError(e?.message || "Could not reach the Glacier server");
      setLibs([]);
    } finally {
      setLoadBusy(false);
    }
  };
  useEffect(() => { refresh(); }, []);

  // Enable / disable a library. Disabled libraries are skipped by "all-library"
  // scans/operations but keep their files on disk.
  const toggleEnabled = async (l) => {
    const next = !(l.enabled ?? true);
    setLibs((ps) => ps.map((x) => (x.id === l.id ? { ...x, enabled: next } : x)));
    try {
      await api.setLibraryEnabled(l.id, next);
      toast.success(`${l.name} ${next ? "enabled" : "disabled"}`);
    } catch (e) {
      toast.error(e.message || "Could not update library");
      setLibs((ps) => ps.map((x) => (x.id === l.id ? { ...x, enabled: !next } : x)));
    }
  };

  const pathName = (p) => p.split(/[\\/]/).filter(Boolean).pop() || p;

  const add = async () => {
    try {
      await api.addLibrary(pathName(newPath), newPath);
      toast.success("Library added");
      setNewPath("");
      setPicker(false);
      refresh();
    } catch (e) {
      toast.error(e.message);
      // If the folder is already a library, stop prompting to re-add it and
      // just show the current, up-to-date list.
      if (/already exists/i.test(e.message || "")) {
        setNewPath("");
        setPicker(false);
        refresh();
      }
    }
  };

  const renameSubmit = async () => {
    if (!rename) return;
    try {
      await api.renameLibrary(rename.id, renameVal);
      toast.success("Renamed");
      setRename(null);
      refresh();
    } catch (e) {
      toast.error(e.message);
    }
  };

  const scan = async (id) => {
    const res = await run("analyze", { library_ids: [id] });
    if (res?.ok) toast.success("Library scanned");
    else if (res?.error) toast.error(res.error);
    refresh();
  };

  const doRemove = async () => {
    if (!removeId) return;
    try {
      await api.removeLibrary(removeId);
      toast.success("Library removed (files untouched)");
      setRemoveId(null);
      refresh();
    } catch (e) {
      toast.error(e.message);
    }
  };

  return (
    <div>
      <PageHeader
        title="Libraries"
        description="Managed music folders. Glacier enforces that tracks exist exclusively in one library."
      >
        <Button variant="outline" onClick={() => refresh()} disabled={loadBusy}>
          <RefreshCw className={loadBusy ? "size-4 animate-spin" : "size-4"} /> Load libraries
        </Button>
        <Button onClick={() => setPicker(true)}>
          <Plus className="size-4" /> Add library
        </Button>
      </PageHeader>

      {/* Server connection state */}
      {conn === "loading" && (
        <Card className="mb-4"><CardContent className="flex items-center gap-3 pt-4 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin text-primary" /> Loading libraries from the server…
        </CardContent></Card>
      )}

      {conn === "error" && (
        <Card className="mb-4 border-warn/60"><CardContent className="flex flex-wrap items-center gap-3 pt-4 text-sm">
          <ServerOff className="size-4 text-warn" />
          <span>
            <span className="font-medium text-warn">Cannot reach the Glacier server.</span>{" "}
            <span className="text-muted-foreground">{connError || "The backend may be stopped, or the page was opened without the server running."}</span>
          </span>
          <Button variant="outline" size="sm" className="ml-auto" disabled={loadBusy} onClick={() => refresh()}>
            <RefreshCw className={loadBusy ? "size-3.5 animate-spin" : "size-3.5"} /> Retry
          </Button>
        </CardContent></Card>
      )}

      {conn === "ok" && (
        libs.length === 0 ? (
          <Card><CardContent className="pt-6"><Empty text="No libraries configured yet. Add a music folder to begin." /></CardContent></Card>
        ) : (
          <>
            <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="secondary">{libs.filter((l) => l.enabled ?? true).length} active</Badge>
              <Badge variant="secondary">{libs.filter((l) => (l.enabled ?? true) === false).length} disabled</Badge>
              <span>Only active libraries are included in “all-library” scans and operations.</span>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
          {libs.map((l) => {
            const dir = l.scan;
            const enabled = l.enabled ?? true;
            return (
              <Card key={l.id} className={enabled ? "" : "opacity-60"}><CardHeader className="border-b">
                <CardTitle className="flex items-center gap-2">
                  <Folder className="size-4 text-primary" />
                  {l.name}
                  {enabled
                    ? <Badge variant="success"><CheckCircle2 /> Active</Badge>
                    : <Badge variant="secondary"><CircleOff /> Disabled</Badge>}
                </CardTitle>
                <CardAction>
                  <div className="flex items-center gap-2">
                    <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <Switch checked={enabled} onCheckedChange={() => toggleEnabled(l)} aria-label={`Enable ${l.name}`} />
                      {enabled ? "on" : "off"}
                    </label>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => { setRename({ id: l.id, name: l.name }); setRenameVal(l.name); }}
                    >
                      <Pencil className="size-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="text-destructive hover:text-destructive"
                      onClick={() => setRemoveId(l.id)}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                </CardAction>
              </CardHeader>
                <CardContent className="space-y-3 pt-4 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Path</span>
                    <span className="font-mono text-xs flex items-center gap-1.5">
                      {l.exists
                        ? <CheckCircle2 className="size-3.5 text-ok" />
                        : <AlertTriangle className="size-3.5 text-warn" />}
                      {l.path}
                    </span>
                  </div>
                  {!l.exists && (
                    <div className="rounded-md border border-warn/50 bg-warn/10 px-2 py-1 text-xs text-warn">
                      This path is not reachable on disk — check the mount / drive before scanning.
                    </div>
                  )}
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Tracks</span>
                    <span className="font-mono font-medium">{dir ? dir.tracks : "—"}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Size</span>
                    <span className="font-mono">{dir ? fmtBytes(dir.size ?? 0) : "—"}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Last scan</span>
                    <span className="font-mono text-xs text-muted-foreground">{dir ? fmtDate(dir.at) : "never"}</span>
                  </div>
                  <div className="pt-2">
                    <Button variant="outline" size="sm" disabled={running || !enabled} onClick={() => scan(l.id)}>
                      <RefreshCw className={running ? "size-3.5 animate-spin" : "size-3.5"} /> Rescan
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
          </div>
          </>
        )
      )}

      {/* Artist exclusivity (Stage 2) */}
      <Card className="mt-4">
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
                  {ARTIST_POLICIES.map((p) => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
                </SelectContent>
              </Select>
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

          {artistGroups.length > 0 && (
            <div className="max-h-40 space-y-1 overflow-auto rounded-lg border bg-muted/30 p-2 text-xs">
              {artistGroups.map((g) => (
                <div key={g.artist} className="border-b border-border/40 py-0.5">
                  <span className="font-medium">{g.display}</span>
                  <span className="text-muted-foreground"> - {g.libraries.map((l) => libName(l.library_id) + " (" + l.count + ")").join(", ")}</span>
                </div>
              ))}
            </div>
          )}

          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={running} onClick={() => resolveArtists(true)}>
              <RefreshCw className="size-3.5" /> Resolve dry run
            </Button>
            <Button size="sm" disabled={running} onClick={() => setArtistApply(true)}>Apply</Button>
          </div>
        </CardContent>
      </Card>

      {/* Create library & move (Stage 2) */}
      <Card className="mt-4">
        <CardHeader className="border-b">
          <CardTitle className="flex items-center gap-2"><MoveRight className="size-4 text-primary" /> Create library &amp; move</CardTitle>
          <CardDescription>Split matching files into a brand-new library in one confirmed action</CardDescription>
          <CardAction>
            <Button size="sm" onClick={() => setExtOpen(true)}><Plus className="size-4" /> New...</Button>
          </CardAction>
        </CardHeader>
        <CardContent>
          <Empty text="Create a library (e.g. a language/script split) with filters, preview a dry run, then move matching files in one action." />
        </CardContent>
      </Card>

      {/* Create library & move — wizard modal */}
      <Modal open={extOpen} onClose={() => setExtOpen(false)} title="Create library & move" width="max-w-3xl">
        <div className="space-y-4 pt-2">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">New library name</label>
              <Input value={extName} onChange={(e) => setExtName(e.target.value)} placeholder="e.g. Hebrew" />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">Destination path (folder will be created)</label>
              <Input value={extPath} onChange={(e) => setExtPath(e.target.value)} placeholder="C:\Music\Hebrew" className="font-mono text-xs" />
            </div>
          </div>

          <div className="rounded-lg border bg-muted/30 p-3">
            <p className="mb-2 text-xs font-medium text-muted-foreground">Filters (all conditions must match)</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground">Script heuristic</label>
                <Select value={extScript} onValueChange={setExtScript}>
                  <SelectTrigger className="w-full"><SelectValue placeholder="Any" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">Any</SelectItem>
                    <SelectItem value="hebrew">Hebrew</SelectItem>
                    <SelectItem value="cyrillic">Cyrillic</SelectItem>
                    <SelectItem value="arabic">Arabic</SelectItem>
                    <SelectItem value="latin">Latin</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground">Genre contains</label>
                <Input value={extGenre} onChange={(e) => setExtGenre(e.target.value)} placeholder="e.g. Folk" />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground">Artists (comma separated)</label>
                <Input value={extArtists} onChange={(e) => setExtArtists(e.target.value)} placeholder="Artist A, Artist B" />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground">Path regex</label>
                <Input value={extPathRegex} onChange={(e) => setExtPathRegex(e.target.value)} placeholder="e.g. \\.flac$" className="font-mono text-xs" />
              </div>
            </div>
          </div>

          <div className="space-y-1.5">
            <p className="text-xs font-medium text-muted-foreground">Source libraries to pull from</p>
            <div className="flex flex-wrap gap-2">
              {libs.map((l) => (
                <label key={l.id} className="flex items-center gap-2 rounded-lg border bg-muted/30 px-3 py-1.5 text-sm">
                  <Checkbox checked={extSources.includes(l.id)} onCheckedChange={() => toggleSource(l.id)} />
                  {l.name}
                </label>
              ))}
            </div>
          </div>

          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={dryExtract}><RefreshCw className="size-4" /> Dry run</Button>
            <Button disabled={!extPreview} onClick={() => setExtApply(true)}><MoveRight className="size-4" /> Move &amp; create</Button>
          </div>

          {extPreview && (
            <div className="space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground">
                Dry-run: {extPreview.count} file(s) · {fmtBytes(extPreview.bytes)}
              </p>
              <div className="max-h-48 space-y-1 overflow-auto rounded-lg border bg-muted/40 p-2 font-mono text-xs">
                {(extPreview.samples || []).map((s, i) => (
                  <div key={i} className="border-b border-border/40 py-0.5">
                    <span className="text-muted-foreground">{s.source_library_name}:</span> {s.source}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </Modal>

      <Confirm
        open={extApply}
        title="Create library & move files?"
        message="This will create the new library folder and MOVE (not copy) the matched files into it. The library will be added to Glacier."
        onCancel={() => setExtApply(false)}
        onConfirm={applyExtract}
        confirmLabel="Create & move"
      />
      <Confirm
        open={artistApply}
        title="Apply artist exclusivity resolution?"
        message="Glacier will move the artist's files out of all non-preferred libraries, leaving the artist in one library only."
        onCancel={() => setArtistApply(false)}
        onConfirm={() => resolveArtists(false)}
        confirmLabel="Apply"
      />

      <FileExplorer open={picker} onClose={() => setPicker(false)} onSelect={(p) => { setNewPath(p); setPicker(false); }} />

      <Modal open={newPath !== ""} onClose={() => setNewPath("")} title="Confirm Library Path" width="max-w-md">
        <div className="space-y-4 pt-2">
          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground">Selected Path</label>
            <Input value={newPath} readOnly className="font-mono text-xs" />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setNewPath("")}>Cancel</Button>
            <Button onClick={add}>Add Library</Button>
          </div>
        </div>
      </Modal>

      <Modal open={rename !== null} onClose={() => setRename(null)} title="Rename Library" width="max-w-sm">
        <div className="space-y-4 pt-2">
          <Input value={renameVal} onChange={(e) => setRenameVal(e.target.value)} placeholder="Library name" />
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setRename(null)}>Cancel</Button>
            <Button onClick={renameSubmit}>Save</Button>
          </div>
        </div>
      </Modal>

      <Confirm
        open={removeId !== null}
        onCancel={() => setRemoveId(null)}
        onConfirm={doRemove}
        title="Remove Library?"
        message="This will remove the library from Glacier. Your music files on disk will NOT be deleted."
        confirmLabel="Remove"
        danger
      />
    </div>
  );
}
