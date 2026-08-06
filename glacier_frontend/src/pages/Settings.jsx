import { useEffect, useState } from 'react';
import { Save, Server, SlidersHorizontal, FolderTree, ShieldAlert, Radio, Palette, Volume2, Loader2, CheckCircle2, XCircle, Sparkles, Settings2, FileText, FolderOpen, Tag } from 'lucide-react';
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

const CODE_SNIPPETS = [
  '{title}', '{artist}', '{artists}', '{album}', '{album_artist}',
  '{track}', '{total_tracks}', '{disc}', '{total_discs}',
  '{year}', '{date}', '{isrc}', '{upc}', '{category}', '{playlist}',
];

const NAV_ITEMS = [
  { id: 'general', label: 'General', Icon: Settings2 },
  { id: 'naming', label: 'Naming', Icon: FileText },
  { id: 'filemanagement', label: 'File Management', Icon: FolderOpen },
  { id: 'metadata', label: 'Metadata', Icon: Tag },
];

export default function Settings({ settings, onSettings }) {
  const [s, setS] = useState(settings || {});
  const [plexTest, setPlexTest] = useState(null);
  const [plextesting, setPlexTesting] = useState(false);
  const [activeTab, setActiveTab] = useState('general');

  useEffect(() => { if (settings) setS(settings); }, [settings]);

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
        startup_scan_enabled: s.startup_scan_enabled,
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

  // Live preview for naming
  const sampleTags = {
    artist: 'HUNTR/X',
    album: 'KPop Demon Hunters (Soundtrack from the Netflix Film)',
    album_artist: 'KPop Demon Hunters Cast',
    title: 'Golden',
    track: '04',
    total_tracks: '12',
    disc: '1',
    total_discs: '2',
    year: '2025',
    date: '2025-03-15',
    isrc: 'US-ABC-25-12345',
    upc: '123456789012',
    category: 'Soundtrack',
    playlist: 'KPop Hits 2025',
  };

  const renderPreview = (pattern, tags) => {
    if (!pattern) return 'Enter a pattern to preview';
    let result = pattern;
    for (const [key, value] of Object.entries(tags)) {
      result = result.replace(new RegExp(`{${key}}`, 'g'), value || `{${key}}`);
    }
    return result;
  };

  return (
    <div className="flex flex-col h-full">
      <PageHeader title="Settings" description="Configure Glacier to your liking." />

      <div className="flex flex-1 gap-6">
        {/* Sidebar Navigation */}
        <div className="w-48 shrink-0 space-y-1">
          {NAV_ITEMS.map(({ id, label, Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={cn(
                'flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all',
                activeTab === id
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
              )}
            >
              <Icon className="size-4" />
              {label}
            </button>
          ))}
        </div>

        {/* Content Panel */}
        <div className="flex-1 min-w-0">
          {/* ===== GENERAL TAB ===== */}
          {activeTab === 'general' && (
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle>General</CardTitle>
                  <CardDescription>Application-wide settings</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-1.5">
                    <label>Language</label>
                    <Select value="en" onValueChange={() => {}}>
                      <SelectTrigger className="w-full"><SelectValue placeholder="English" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="en">English</SelectItem>
                        <SelectItem value="he">Hebrew</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-1.5">
                    <label>Mode</label>
                    <Select value={s.theme?.mode || 'dark'} onValueChange={(v) => setNested('theme', 'mode', v)}>
                      <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="dark">Dark</SelectItem>
                        <SelectItem value="light">Light</SelectItem>
                        <SelectItem value="amoled">AMOLED</SelectItem>
                        <SelectItem value="auto">Auto</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-1.5">
                    <label>Accent</label>
                    <div className="flex flex-wrap items-center gap-2">
                      {ACCENTS.map((a) => (
                        <button
                          key={a}
                          onClick={() => setNested('theme', 'accent', a)}
                          className={`h-8 w-8 rounded-full border-2 transition ${s.theme?.accent === a ? 'border-foreground scale-110' : 'border-transparent'}`}
                          style={{ background: ACCENT_SWATCH[a] }}
                          title={a}
                        />
                      ))}
                      <button
                        onClick={() => setNested('theme', 'accent', 'custom')}
                        className={`h-8 w-8 rounded-full border-2 transition ${s.theme?.accent === 'custom' ? 'border-foreground scale-110' : 'border-transparent'}`}
                        style={{ background: 'linear-gradient(135deg,#f97316,#a855f7,#3b82f6)' }}
                        title="Custom color"
                      />
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <label>Custom accent — hex (#RRGGBB) or rgb(r,g,b)</label>
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
                  </div>

                  <div className="flex items-center justify-between rounded-lg border bg-muted/30 px-3 py-2">
                    <div>
                      <span className="text-sm">Sound Effects</span>
                      <p className="text-xs text-muted-foreground">Play sounds on job completion</p>
                    </div>
                    <Switch checked={!!s.sound_on_complete} onCheckedChange={(v) => set('sound_on_complete', v)} />
                  </div>

                  <div className="flex items-center justify-between rounded-lg border bg-muted/30 px-3 py-2">
                    <div>
                      <span className="text-sm">Update Notifications</span>
                      <p className="text-xs text-muted-foreground">Check for updates on startup</p>
                    </div>
                    <Switch checked={false} onCheckedChange={() => {}} />
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Download Path</CardTitle>
                  <CardDescription>Where downloaded files are stored</CardDescription>
                </CardHeader>
                <CardContent>
                  <Input value="/mnt/music" onChange={() => {}} className="font-mono text-xs" />
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Rate Limited Downloads</CardTitle>
                  <CardDescription>Throttle download speed</CardDescription>
                </CardHeader>
                <CardContent>
                  <Select value="normal">
                    <SelectTrigger className="w-full"><SelectValue placeholder="Normal" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="normal">Normal</SelectItem>
                      <SelectItem value="slow">Slow</SelectItem>
                      <SelectItem value="fast">Fast</SelectItem>
                    </SelectContent>
                  </Select>
                </CardContent>
              </Card>
            </div>
          )}

          {/* ===== NAMING TAB ===== */}
          {activeTab === 'naming' && (
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle>Filename Pattern</CardTitle>
                  <CardDescription>How files should be named when organized</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <Input
                    value={s.naming_pattern || ''}
                    onChange={(e) => set('naming_pattern', e.target.value)}
                    className="font-mono text-sm"
                    placeholder="{artist} - {album} - {track} - {title}"
                  />
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">Preview</p>
                    <div className="rounded-lg border bg-muted/30 p-3 font-mono text-sm text-foreground">
                      {renderPreview(s.naming_pattern || '{artist} - {album} - {track} - {title}', sampleTags)}
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Folder Structure</CardTitle>
                  <CardDescription>How folders should be organized</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <Input
                    value={s.folder_pattern || ''}
                    onChange={(e) => set('folder_pattern', e.target.value)}
                    className="font-mono text-sm"
                    placeholder="{album_artist}/{album} ({year})"
                  />
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">Preview</p>
                    <div className="rounded-lg border bg-muted/30 p-3 font-mono text-sm text-foreground">
                      {renderPreview(s.folder_pattern || '{album_artist}/{album} ({year})', sampleTags)}
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Code Snippets</CardTitle>
                  <CardDescription>Available variables for patterns</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="flex flex-wrap gap-2">
                    {CODE_SNIPPETS.map((snippet) => (
                      <span key={snippet} className="rounded-md bg-muted/30 px-2.5 py-1 font-mono text-xs text-muted-foreground">
                        {snippet}
                      </span>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* ===== FILE MANAGEMENT TAB ===== */}
          {activeTab === 'filemanagement' && (
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle>File Management</CardTitle>
                  <CardDescription>How files are handled</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between rounded-lg border bg-muted/30 px-3 py-2">
                    <div>
                      <span className="text-sm">Backup before moving</span>
                      <p className="text-xs text-muted-foreground">Create .bak copy before organizing</p>
                    </div>
                    <Switch checked={!!s.backup_before_move} onCheckedChange={(v) => set('backup_before_move', v)} />
                  </div>

                  <div className="space-y-1.5">
                    <label>Excluded folders (comma separated)</label>
                    <Input
                      value={exclText}
                      onChange={(e) => set('excluded_folders', e.target.value.split(',').map((x) => x.trim()).filter(Boolean))}
                      className="font-mono text-xs"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label>Audio extensions (comma separated)</label>
                    <Input
                      value={extText}
                      onChange={(e) => set('extensions', e.target.value.split(',').map((x) => x.trim()).filter(Boolean))}
                      className="font-mono text-xs"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label>Preferred format for duplicates</label>
                    <Select value={s.dup_priority || 'flac'} onValueChange={(v) => set('dup_priority', v)}>
                      <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {['flac', 'wav', 'alac', 'm4a', 'ogg', 'opus', 'wma', 'mp3', 'aac'].map((f) => (
                          <SelectItem key={f} value={f}>{f}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
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
            </div>
          )}

          {/* ===== METADATA TAB ===== */}
          {activeTab === 'metadata' && (
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle>Exclusivity</CardTitle>
                  <CardDescription>Cross-library identity and default policy</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-1.5">
                    <label>Identity match</label>
                    <Select value={s.exclusivity?.identity || 'auto'} onValueChange={(v) => setNested('exclusivity', 'identity', v)}>
                      <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {IDENTITIES.map((i) => <SelectItem key={i.value} value={i.value}>{i.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-1.5">
                    <label>Default resolution policy</label>
                    <Select value={s.exclusivity?.default_policy || 'report_only'} onValueChange={(v) => setNested('exclusivity', 'default_policy', v)}>
                      <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {POLICIES.map((p) => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-1.5">
                    <label>Primary Music Library</label>
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

              <Card>
                <CardHeader>
                  <CardTitle>Plex Integration</CardTitle>
                  <CardDescription>Media server connection</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-1.5">
                    <label>Server URL</label>
                    <Input value={s.plex?.url || ''} onChange={(e) => setNested('plex', 'url', e.target.value)} placeholder="http://192.168.1.10:32400" />
                  </div>
                  <div className="space-y-1.5">
                    <label>API token</label>
                    <Input value={s.plex?.token || ''} onChange={(e) => setNested('plex', 'token', e.target.value)} placeholder="Plex authentication token" />
                  </div>
                  <div className="space-y-1.5">
                    <label>Music section name</label>
                    <Input value={s.plex?.music_section || ''} onChange={(e) => setNested('plex', 'music_section', e.target.value)} placeholder="Music" />
                  </div>

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
                      <p className="text-xs text-muted-foreground">Periodically writes Plex star ratings into file tags</p>
                    </div>
                    <Switch
                      checked={!!s.plex?.rating_sync_enabled}
                      onCheckedChange={(v) => setNested('plex', 'rating_sync_enabled', v)}
                    />
                  </div>

                  {s.plex?.last_rating_sync && (
                    <p className="text-[11px] text-muted-foreground">
                      Last sync: {new Date(s.plex.last_rating_sync * 1000).toLocaleString()}
                      {s.plex.last_rating_sync_result ? ` — ${s.plex.last_rating_sync_result.written ?? 0} written, ${s.plex.last_rating_sync_result.matched ?? 0} matched` : ''}
                    </p>
                  )}
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      </div>

      {/* Sticky save button */}
      <div className="sticky bottom-0 z-10 -mx-4 border-t bg-background/80 px-4 py-3 backdrop-blur md:-mx-8 md:px-8">
        <div className="flex justify-end">
          <Button onClick={save}><Save className="size-4" /> Save changes</Button>
        </div>
      </div>
    </div>
  );
}