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
    if (data.type === 'log') {
      addLog(data);
    }
    if (data.type === 'error') {
      const err = { id: Math.random().toString(36).slice(2), level: 'error', ...data };
      setErrors((prev) => [...prev.slice(-99), err]);
      addLog(err);
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
    es.onerror = () => {
      // EventSource auto-reconnects; record a disconnected log line so it shows
      // in the console's "Disconnected" category.
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

  // Error collector: dismiss one error (fix it on the fly, no log digging) or
  // clear the whole list.
  const dismissError = (id) => setErrors((prev) => prev.filter((e) => e.id !== id));
  const clearErrors = () => setErrors([]);

  return { events, jobs, progress, logs, errors, dismissError, clearErrors };
}
