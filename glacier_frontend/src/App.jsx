import { useEffect, useRef, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { useSSE } from './useSSE.js';
import { api } from './api.js';
import { applySettingsTheme } from './lib/themes.js';
import { playJobSound, unlockAudio } from './lib/sound.js';
import Sidebar from './components/Sidebar.jsx';
import TitleBar from './components/TitleBar.jsx';
import { Progress } from '@/components/ui/progress.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Libraries from './pages/Libraries.jsx';
import Tools from './pages/Tools.jsx';
import Cleanup from './pages/Cleanup.jsx';
import Tags from './pages/Tags.jsx';
import Plex from './pages/Plex.jsx';
import Logs from './pages/Logs.jsx';
import Settings from './pages/Settings.jsx';
import About from './pages/About.jsx';

const VALID = ['dashboard', 'libraries', 'tools', 'cleanup', 'tags', 'plex', 'logs', 'settings', 'about'];

function readHash() {
  const h = window.location.hash.replace(/^#\/?/, '');
  return VALID.includes(h) ? h : 'dashboard';
}

export default function App() {
  const [page, setPage] = useState(readHash);
  const [sys, setSys] = useState(null);
  const [settings, setSettings] = useState(null);
  const settingsRef = useRef(null);
  settingsRef.current = settings;

  const handleEvent = (data) => playJobSound(data, settingsRef.current);
  const { job, progress } = useSSE(handleEvent);

  useEffect(() => {
    api.system().then(setSys).catch(() => {});
    api.settings().then((s) => { setSettings(s); applySettingsTheme(s); }).catch(() => {});
    // Unlock audio playback on the first user gesture (autoplay policy).
    const unlock = () => unlockAudio();
    window.addEventListener('pointerdown', unlock);
    window.addEventListener('keydown', unlock);
    const onHash = () => setPage(readHash());
    window.addEventListener('hashchange', onHash);
    return () => {
      window.removeEventListener('pointerdown', unlock);
      window.removeEventListener('keydown', unlock);
      window.removeEventListener('hashchange', onHash);
    };
  }, []);

  const nav = (key) => { window.location.hash = `/${key}`; setPage(key); };

  return (
    <div className="h-screen w-full overflow-hidden">
      <Sidebar page={page} onNavigate={nav} />
      <TitleBar sys={sys} job={job} />
      <main className="ml-14 mt-10 h-[calc(100vh-40px)] overflow-y-auto px-4 py-6 md:px-8">
        <div key={page} className="anim-fade mx-auto w-full max-w-6xl">
          {page === 'dashboard' && <Dashboard onNavigate={nav} />}
          {page === 'libraries' && <Libraries />}
          {page === 'tools' && <Tools />}
          {page === 'cleanup' && <Cleanup />}
          {page === 'tags' && <Tags />}
          {page === 'plex' && <Plex />}
          {page === 'logs' && <Logs />}
          {page === 'settings' && <Settings settings={settings} onSettings={setSettings} />}
          {page === 'about' && <About sys={sys} />}
        </div>
      </main>

      {job?.running && progress && (
        <div className="fixed bottom-4 left-1/2 z-40 w-80 -translate-x-1/2 rounded-lg border bg-popover p-3 shadow-xl">
          <div className="mb-2 flex items-center gap-2 text-xs font-medium">
            <Loader2 className="size-3.5 animate-spin text-primary" />
            <span className="truncate">{progress.label || job?.job?.operation}</span>
            <span className="ml-auto font-mono text-muted-foreground">
              {progress.current}/{progress.total}
            </span>
          </div>
          <Progress value={progress.current} max={progress.total} />
        </div>
      )}
    </div>
  );
}
