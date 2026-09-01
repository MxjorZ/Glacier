import { useEffect, useMemo, useRef, useState } from 'react';
import { Mic, Loader2, AudioWaveform, Activity, Flame, RefreshCw, AlertTriangle, LibraryBig, Download } from 'lucide-react';
import { api } from '../../api.js';
import SearchableTrackPicker from '../../components/SearchableTrackPicker.jsx';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card.jsx';
import { Badge } from '@/components/ui/badge.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select.jsx';
import { Empty } from '../../components/PageHeader.jsx';
import { toast } from '../../toast.jsx';

// Audio Quality Analyzer: pick a library, search ANY track in it, then see
// its waveform timeline, full 0–22 kHz spectrum and a spectrogram heat view.
export default function AudioQualityAnalyzer() {
  const [libs, setLibs] = useState([]);
  const [libId, setLibId] = useState('');
  const [track, setTrack] = useState(null);
  const [info, setInfo] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [ffmpeg, setFfmpeg] = useState(null); // null=unknown, true/false

  useEffect(() => {
    api.settings().then((s) => {
      const l = s.libraries || [];
      setLibs(l);
      if (l.length) setLibId(l[0].id);
    }).catch(() => {});
    api.post('/api/audio-analysis-status').then((r) => setFfmpeg(!!r.ffmpeg)).catch(() => setFfmpeg(false));
  }, []);

  const analyze = async (t) => {
    if (!t?.path) return;
    setAnalyzing(true);
    setAnalysis(null);
    setInfo(null);
    try {
      const [iRes, aRes] = await Promise.all([
        api.post('/api/audio-info', { path: t.path }).catch(() => null),
        api.runAndAwait('audio-analyze', { path: t.path }),
      ]);
      if (iRes?.ok) setInfo(iRes.info);
      if (aRes?.ok) setAnalysis(aRes);
      else toast.error(aRes?.error || 'Analysis failed');
    } catch (e) {
      toast.error(e.message);
    } finally {
      setAnalyzing(false);
    }
  };

  const onPick = (t) => {
    setTrack(t);
    if (t) analyze(t);
  };

  const installFfmpeg = async () => {
    setInstalling(true);
    try {
      const res = await api.runAndAwait('ffmpeg-install', {}, { timeoutMs: 10 * 60 * 1000 });
      if (res?.ok) { toast.success('ffmpeg installed — analysis enabled'); setFfmpeg(true); }
      else toast.error(res?.error || 'Install failed — see the Error Center');
    } catch (e) { toast.error(e.message); }
    finally { setInstalling(false); }
  };

  const fmt = (sec) => {
    if (!Number.isFinite(sec)) return '–';
    const m = Math.floor(sec / 60), s = Math.floor(sec % 60);
    return `${m}:${String(s).padStart(2, '0')}`;
  };

  return (
    <div className="space-y-4">
      {/* Library + track search */}
      <Card>
        <CardHeader className="border-b">
          <CardTitle className="flex items-center gap-2"><Mic className="size-4 text-primary" /> Audio Quality Analyzer</CardTitle>
          <CardDescription>Inspect the waveform, full-range spectrum (0–22 kHz) and spectrogram of any track.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 pt-4">
          <div className="flex flex-wrap items-center gap-2">
            <LibraryBig className="size-4 text-muted-foreground" />
            <Select value={libId} onValueChange={(v) => { setLibId(v); setTrack(null); setAnalysis(null); setInfo(null); }}>
              <SelectTrigger className="w-60"><SelectValue placeholder="Select a library" /></SelectTrigger>
              <SelectContent>
                {libs.map((l) => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <SearchableTrackPicker
            libraries={libs}
            libraryId={libId}
            onLibraryChange={setLibId}
            value={track?.path}
            onChange={onPick}
            placeholder="Search any song in the library — title, artist, album, genre…"
          />
          {ffmpeg === false && (
            <div className="flex flex-wrap items-center gap-3 rounded-xl border border-warn/40 bg-warn/10 px-3 py-2 text-xs text-warn">
              <AlertTriangle className="size-4 shrink-0" />
              <span className="flex-1">ffmpeg isn't available on the backend host — waveform &amp; spectrum views need it.</span>
              <Button size="sm" variant="outline" onClick={installFfmpeg} disabled={installing}>
                {installing ? <Loader2 className="size-3.5 animate-spin" /> : <Download className="size-3.5" />}
                {installing ? 'Installing…' : 'Install automatically'}
              </Button>
            </div>
          )}
          {track && (
            <p className="truncate font-mono text-[11px] text-muted-foreground">{track.path}</p>
          )}
        </CardContent>
      </Card>

      {analyzing && (
        <Card><CardContent className="flex items-center gap-3 pt-4 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin text-primary" /> Decoding &amp; analyzing audio…
        </CardContent></Card>
      )}

      {info && (
        <Card>
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2">
              <Activity className="size-4 text-primary" />
              {info.tags?.title || 'Untitled'}
            </CardTitle>
            <CardDescription>
              {info.tags?.artist || 'Unknown artist'} • {info.tags?.album || 'Unknown album'}
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-4">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              <InfoItem label="Format" value={(info.format || '–') + (info.codec ? '' : '')} />
              <InfoItem label="Duration" value={fmt(info.duration)} />
              <InfoItem label="Bitrate" value={info.bitrate ? `${Math.round(info.bitrate / 1000)} kbps` : '–'} />
              <InfoItem label="Sample rate" value={info.sample_rate ? `${(info.sample_rate / 1000).toFixed(1)} kHz` : '–'} />
              <InfoItem label="Channels" value={info.channels ? (info.channels === 1 ? 'Mono' : `${info.channels} ch`) : '–'} />
              <InfoItem label="Bits/sample" value={info.bits_per_sample ? `${info.bits_per_sample} bit` : '–'} />
              <InfoItem label="Peak level" value={analysis?.levels ? `${analysis.levels.peak.toFixed(3)}` : '–'} />
              <InfoItem label="RMS" value={analysis?.levels ? `${analysis.levels.rms_db} dB` : '–'} />
            </div>
          </CardContent>
        </Card>
      )}

      {analysis?.ok && (
        <>
          <Card>
            <CardHeader className="border-b">
              <CardTitle className="flex items-center gap-2"><AudioWaveform className="size-4 text-primary" /> Waveform timeline</CardTitle>
              <CardDescription>
                {fmt(analysis.duration)} · {analysis.waveform.buckets} buckets · hover to scrub
              </CardDescription>
            </CardHeader>
            <CardContent className="pt-4">
              <WaveformView waveform={analysis.waveform} duration={analysis.duration} accent={getAccent()} />
            </CardContent>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader className="border-b">
                <CardTitle className="flex items-center gap-2"><Activity className="size-4 text-primary" /> Spectrum · 0–22 kHz</CardTitle>
                <CardDescription>Full audible range FFT (dBFS)</CardDescription>
              </CardHeader>
              <CardContent className="pt-4">
                <SpectrumView spectrum={analysis.spectrum} accent={getAccent()} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="border-b">
                <CardTitle className="flex items-center gap-2"><Flame className="size-4 text-primary" /> Spectrogram</CardTitle>
                <CardDescription>Frequency energy over time</CardDescription>
              </CardHeader>
              <CardContent className="pt-4">
                <SpectrogramView spectrogram={analysis.spectrogram} duration={analysis.duration} accent={getAccent()} />
              </CardContent>
            </Card>
          </div>
        </>
      )}

      {!track && !analyzing && (
        <Card><CardContent className="pt-6">
          <Empty text="Search and pick any song from your library to see its waveform, spectrum and spectrogram." />
        </CardContent></Card>
      )}
    </div>
  );
}

function getAccent() {
  const v = getComputedStyle(document.documentElement).getPropertyValue('--primary').trim();
  return v || '#22d3ee';
}

// ---- Waveform (canvas, min/max peaks, hover scrub) -------------------------
function WaveformView({ waveform, duration, accent }) {
  const ref = useRef(null);
  const [hover, setHover] = useState(null);

  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    const dpr = window.devicePixelRatio || 1;
    const w = cv.clientWidth, h = cv.clientHeight;
    cv.width = w * dpr; cv.height = h * dpr;
    const ctx = cv.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    const { min, max } = waveform;
    const mid = h / 2;
    const n = min.length;
    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, accent);
    grad.addColorStop(0.5, accent + 'cc');
    grad.addColorStop(1, accent);
    ctx.fillStyle = grad;

    const step = w / n;
    ctx.globalAlpha = 0.9;
    for (let i = 0; i < n; i++) {
      const x = i * step;
      const y1 = mid - max[i] * mid * 0.95;
      const y2 = mid - min[i] * mid * 0.95;
      const barW = Math.max(1, step * 0.7);
      ctx.fillRect(x, Math.min(y1, y2), barW, Math.max(1, Math.abs(y2 - y1)));
    }
    // Center line
    ctx.globalAlpha = 0.25;
    ctx.fillStyle = accent;
    ctx.fillRect(0, mid, w, 1);
    ctx.globalAlpha = 1;

    if (hover != null) {
      ctx.fillStyle = accent;
      ctx.globalAlpha = 0.6;
      ctx.fillRect(hover * w, 0, 2, h);
      ctx.globalAlpha = 1;
    }
  }, [waveform, accent, hover]);

  const onMove = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    setHover(Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)));
  };

  const hoverT = hover != null ? hover * duration : null;

  return (
    <div className="relative">
      <canvas ref={ref} className="h-40 w-full rounded-lg"
        onMouseMove={onMove} onMouseLeave={() => setHover(null)} />
      {hoverT != null && (
        <div className="pointer-events-none absolute left-2 top-1 rounded bg-background/70 px-1.5 py-0.5 font-mono text-[10px] text-foreground">
          {Math.floor(hoverT / 60)}:{String(Math.floor(hoverT % 60)).padStart(2, '0')}
        </div>
      )}
      <div className="mt-1 flex justify-between font-mono text-[10px] text-muted-foreground">
        <span>0:00</span><span>{fmtTime(duration)}</span>
      </div>
    </div>
  );
}

