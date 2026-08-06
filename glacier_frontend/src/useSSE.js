import { useEffect, useRef, useState } from 'react';
import { api } from './api.js';

// Connects to /api/events (SSE) and tracks:
//  - events: raw ring buffer
//  - jobs:    { [jobId]: runningJob } — multiple jobs can run at once
//  - progress:{ [jobId]: {current,total,label,ts} } per job
//  - logs:    recent log events (incl. per-file "verbose" loads)
//  - errors:  dedicated error events (for the top-bar notification)
export function useSSE(onEvent) {
  const [events, setEvents] = useState([]);
  const [jobs, setJobs] = useState({});
  const [progress, setProgress] = useState({});
  const [logs, setLogs] = useState([]);
  const [errors, setErrors] = useState([]);
  const cb = useRef(onEvent);
  cb.current = onEvent;

  const addLog = useRef((entry) => {
    setLogs((prev) => [...prev.slice(-599), { id: Math.random().toString(36).slice(2), ...entry }]);
  }).current;
  const lastProg = useRef({});

  const apply = (data) => {
    setEvents((prev) => [...prev.slice(-499), data]);

    if (data.type === 'job_state') {
      const id = data.id;
      setJobs((prev) => {
        const next = { ...prev };
        if (data.running) next[id] = { ...data, running: true };
        else delete next[id];
        return next;
      });
    }
    if (data.type === 'progress' && data.job_id != null) {
      setProgress((prev) => ({ ...prev, [data.job_id]: data }));
      // Throttled progress -> log line (Progress category) at 10% boundaries and completion.
      const id = data.job_id;
      const tot = data.total || 0;
      const cur = data.current || 0;
      const bucket = tot ? Math.floor((cur / tot) * 10) : -1;
      const prevBucket = lastProg.current[id];
      if (bucket === 10 || prevBucket !== bucket) {
        lastProg.current[id] = bucket;
        if (cur >= tot || bucket >= prevBucket) {
          addLog({ type: 'progress', level: 'progress', message: `${data.label || 'Progress'}: ${cur}/${tot}`, ts: data.ts || Date.now() / 1000 });
        }
      }
    }
    if (data.type === 'done' && data.job_id != null) {
      setProgress((prev) => {
        const n = { ...prev };
        delete n[data.job_id];
        return n;
      });
      delete lastProg.current[data.job_id];
    }

    // ---- Capture all loggable events ----
    const loggableTypes = ['log', 'success', 'error', 'warning', 'info', 'verbose', 'connected', 'disconnected', 'progress'];
    if (data.type && loggableTypes.includes(data.type)) {
      // If it's a log, it already has message/level; use as is.
      // For success/error/warning, we may need to build a message.
      const entry = { ...data };
      // Ensure it has a level for categorization
      if (!entry.level) {
        // Map type to level: success->success, error->error, warning->warning, etc.
        const levelMap = {
          success: 'success',
          error: 'error',
          warning: 'warning',
          info: 'info',
          verbose: 'verbose',
          connected: 'connected',
          disconnected: 'disconnected',
        };
        entry.level = levelMap[data.type] || 'info';
      }
      if (!entry.message) {
        // If no message, use a default
        entry.message = data.label || data.msg || data.text || `Event: ${data.type}`;
      }
      // Ensure we have a timestamp
      if (!entry.ts) entry.ts = Date.now() / 1000;
      addLog(entry);
    }

    // Also capture dedicated error events (they come as type='error')
    if (data.type === 'error') {
      const err = { id: Math.random().toString(36).slice(2), level: 'error', ...data };
      setErrors((prev) => [...prev.slice(-99), err]);
      // Already added to logs via the general capture above, but we also update errors.
    }

    if (cb.current) cb.current(data);
  };

  useEffect(() => {
    let es;
    try {
      es = new EventSource('/api/events');
    } catch {
      return undefined;
    }
    es.onmessage = (e) => {
      let d;
      try { d = JSON.parse(e.data); } catch { return; }
      apply(d);
    };
    es.onopen = () => {
      addLog({ type: 'connected', level: 'connected', message: 'Live stream reconnected', ts: Date.now() / 1000 });
      api.currentJob().then((r) => {
        const arr = r?.jobs || [];
        if (arr.length) setJobs(Object.fromEntries(arr.map((j) => [j.id, { ...j, running: true }])));
      }).catch(() => {});
    };
    es.onerror = () => {
      addLog({ type: 'disconnected', level: 'disconnected', message: 'Live stream disconnected — reconnecting…', ts: Date.now() / 1000 });
    };
    addLog({ type: 'connected', level: 'connected', message: 'Connected to Glacier live stream', ts: Date.now() / 1000 });

    // Seed with any already-running jobs (page refresh mid-job).
    api.currentJob().then((r) => {
      const arr = r?.jobs || [];
      if (arr.length) setJobs(Object.fromEntries(arr.map((j) => [j.id, { ...j, running: true }])));
    }).catch(() => {});

    return () => es.close();
  }, []);

  const dismissError = (id) => setErrors((prev) => prev.filter((e) => e.id !== id));
  const clearErrors = () => setErrors([]);

  return { events, jobs, progress, logs, errors, dismissError, clearErrors };
}