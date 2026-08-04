import { useState } from 'react';
import { api } from './api.js';

// Runs a job through /api/run/<op> and polls /api/jobs/history until a job
// with the matching id completes. Returns { running, result, error, run }.
export function useJob() {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const run = async (op, body, { raw = false } = {}) => {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const start = await api.run(op, body);
      const jobId = start?.job?.id;
      // Poll for completion.
      const deadline = 1000 * 60 * 30; // 30 min guard
      const t0 = Date.now();
      while (Date.now() - t0 < deadline) {
        await new Promise((r) => setTimeout(r, 500));
        const hist = await api.get('/api/jobs/history');
        if (jobId != null) {
          const done = (hist.jobs || []).find((j) => j.id === jobId && j.status !== 'running');
          if (done) {
            const res = done.result ?? done;
            setResult(res);
            setRunning(false);
            if (raw) return { running: false, result: res, error: null };
            return res;
          }
        } else {
          const done = (hist.jobs || []).filter((j) => j.status !== 'running').pop();
          if (done) {
            const res = done.result ?? done;
            setResult(res);
            setRunning(false);
            if (raw) return { running: false, result: res, error: null };
            return res;
          }
        }
      }
      throw new Error('Job timed out');
    } catch (e) {
      setError(e.message);
      setRunning(false);
      return { ok: false, error: e.message };
    }
  };

  return { running, result, error, run };
}
