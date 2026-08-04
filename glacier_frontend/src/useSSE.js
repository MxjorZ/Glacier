import { useEffect, useRef, useState } from 'react';

// Connects to /api/events (SSE). Appends each event to a ring buffer and
// exposes the latest job-state snapshot + progress.
export function useSSE(onEvent) {
  const [events, setEvents] = useState([]);
  const [job, setJob] = useState({ running: false, job: null });
  const [progress, setProgress] = useState(null);
  const buffer = useRef([]);
  const cb = useRef(onEvent);
  cb.current = onEvent;

  useEffect(() => {
    let es;
    try {
      es = new EventSource('/api/events');
    } catch {
      return undefined;
    }
    es.onmessage = (e) => {
      let data;
      try { data = JSON.parse(e.data); } catch { return; }
      buffer.current = [...buffer.current.slice(-400), data];
      setEvents(buffer.current);
      if (data.type === 'job_state') setJob({ running: !!data.running, job: data });
      if (data.type === 'progress') setProgress(data);
      if (data.type === 'done') setProgress(null);
      if (data.type === 'connected') setProgress(null);
      if (cb.current) cb.current(data);
    };
    es.onerror = () => {
      // EventSource auto-reconnects; nothing to do.
    };
    return () => es.close();
  }, []);

  return { events, job, progress };
}
