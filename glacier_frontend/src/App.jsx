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
import Plex from './pages/Plex.jsx';
import Logs from './pages/Logs.jsx';
import Errors from './pages/Errors.jsx';
import Settings from './pages/Settings.jsx';
import About from './pages/About.jsx';

const VALID = ['dashboard', 'libraries', 'tools', 'plex', 'logs', 'errors', 'settings', 'about'];

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

  const seenErrors = useRef(0);
  useEffect(() => {
    while (seenErrors.current < errors.length) {
      toast.error(errors[seenErrors.current].message || 'An error occurred');
      seenErrors.current += 1;
    }
  }, [errors]);

  const [ctx, setCtx] = useState(null);
  useEffect(() => {
    const onCtx = (e) => { e.preventDefault(); setCtx({ x: e.clientX, y: e.clientY }); };
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
      {/* Ambient gradient field — the glass surfaces blur this for depth. */}
      <div className="ambience-layer" aria-hidden="true" />
      <Sidebar page={page} onNavigate={nav} />
      <TitleBar
        sys={sys}
        jobsCount={Object.keys(jobs).length}
        errorCount={errors.length}
        onErrors={() => nav('errors')}
        onLogs={() => nav('logs')}
      />
      <main className="main-content relative z-10">
        <div className="mx-auto w-full max-w-7xl">
          {page === 'dashboard' && <Dashboard onNavigate={nav} />}
          {page === 'libraries' && <Libraries />}
          {page === 'tools' && <Tools />}
          {page === 'plex' && <Plex />}
          {page === 'logs' && <Logs />}
          {page === 'errors' && <Errors liveErrors={errors} />}
          {page === 'settings' && <Settings settings={settings} onSettings={setSettings} />}
          {page === 'about' && <About sys={sys} />}
        </div>
      </main>

      <ActivityDock
        jobs={jobs}
        progress={progress}
        logs={logs}
        errors={errors}
        onDismissError={dismissError}
        onClearErrors={clearErrors}
      />

      {ctx && (
        <div style={{ top: ctx.y, left: ctx.x }} className="fixed z-50 w-52 overflow-hidden rounded-lg border bg-popover p-1 shadow-xl">
          <button onClick={() => { setCtx(null); nav('errors'); }} className="context-menu-item flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent">
            <ShieldAlert className="size-4 text-destructive" /> Error Center {errors.length > 0 && <span className="ml-auto text-xs text-destructive">({errors.length})</span>}
          </button>
          <button onClick={() => { setCtx(null); nav('logs'); }} className="context-menu-item flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent">
            <ScrollText className="size-4" /> Logs
          </button>
          <button onClick={() => { setCtx(null); nav('tools'); }} className="context-menu-item flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent">
            <Music2 className="size-4" /> Tools
          </button>
          <button onClick={() => { setCtx(null); nav('settings'); }} className="context-menu-item flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent">
            <Wrench className="size-4" /> Settings
          </button>
        </div>
      )}
    </div>
  );
}