import { useState, useEffect } from 'react';
import { Mic, Folder, RefreshCw } from 'lucide-react';
import { api } from '../../api.js';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card.jsx';
import { Button } from '@/components/ui/button.jsx';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select.jsx';
import { Badge } from '@/components/ui/badge.jsx';
import { Empty } from '../../components/PageHeader.jsx';
import { toast } from '../../toast.jsx';
import FileExplorer from '../../FileExplorer.jsx';

export default function AudioQualityAnalyzer() {
  const [libs, setLibs] = useState([]);
  const [libId, setLibId] = useState('');
  const [tracks, setTracks] = useState([]);
  const [selectedFile, setSelectedFile] = useState('');
  const [audioInfo, setAudioInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [picker, setPicker] = useState(false);

  useEffect(() => {
    api.settings().then((s) => {
      const l = s.libraries || [];
      setLibs(l);
      if (l.length) setLibId(l[0].id);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!libId) return;
    setLoading(true);
    api.tracks({ library_id: libId, page: 1, per_page: 200 })
      .then((res) => setTracks(res.items || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [libId]);

  const loadAudioInfo = async (path) => {
    if (!path) return;
    setLoading(true);
    setAudioInfo(null);
    try {
      const res = await api.post('/api/audio-info', { path });
      if (res?.ok) {
        setAudioInfo(res.info);
        toast.success('Audio info loaded');
      } else {
        toast.error(res?.error || 'Failed to load audio info');
      }
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleTrackSelect = (path) => {
    setSelectedFile(path);
    loadAudioInfo(path);
  };

  const onFileExplorerSelect = (path, paths) => {
    const p = path || (paths && paths[0]);
    if (p) {
      setSelectedFile(p);
      setPicker(false);
      loadAudioInfo(p);
    }
  };

  const formatDuration = (sec) => {
    if (!sec) return '0:00';
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  const formatBitrate = (bitrate) => {
    if (!bitrate) return '–';
    if (bitrate >= 1000) return `${(bitrate / 1000).toFixed(1)} Mbps`;
    return `${bitrate} kbps`;
  };

  const formatSampleRate = (rate) => {
    if (!rate) return '–';
    if (rate >= 1000) return `${(rate / 1000).toFixed(1)} kHz`;
    return `${rate} Hz`;
  };

  const formatSize = (bytes) => {
    if (!bytes) return '–';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1073741824) return `${(bytes / 1048576).toFixed(1)} MB`;
    return `${(bytes / 1073741824).toFixed(1)} GB`;
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Select value={libId} onValueChange={setLibId}>
          <SelectTrigger className="w-56"><SelectValue placeholder="Select a library" /></SelectTrigger>
          <SelectContent>
            {libs.map((l) => <SelectItem key={l.id} value={l.id}>{l.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <Button variant="outline" onClick={() => setPicker(true)}>
          <Folder className="size-4" /> Browse file
        </Button>
        {selectedFile && (
          <Badge variant="secondary" className="font-mono text-xs truncate max-w-xs">
            {selectedFile}
          </Badge>
        )}
      </div>

      {libId && tracks.length > 0 && (
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">Select a track from library</label>
          <Select value={selectedFile} onValueChange={handleTrackSelect}>
            <SelectTrigger className="w-full"><SelectValue placeholder="Choose a track…" /></SelectTrigger>
            <SelectContent className="max-h-60">
              {tracks.map((t) => {
                const label = `${t.artist || '?'} – ${t.title || t.path}`;
                return <SelectItem key={t.path} value={t.path}>{label}</SelectItem>;
              })}
            </SelectContent>
          </Select>
        </div>
      )}

      {loading && (
        <div className="flex items-center gap-2 text-muted-foreground">
          <RefreshCw className="size-4 animate-spin" /> Loading audio info…
        </div>
      )}

      {audioInfo && (
        <Card>
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2">
              <Mic className="size-4 text-primary" />
              {audioInfo.tags?.title || 'Untitled'}
            </CardTitle>
            <CardDescription>
              {audioInfo.tags?.artist || 'Unknown artist'} • {audioInfo.tags?.album || 'Unknown album'}
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-4">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              <InfoItem label="Format" value={audioInfo.format || '–'} />
              <InfoItem label="Codec" value={audioInfo.codec || '–'} />
              <InfoItem label="Duration" value={formatDuration(audioInfo.duration)} />
              <InfoItem label="Bitrate" value={formatBitrate(audioInfo.bitrate)} />
              <InfoItem label="Sample Rate" value={formatSampleRate(audioInfo.sample_rate)} />
              <InfoItem label="Channels" value={audioInfo.channels ? (audioInfo.channels === 1 ? 'Mono' : 'Stereo') : '–'} />
              <InfoItem label="Bits per sample" value={audioInfo.bits_per_sample ? `${audioInfo.bits_per_sample} bit` : '–'} />
              <InfoItem label="File size" value={audioInfo.file_size ? formatSize(audioInfo.file_size) : '–'} />
            </div>
          </CardContent>
        </Card>
      )}

      {!audioInfo && !loading && <Empty text="Select a track or browse a file to analyze audio quality." />}

      <FileExplorer
        open={picker}
        onClose={() => setPicker(false)}
        onSelect={onFileExplorerSelect}
        mode="file"
        audioOnly
        multiple={false}
      />
    </div>
  );
}

function InfoItem({ label, value }) {
  return (
    <div className="rounded-lg border bg-muted/30 p-3 text-center">
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 font-mono text-sm font-semibold">{value}</div>
    </div>
  );
}