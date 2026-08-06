import { useEffect, useState } from 'react';
import { Save, Server, SlidersHorizontal, FolderTree, ShieldAlert, Radio, Palette, Volume2, Loader2, CheckCircle2, XCircle, Sparkles } from 'lucide-react';
import { api } from '../api.js';
import { applySettingsTheme, applyAnimations, ANIM_PRESETS, ACCENTS, customAccentVars, parseAccentColor } from '../lib/themes.js';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardAction } from '@/components/ui/card.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Input, Textarea } from '@/components/ui/input.jsx';
import { Switch } from '@/components/ui/switch.jsx';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select.jsx';
import { PageHeader } from '../components/PageHeader.jsx';
import { toast } from '../toast.jsx';
import { cn } from '@/lib/utils.js';

const ACCENT_SWATCH = {
  cyan: '#22d3ee', sky: '#38bdf8', teal: '#2dd4bf', blue: '#3b82f6',
  purple: '#a855f7', green: '#4ade80', orange: '#fb923c', red: '#f87171', yellow: '#facc15',
};
const IDENTITIES = [
  { value: 'auto', label: 'Auto (first match)' },
  { value: 'isrc', label: 'ISRC' },
  { value: 'artist_title_album', label: 'Artist + Title + Album' },
  { value: 'artist_title', label: 'Artist + Title' },
];
const POLICIES = [
  { value: 'report_only', label: 'Report only' },
  { value: 'keep_best_quality', label: 'Keep best quality' },
  { value: 'keep_preferred_library', label: 'Keep preferred library' },
  { value: 'keep_newest', label: 'Keep newest' },
  { value: 'move_to_library', label: 'Move to library' },
  { value: 'quarantine', label: 'Quarantine' },
];