function fmtTime(sec) {
  const m = Math.floor(sec / 60), s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

// ---- Spectrum (0..22 kHz, dB, log-ish grid) ---------------------------------
function SpectrumView({ spectrum, accent }) {
  const ref = useRef(null);

  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    const dpr = window.devicePixelRatio || 1;
    const w = cv.clientWidth, h = cv.clientHeight;
    cv.width = w * dpr; cv.height = h * dpr;
    const ctx = cv.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    const { freqs, db, max_hz } = spectrum;
    const n = db.length;
    const minDb = -100, maxDb = 0;

    // Filled area
    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, accent);
    grad.addColorStop(1, accent + '30');
    ctx.beginPath();
    ctx.moveTo(0, h);
    for (let i = 0; i < n; i++) {
      const x = (freqs[i] / max_hz) * w;
      const y = h - ((Math.max(db[i], minDb) - minDb) / (maxDb - minDb)) * h;
      ctx.lineTo(x, y);
    }
    ctx.lineTo(w, h);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.globalAlpha = 0.55;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.strokeStyle = accent;
    ctx.lineWidth = 1.4;
    ctx.stroke();

    // Grid: 5/10/15/20 kHz + dB lines
    ctx.strokeStyle = 'rgba(255,255,255,0.08)';
    ctx.fillStyle = 'rgba(255,255,255,0.35)';
    ctx.font = '10px ui-monospace, monospace';
    ctx.lineWidth = 1;
    for (const khz of [0, 5, 10, 15, 20]) {
      const x = (khz * 1000 / max_hz) * w;
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
      ctx.fillText(`${khz}k`, x + 3, h - 4);
    }
    for (const dbLine of [-20, -40, -60, -80]) {
      const y = h - ((dbLine - minDb) / (maxDb - minDb)) * h;
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
      ctx.fillText(`${dbLine}`, 3, y - 3);
    }
  }, [spectrum, accent]);

  return <canvas ref={ref} className="h-56 w-full rounded-lg" />;
}

