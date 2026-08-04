// Sound-on-complete player (Stage 2).
// Uses a single reusable Audio element. Browser autoplay policies require a
// user gesture before audio can play, so the audio context is unlocked on the
// first pointer/keydown anywhere in the app (see unlockAudio below).

let audioEl = null;
let unlocked = false;

function ensureAudio() {
  if (!audioEl) {
    try {
      audioEl = new Audio();
      audioEl.preload = 'auto';
    } catch {
      audioEl = null;
    }
  }
  return audioEl;
}

// Call once on any user gesture to satisfy autoplay policies. Safe to call
// repeatedly; audio playback never blocks the UI.
export function unlockAudio() {
  const el = ensureAudio();
  if (el) {
    unlocked = true;
    try { el.load(); } catch { /* ignore */ }
  }
}

export function playSound(src) {
  const el = ensureAudio();
  if (!el || !unlocked) return; // wait for a user gesture first
  try {
    el.src = src;
    el.play().catch(() => { /* autoplay may still be blocked; non-blocking */ });
  } catch {
    /* ignore */
  }
}

// Trigger playback for an SSE 'done' event based on the current settings.
export function playJobSound(data, settings) {
  if (!data || data.type !== 'done') return;
  const failed = !!data.result && data.result.ok === false;
  const enabled = failed
    ? settings?.sound_on_error
    : settings?.sound_on_complete;
  if (!enabled) return;
  const asset = settings?.sound_asset_complete || 'sounds/job-done.wav';
  playSound(asset);
}
