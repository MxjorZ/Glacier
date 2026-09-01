// Thin API client. All calls return parsed JSON; non-2xx throws with message.
async function req(method, url, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = null; }
  if (!res.ok) {
    const msg = (data && (data.error || data.message)) || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

export const api = {
  get: (url) => req('GET', url),
  post: (url, body) => req('POST', url, body),
  patch: (url, body) => req('PATCH', url, body),
  delete: (url) => req('DELETE', url),

  // high-level helpers
  settings: () => req('GET', '/api/settings'),
  saveSettings: (patch) => req('POST', '/api/settings', patch),
  replaceSettings: (body) => req('POST', '/api/settings', { ...body, action: 'replace' }),
  libraries: () => req('GET', '/api/libraries'),
  libraryStatus: () => req('GET', '/api/libraries/status'),
  addLibrary: (name, path) => req('POST', '/api/libraries', { name, path }),
  renameLibrary: (id, name) => req('PATCH', `/api/libraries/${id}`, { name }),
  setLibraryEnabled: (id, enabled) => req('PATCH', `/api/libraries/${id}`, { enabled }),
  removeLibrary: (id) => req('DELETE', `/api/libraries/${id}`),
  listDir: (path) => req('POST', '/api/list-dir', { path }),
  system: () => req('GET', '/api/system'),
  currentJob: () => req('GET', '/api/jobs/current'),
  logs: (limit = 300) => req('GET', `/api/logs?limit=${limit}`),

  run: (op, body) => req('POST', `/api/run/${op}`, body),

  // Start a job and poll its history entry until it finishes. Resolves with
  // the job's result. One shared implementation — previously three pages had
  // their own private copies of this loop.
  runAndAwait: async (op, body, { timeoutMs = 30 * 60 * 1000, pollMs = 500 } = {}) => {
    const start = await req('POST', `/api/run/${op}`, body);
    const jid = start?.job?.id;
    const t0 = Date.now();
    while (Date.now() - t0 < timeoutMs) {
      await new Promise((r) => setTimeout(r, pollMs));
      const hist = await req('GET', '/api/jobs/history');
      const jobs = hist.jobs || [];
      const done = jid != null
        ? jobs.find((j) => j.id === jid && j.status !== 'running')
        : jobs.filter((j) => j.status !== 'running').pop();
      if (done) return done.result ?? done;
    }
    throw new Error('Job timed out');
  },

  previewPath: (body) => req('POST', '/api/preview-path', body),

  artistExclusivity: () => req('POST', '/api/run/artist-exclusivity'),
  resolveArtistExclusivity: (body) => req('POST', '/api/run/resolve-artist-exclusivity', body),
  extractMove: (body) => req('POST', '/api/run/library_extract_move', body),

  tagList: (paths) => req('POST', '/api/tag-list', { paths }),
  tagRead: (paths) => req('POST', '/api/tag-read', { paths }),
  tagSave: (paths, field, value) => req('POST', '/api/tag-save', { paths, field, value }),

  // File manager (library-scoped, backend enforces containment)
  fileRename: (path, name, library_id) => req('POST', '/api/files/rename', { path, name, library_id }),
  fileNewFolder: (path, name, library_id) => req('POST', '/api/files/new-folder', { path, name, library_id }),

  plex: {
    status: () => req('POST', '/api/plex/status'),
    test: (url, token, section) => req('POST', '/api/plex/test', { url, token, section }),
    sections: (url, token) => req('POST', '/api/plex/sections', { url, token }),
    stats: () => req('POST', '/api/plex/stats'),
    libraryStats: () => req('POST', '/api/plex/library-stats'),
    search: (query) => req('POST', '/api/plex/search', { query }),
    rate: (query, rating) => req('POST', '/api/plex/rate', { query, rating }),
    duplicates: () => req('POST', '/api/plex/duplicates'),
    syncRatings: () => req('POST', '/api/plex/sync-ratings'),
    syncStatus: () => req('GET', '/api/plex/sync-status'),
    exportLibrary: (section, url, token) => req('POST', '/api/run/plex-export', { section, url, token }),
    exportContent: (url, token, section) => req('POST', '/api/plex/export', { section, url, token }),
  },

  // Stage 4
  errors: () => req('GET', '/api/errors'),
  clearErrors: () => req('DELETE', '/api/errors'),
  operations: (limit = 100) => req('GET', `/api/operations?limit=${limit}`),
  quickScan: (library_ids) => req('POST', '/api/run/quick-scan', { library_ids }),
  tracks: (body) => req('POST', '/api/tracks', body),
  genres: (library_id) => req('POST', '/api/genres', { library_id }),
  genreOps: (op, body) => req('POST', `/api/run/genres/${op}`, body),
  stats: () => req('GET', '/api/stats'),
  terminateJob: (id) => req('POST', `/api/jobs/${id}/terminate`),
};

// ---- Formatters (Stage 4 #11): one consistent DD/MM/YYYY HH:mm:ss format -----
const pad = (n) => String(n).padStart(2, '0');

export const fmtDateTime = (ts) => {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
};

export const fmtDateDay = (ts) => {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
};

// Recent-operation style label: Today 21:35 / Yesterday 18:42 / 05/08/2026 11:32
export const fmtRelative = (ts) => {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diffDays = Math.round((startToday - startDay) / 86400000);
  const time = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  if (diffDays === 0) return `Today ${time}`;
  if (diffDays === 1) return `Yesterday ${time}`;
  return `${fmtDateDay(ts)} ${time}`;
};

// Formatters reused across pages.
export const fmtBytes = (n) => {
  if (!n) return '0 B';
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.min(u.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
  return `${(n / 1024 ** i).toFixed(i ? 1 : 0)} ${u[i]}`;
};
export const fmtDur = (sec) => {
  if (!sec) return '0:00';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
};
// Back-compat wrapper for existing callers; now uses the standard format.
export const fmtDate = (ts) => fmtDateTime(ts);