// ---- Spectrogram (time x frequency heat grid) --------------------------------
function SpectrogramView({ spectrogram, duration, accent }) {
  const ref = useRef(null);

  useEffect(() => {
    const cv = ref.current;
    if (!cv || !spectrogram) return;
    const frames = spectrogram.frames;
    if (!frames.length) return;
    const dpr = window.devicePixelRatio || 1;
    const w = cv.clientWidth, h = cv.clientHeight;
    cv.width = w * dpr; cv.height = h * dpr;
    const ctx = cv.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    const cols = frames.length;
    const rows = spectrogram.freq_bins;
    const cellW = w / cols;
    const cellH = h / rows;
    const minDb = -100, maxDb = 0;

    // Heat: accent-tinted viridis-like ramp from dark to accent/white.
    // Row 0 of backend data = lowest frequency; draw low freqs at bottom.
    for (let c = 0; c < cols; c++) {
      const frame = frames[c];
      for (let r = 0; r < rows; r++) {
        const v = Math.max(frame[rows - 1 - r], minDb);   // flip: low freq bottom
        const t = (v - minDb) / (maxDb - minDb);
        if (t <= 0.02) continue;
        ctx.fillStyle = heatColor(t);
        ctx.globalAlpha = Math.min(1, 0.15 + t * 0.95);
        ctx.fillRect(c * cellW, r * cellH, Math.ceil(cellW), Math.ceil(cellH));
      }
    }
    ctx.globalAlpha = 1;

    // Frequency axis labels
    ctx.fillStyle = 'rgba(255,255,255,0.35)';
    ctx.font = '10px ui-monospace, monospace';
    const maxK = Math.round(spectrogram.max_hz / 1000);
    for (const khz of [0, Math.round(maxK / 2), maxK]) {
      const y = h - (khz * 1000 / spectrogram.max_hz) * h - 3;
      ctx.fillText(`${khz}k`, 3, Math.max(10, y));
    }
  }, [spectrogram, accent]);

  return (
    <div className="relative">
      <canvas ref={ref} className="h-56 w-full rounded-lg" />
      <div className="mt-1 flex justify-between font-mono text-[10px] text-muted-foreground">
        <span>0:00</span><span>{fmtTime(duration)}</span>
      </div>
    </div>
  );
}

// t in 0..1 -> perceptual heat color (dark navy -> accent -> white-hot).
function heatColor(t) {
  // Precomputed perceptual ramp; blend stops.
  const stops = [
    [8, 10, 40], [18, 40, 90], [10, 90, 130], [30, 140, 120],
    [120, 190, 90], [230, 210, 70], [255, 250, 200],
  ];
  const pos = Math.min(0.9999, Math.max(0, t)) * (stops.length - 1);
  const i = Math.floor(pos);
  const f = pos - i;
  const a = stops[i], b = stops[i + 1];
  const mix = a.map((v, k) => Math.round(v + (b[k] - v) * f));
  return `rgb(${mix[0]} ${mix[1]} ${mix[2]})`;
}

function InfoItem({ label, value }) {
  return (
    <div className="glass-surface rounded-lg border border-white/10 p-3 text-center">
      <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 font-mono text-sm font-semibold">{value}</div>
    </div>
  );
}