export default function Settings({ settings, onSettings }) {
  const [s, setS] = useState(settings || {});
  const [plexTest, setPlexTest] = useState(null);   // null | {ok,..} | {error}
  const [plextesting, setPlexTesting] = useState(false);

  useEffect(() => { if (settings) setS(settings); }, [settings]);

  // Live animation preview as the user tweaks the Animations card (Stage 4 #16).
  useEffect(() => { applyAnimations(s); }, [s.animations]);

  const testPlex = async () => {
    setPlexTesting(true);
    setPlexTest(null);
    try {
      const res = await api.plex.test(s.plex?.url, s.plex?.token, s.plex?.music_section);
      setPlexTest(res.ok ? res : { error: res.error || 'Connection failed' });
    } catch (e) {
      setPlexTest({ error: e.message });
    } finally {
      setPlexTesting(false);
    }
  };

  const set = (key, value) => setS((prev) => ({ ...prev, [key]: value }));
  const setNested = (root, key, value) =>
    setS((prev) => ({ ...prev, [root]: { ...(prev[root] || {}), [key]: value } }));

  const libs = s.libraries || [];
  const save = async () => {
    try {
      const res = await api.saveSettings({
        server: s.server,
        extensions: s.extensions,
        excluded_folders: s.excluded_folders,
        folder_pattern: s.folder_pattern,
        naming_pattern: s.naming_pattern,
        dup_priority: s.dup_priority,
        exclusivity: s.exclusivity,
        exclusivity_artist_policy: s.exclusivity_artist_policy,
        artist_exclusivity_exceptions: s.artist_exclusivity_exceptions,
        preferred_library_id: s.preferred_library_id,
        backup_before_move: s.backup_before_move,
        plex: s.plex,
        sound_on_complete: s.sound_on_complete,
        sound_on_error: s.sound_on_error,
        sound_asset_complete: s.sound_asset_complete,
        theme: s.theme,
        animations: s.animations,
      });
      if (res?.settings) { onSettings(res.settings); applySettingsTheme(res.settings); }
      toast.success('Settings saved');
    } catch (e) {
      toast.error(e.message);
    }
  };

  const extText = (s.extensions || []).join(', ');
  const exclText = (s.excluded_folders || []).join(', ');

  return (
    <div>
      <PageHeader title="Settings" description="Configure server, scanning, organization and integrations.">
        <Button onClick={save}><Save className="size-4" /> Save changes</Button>
      </PageHeader>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Server */}
        <Card>
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2"><Server className="size-4 text-primary" /> Server</CardTitle>
            <CardDescription>Bind address and port</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">Host</label>
              <Input value={s.server?.host || ''} onChange={(e) => setNested('server', 'host', e.target.value)} placeholder="0.0.0.0" />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">Port</label>
              <Input type="number" value={s.server?.port || 5050} onChange={(e) => setNested('server', 'port', Number(e.target.value))} />
            </div>
          </CardContent>
        </Card>

        {/* Formats */}
        <Card>
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2"><SlidersHorizontal className="size-4 text-primary" /> Formats</CardTitle>
            <CardDescription>Scanned extensions and duplicate preference</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">Audio extensions (comma separated)</label>
              <Input value={extText}
                onChange={(e) => set('extensions', e.target.value.split(',').map((x) => x.trim()).filter(Boolean))} />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">Preferred format for duplicates</label>
              <Select value={s.dup_priority || 'flac'} onValueChange={(v) => set('dup_priority', v)}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {['flac', 'wav', 'alac', 'm4a', 'ogg', 'opus', 'wma', 'mp3', 'aac'].map((f) => (
                    <SelectItem key={f} value={f}>{f}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        {/* Scanning */}
        <Card>
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2"><FolderTree className="size-4 text-primary" /> Scanning</CardTitle>
            <CardDescription>Excluded folders and move safety. (Folder/naming templates live in Tools → Organize.)</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">Excluded folders (comma separated)</label>
              <Input value={exclText}
                onChange={(e) => set('excluded_folders', e.target.value.split(',').map((x) => x.trim()).filter(Boolean))} />
            </div>
            <div className="flex items-center justify-between rounded-lg border bg-muted/30 px-3 py-2">
              <div>
                <span className="text-sm">Run quick scan on app startup</span>
                <p className="text-xs text-muted-foreground">Automatically scans for changes when the app loads</p>
              </div>
              <Switch
                checked={!!s.startup_scan_enabled}
                onCheckedChange={(v) => set('startup_scan_enabled', v)}
              />
            </div>
          </CardContent>
        </Card>

        {/* Exclusivity */}
        <Card>
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2"><ShieldAlert className="size-4 text-primary" /> Exclusivity</CardTitle>
            <CardDescription>Cross-library identity and default policy</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">Identity match</label>
              <Select value={s.exclusivity?.identity || 'auto'} onValueChange={(v) => setNested('exclusivity', 'identity', v)}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {IDENTITIES.map((i) => <SelectItem key={i.value} value={i.value}>{i.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">Default resolution policy</label>
              <Select value={s.exclusivity?.default_policy || 'report_only'} onValueChange={(v) => setNested('exclusivity', 'default_policy', v)}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {POLICIES.map((p) => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">Primary Music Library</label>
              <Select value={s.exclusivity?.preferred_library_id || ''} onValueChange={(v) => setNested('exclusivity', 'preferred_library_id', v)}>
                <SelectTrigger className="w-full"><SelectValue placeholder="None" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="">None</SelectItem>
                  {libs.map((l) => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
                </SelectContent>
              </Select>
              <p className="text-[11px] text-muted-foreground">Your main collection. When resolving duplicates that appear in more than one library, Glacier prefers to keep the copy here.</p>
            </div>
          </CardContent>
        </Card>

        {/* Plex */}
        <Card>
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2"><Radio className="size-4 text-primary" /> Plex</CardTitle>
            <CardDescription>Media server connection</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">Server URL</label>
              <Input value={s.plex?.url || ''} onChange={(e) => setNested('plex', 'url', e.target.value)} placeholder="http://192.168.1.10:32400" />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">API token</label>
              <Input value={s.plex?.token || ''} onChange={(e) => setNested('plex', 'token', e.target.value)} placeholder="Plex authentication token" />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">Music section name</label>
              <Input value={s.plex?.music_section || ''} onChange={(e) => setNested('plex', 'music_section', e.target.value)} placeholder="Music" />
            </div>

            {/* Test connection before applying */}
            <div className="rounded-lg border p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium">Test connection</span>
                <Button size="sm" variant="outline" onClick={testPlex} disabled={plextesting}>
                  {plextesting ? <Loader2 className="size-4 animate-spin" /> : <Radio className="size-4" />}
                  {plextesting ? 'Testing…' : 'Test'}
                </Button>
              </div>
              {plexTest && (
                <div className={cn('mt-2 flex items-start gap-2 rounded-lg p-2 text-xs',
                  plexTest.ok ? 'bg-ok/10 text-ok' : 'bg-destructive/10 text-destructive')}>
                  {plexTest.ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0" />
                    : <XCircle className="mt-0.5 size-4 shrink-0" />}
                  <div className="min-w-0">
                    {plexTest.ok ? (
                      <>
                        <p className="font-medium">Connected to {plexTest.friendly_name || 'Plex'} (v{plexTest.version || '?'})</p>
                        <p className="opacity-80">Server URL + token are valid. {(plexTest.libraries || []).length} section(s) found.</p>
                      </>
                    ) : (
                      <p className="break-words">{plexTest.error || 'Connection failed — check URL and token.'}</p>
                    )}
                  </div>
                </div>
              )}
            </div>
            <div className="flex items-center justify-between rounded-lg border bg-muted/30 px-3 py-2">
              <div>
                <span className="text-sm">Sync Plex ratings to file tags</span>
                <p className="text-xs text-muted-foreground">When on, Glacier checks Plex periodically and writes your star ratings into the matching files' tags (5 stars → rating 100). No other setup needed.</p>
              </div>
              <Switch checked={!!s.plex?.rating_sync_enabled} onCheckedChange={(v) => setNested('plex', 'rating_sync_enabled', v)} />
            </div>
            {s.plex?.last_rating_sync && (
              <p className="text-[11px] text-muted-foreground">
                Last sync: {new Date(s.plex.last_rating_sync * 1000).toLocaleString()}
                {s.plex.last_rating_sync_result ? ` — ${s.plex.last_rating_sync_result.written ?? 0} written, ${s.plex.last_rating_sync_result.matched ?? 0} matched` : ''}
              </p>
            )}
          </CardContent>
        </Card>


        {/* Theme */}
        <Card className="lg:col-span-2">
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2"><Palette className="size-4 text-primary" /> Theme</CardTitle>
            <CardDescription>Color mode (incl. AMOLED), accent preset, or a custom color</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-6 sm:flex-row sm:items-start">
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">Color mode</label>
              <Select value={s.theme?.mode || 'dark'} onValueChange={(v) => setNested('theme', 'mode', v)}>
                <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="dark">Dark</SelectItem>
                  <SelectItem value="light">Light</SelectItem>
                  <SelectItem value="amoled">AMOLED (true black)</SelectItem>
                  <SelectItem value="auto">Auto (system)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">Accent</label>
              <div className="flex flex-wrap items-center gap-2">
                {ACCENTS.map((a) => (
                  <button
                    key={a}
                    data-accent={a}
                    onClick={() => setNested('theme', 'accent', a)}
                    className={`h-7 w-7 rounded-full border-2 transition ${s.theme?.accent === a ? 'border-foreground scale-110' : 'border-transparent'}`}
                    style={{ background: ACCENT_SWATCH[a] }}
                    title={a}
                  />
                ))}
                <button
                  onClick={() => setNested('theme', 'accent', 'custom')}
                  className={`h-7 w-7 rounded-full border-2 transition ${s.theme?.accent === 'custom' ? 'border-foreground scale-110' : 'border-transparent'}`}
                  style={{ background: 'linear-gradient(135deg,#f97316,#a855f7,#3b82f6)' }}
                  title="Custom color"
                />
              </div>
            </div>
            <div className="min-w-[220px] space-y-1.5">
              <label className="text-xs text-muted-foreground">Custom accent — hex (#RRGGBB / #RGB) or rgb(r,g,b)</label>
              <div className="flex items-center gap-2">
                <Input
                  value={s.theme?.accent_custom || ''}
                  onChange={(e) => setNested('theme', 'accent_custom', e.target.value)}
                  placeholder="#00A3FF or 0,163,255"
                  className="font-mono text-xs"
                  onBlur={() => {
                    const v = s.theme?.accent_custom;
                    if (v && s.theme?.accent === 'custom') {
                      const vars = customAccentVars(v);
                      if (vars) { applySettingsTheme({ theme: { mode: s.theme?.mode, accent: 'custom', accent_custom: v } }); toast.success('Custom accent applied'); }
                      else toast.error('Invalid color — use #RRGGBB, #RGB, or r,g,b');
                    }
                  }}
                />
                <span
                  className="h-7 w-7 shrink-0 rounded-full border"
                  style={{ background: customAccentVars(s.theme?.accent_custom) ? customAccentVars(s.theme?.accent_custom)['--primary'] : 'transparent' }}
                  title="Custom accent swatch"
                />
              </div>
              {parseAccentColor(s.theme?.accent_custom) && (
                <p className="text-[11px] text-muted-foreground">Live preview updates as you type.</p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Animations */}
        <Card className="lg:col-span-2">
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2"><Sparkles className="size-4 text-primary" /> Animations</CardTitle>
            <CardDescription>Pick a movement preset and fine-tune how Glacier feels</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">Preset</label>
              <Select value={s.animations?.preset || 'modern'}
                onValueChange={(v) => setNested('animations', 'preset', v)}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {ANIM_PRESETS.map((p) => <SelectItem key={p} value={p}>{p[0].toUpperCase() + p.slice(1)}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground">Duration (ms): {s.animations?.duration_ms ?? 220}</label>
                <Input type="number" min={50} max={1000} value={s.animations?.duration_ms ?? 220}
                  onChange={(e) => setNested('animations', 'duration_ms', Number(e.target.value) || 220)} />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-muted-foreground">Easing style</label>
                <Select value={s.animations?.easing || 'ease-out'} onValueChange={(v) => setNested('animations', 'easing', v)}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {['ease', 'ease-in', 'ease-out', 'ease-in-out'].map((e) => <SelectItem key={e} value={e}>{e}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="flex flex-wrap gap-3">
              {[['page_transitions', 'Page transitions'], ['hover', 'Hover animations'], ['click', 'Click animations']].map(([key, label]) => (
                <div key={key} className="flex items-center gap-2 rounded-lg border bg-muted/30 px-3 py-2">
                  <Switch checked={s.animations?.[key] !== false} onCheckedChange={(v) => setNested('animations', key, v)} />
                  <span className="text-sm">{label}</span>
                </div>
              ))}
            </div>
            <p className="text-[11px] text-muted-foreground">
              Live preview applies as you change these options — press “Save changes” to keep them.
            </p>
          </CardContent>
        </Card>

        {/* Sound */}
        <Card className="lg:col-span-2">
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2"><Volume2 className="size-4 text-primary" /> Sound</CardTitle>
            <CardDescription>Play a short sound when a job finishes</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between rounded-lg border bg-muted/30 px-3 py-2">
              <div>
                <span className="text-sm">Play sound on successful completion</span>
                <p className="text-xs text-muted-foreground">Fires on SSE <code className="font-mono">done</code> for Analyze / Organize / etc.</p>
              </div>
              <Switch checked={!!s.sound_on_complete} onCheckedChange={(v) => set('sound_on_complete', v)} />
            </div>
            <div className="flex items-center justify-between rounded-lg border bg-muted/30 px-3 py-2">
              <div>
                <span className="text-sm">Play sound on error</span>
                <p className="text-xs text-muted-foreground">Distinct cue when a job fails</p>
              </div>
              <Switch checked={!!s.sound_on_error} onCheckedChange={(v) => set('sound_on_error', v)} />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground">Completion sound asset</label>
              <Input value={s.sound_asset_complete || ''} onChange={(e) => set('sound_asset_complete', e.target.value)} className="font-mono text-xs" placeholder="sounds/job-done.wav" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Sticky save button - always visible */}
      <div className="sticky bottom-0 z-10 -mx-4 border-t bg-background/80 px-4 py-3 backdrop-blur md:-mx-8 md:px-8">
        <div className="flex justify-end">
          <Button onClick={save}><Save className="size-4" /> Save changes</Button>
        </div>
      </div>
    </div>
  );
}

