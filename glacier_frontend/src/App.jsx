import { useEffect, useRef, useState } from 'react';
import { useSSE } from './useSSE.js';
import { api } from './api.js';
import { applySettingsTheme } from './lib/themes.js';
import { playJobSound, unlockAudio } from './lib/sound.js';
import { ShieldAlert, ScrollText, Music2, Wrench } from 'lucide-react';
import Sidebar from './components/Sidebar.jsx';
import TitleBar from './components/TitleBar.jsx';
import { toast } from './toast.jsx';
import ActivityDock from './ActivityDock.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Libraries from './pages/Libraries.jsx';
import Tools from './pages/Tools.jsx';
import Genres from './pages/Genres.jsx';
import Cleanup from './pages/Cleanup.jsx';
import Tags from './pages/Tags.jsx';
import Plex from './pages/Plex.jsx';
import Logs from './pages/Logs.jsx';
import Errors from './pages/Errors.jsx';
import Settings from './pages/Settings.jsx';
import About from './pages/About.jsx';

const VALID = ['dashboard', 'libraries', 'tools', 'genres', 'cleanup', 'tags', 'plex', 'logs', 'errors', 'settings', 'about'];

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
  const { jobs, progress, logs, errors, dismissError, clearErrors } = useSSE(handleEvent);

  // Surface every new error as a notification (toast), regardless of the page.
  const seenErrors = useRef(0);
  useEffect(() => {
    while (seenErrors.current < errors.length) {
      toast.error(errors[seenErrors.current].message || 'An error occurred');
      seenErrors.current += 1;
    }
  }, [errors]);

  // Stage 4 #2: right-click anywhere opens the context menu (Error Center, Logs).
  const [ctx, setCtx] = useState(null);
  useEffect(() => {
    const onCtx = (e) => {
      e.preventDefault();
      setCtx({ x: e.clientX, y: e.clientY });
    };
    const onCloseCtx = () => setCtx(null);
    window.addEventListener('contextmenu', onCtx);
    window.addEventListener('click', onCloseCtx);
    window.addEventListener('scroll', onCloseCtx, true);
    return () => {
      window.removeEventListener('contextmenu', onCtx);
      window.removeEventListener('click', onCloseCtx);
      window.removeEventListener('scroll', onCloseCtx, true);
    };
  }, []);

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
      <TitleBar sys={sys} jobsCount={Object.keys(jobs).length} errorCount={errors.length} onErrors={() => nav('errors')} onLogs={() => nav('logs')} />
      <main className="ml-14 mt-10 h-[calc(100vh-40px)] overflow-y-auto px-4 pt-6 pb-16 md:px-8">
        {/* All pages stay mounted (hidden with CSS) so navigating doesn't reset
            their state or drop live SSE updates — selections, loaded data and
            background-progress views persist across page switches. */}
        <div className="mx-auto w-full max-w-6xl">
          <div style={{ display: page === 'dashboard' ? undefined : 'none' }} className={`anim-fade ${page === 'dashboard' ? '' : 'hidden'}`}>
            <Dashboard onNavigate={nav} />
          </div>
          <div style={{ display: page === 'libraries' ? undefined : 'none' }} className={`anim-fade ${page === 'libraries' ? '' : 'hidden'}`}>
            <Libraries />
          </div>
          <div style={{ display: page === 'tools' ? undefined : 'none' }} className={`anim-fade ${page === 'tools' ? '' : 'hidden'}`}>
            <Tools />
          </div>
          <div style={{ display: page === 'genres' ? undefined : 'none' }} className={`anim-fade ${page === 'genres' ? '' : 'hidden'}`}>
            <Genres />
          </div>
          <div style={{ display: page === 'cleanup' ? undefined : 'none' }} className={`anim-fade ${page === 'cleanup' ? '' : 'hidden'}`}>
            <Cleanup />
          </div>
          <div style={{ display: page === 'tags' ? undefined : 'none' }} className={`anim-fade ${page === 'tags' ? '' : 'hidden'}`}>
            <Tags />
          </div>
          <div style={{ display: page === 'plex' ? undefined : 'none' }} className={`anim-fade ${page === 'plex' ? '' : 'hidden'}`}>
            <Plex />
          </div>
          <div style={{ display: page === 'logs' ? undefined : 'none' }} className={`anim-fade ${page === 'logs' ? '' : 'hidden'}`}>
            <Logs />
          </div>
          <div style={{ display: page === 'errors' ? undefined : 'none' }} className={`anim-fade ${page === 'errors' ? '' : 'hidden'}`}>
            <Errors liveErrors={errors} />
          </div>
          <div style={{ display: page === 'settings' ? undefined : 'none' }} className={`anim-fade ${page === 'settings' ? '' : 'hidden'}`}>
            <Settings settings={settings} onSettings={setSettings} />
          </div>
          <div style={{ display: page === 'about' ? undefined : 'none' }} className={`anim-fade ${page === 'about' ? '' : 'hidden'}`}>
            <About sys={sys} />
          </div>
        </div>
      </main>

      <ActivityDock jobs={jobs} progress={progress} logs={logs} errors={errors} onDismissError={dismissError} onClearErrors={clearErrors} />

      {/* Context menu */}
      {ctx && (
        <div style={{ top: ctx.y, left: ctx.x }} className="fixed z-50 w-52 overflow-hidden rounded-lg border bg-popover p-1 shadow-xl">
          <button onClick={() => { setCtx(null); nav('errors'); }} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent">
            <ShieldAlert className="size-4 text-destructive" /> Error Center {errors.length > 0 && <span className="ml-auto text-xs text-destructive">({errors.length})</span>}
          </button>
          <button onClick={() => { setCtx(null); nav('logs'); }} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent">
            <ScrollText className="size-4" /> Logs
          </button>
          <button onClick={() => { setCtx(null); nav('genres'); }} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent">
            <Music2 className="size-4" /> Genres
          </button>
          <button onClick={() => { setCtx(null); nav('tools'); }} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent">
            <Wrench className="size-4" /> Tools
          </button>
        </div>
      )}
    </div>
  );
}
