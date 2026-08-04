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

  previewPath: (body) => req('POST', '/api/preview-path', body),

  artistExclusivity: () => req('POST', '/api/run/artist-exclusivity'),
  resolveArtistExclusivity: (body) => req('POST', '/api/run/resolve-artist-exclusivity', body),
  extractMove: (body) => req('POST', '/api/run/library_extract_move', body),

  tagList: (paths) => req('POST', '/api/tag-list', { paths }),
  tagRead: (paths) => req('POST', '/api/tag-read', { paths }),
  tagSave: (paths, field, value) => req('POST', '/api/tag-save', { paths, field, value }),

  plex: {
    status: () => req('POST', '/api/plex/status'),
    stats: () => req('POST', '/api/plex/stats'),
    search: (query) => req('POST', '/api/plex/search', { query }),
    rate: (query, rating) => req('POST', '/api/plex/rate', { query, rating }),
    duplicates: () => req('POST', '/api/plex/duplicates'),
    syncRatings: () => req('POST', '/api/plex/sync-ratings'),
    syncStatus: () => req('GET', '/api/plex/sync-status'),
  },
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
export const fmtDate = (ts) => {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString();
};
