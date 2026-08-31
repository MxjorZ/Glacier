import { useState } from 'react';
import { api } from './api.js';

// Runs a job through /api/run/<op> and awaits its completion via the shared
// api.runAndAwait poller. Returns { running, result, error, run }.
export function useJob() {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const run = async (op, body, { raw = false } = {}) => {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.runAndAwait(op, body);
      setResult(res);
      setRunning(false);
      if (raw) return { running: false, result: res, error: null };
      return res;
    } catch (e) {
      setError(e.message);
      setRunning(false);
      return { ok: false, error: e.message };
    }
  };

  return { running, result, error, run };
}
