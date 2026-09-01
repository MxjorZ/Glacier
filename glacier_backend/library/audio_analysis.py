"""Audio analysis backend: waveform, spectrum and spectrogram data.

Decodes any format Glacier supports through ffmpeg (no extra Python deps
beyond numpy) and produces render-ready data for the Audio Quality Analyzer:

  * waveform : per-bucket min/max peak pairs for the whole file (timeline)
  * spectrum  : full-range FFT magnitude spectrum, 0 Hz .. sample_rate/2
                (up to 40 kHz+ for high-rate files), in dB
  * spectrogram : time x frequency energy grid for the timeline heat view
  * loudness  : simple RMS peak/RMS levels

Everything is downsampled to compact arrays so a 10-minute FLAC ships a few
hundred KB of JSON instead of raw PCM.
"""

import json
import math
import shutil
import subprocess
import tempfile
import os
from pathlib import Path

from .. import events

try:
    import numpy as np
except ImportError:  # pragma: no nover
    np = None

# Analysis rate: 44.1 kHz is enough for a 0..22 kHz spectrum view (the audible
# range) and keeps decode size/time half of what 96 kHz would cost.
ANALYSIS_RATE = 44100
SPECTRUM_MAX_HZ = 22000
WAVEFORM_BUCKETS = 2048
SPECTRUM_BINS = 2048
SPECTROGRAM_FRAMES = 600
SPECTROGRAM_BINS = 256


def _ffmpeg_path():
    p = shutil.which("ffmpeg")
    if p:
        return p
    # Common sidecar install location on Windows dev machines.
    guess = Path.home() / "ffmpeg" / "bin" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    return str(guess) if guess.exists() else None


def ffmpeg_available():
    return _ffmpeg_path() is not None


# --- Automatic installation ------------------------------------------------
#
# Runs the platform's package manager in the background and reports back via
# the job system. Windows tries winget -> scoop -> choco (first one found);
# Linux tries the system package manager (apt/apk/dnf). We never fail hard —
# a missing manager just surfaces a clear error the UI can show.

def _install_commands_windows():
    """Yield (manager, argv) candidates for installing ffmpeg on Windows."""
    for mgr in ("winget", "scoop", "choco"):
        path = shutil.which(mgr)
        if not path:
            continue
        if mgr == "winget":
            # --accept flags keep it non-interactive; scope machine-wide.
            yield mgr, [path, "install", "--id", "Gyan.FFmpeg", "-e",
                        "--accept-source-agreements", "--accept-package-agreements"]
        elif mgr == "scoop":
            yield mgr, [path, "install", "ffmpeg"]
        else:
            yield mgr, [path, "install", "-y", "ffmpeg"]


def _install_commands_linux():
    for mgr, argv in (
        ("apt", ["apt-get", "install", "-y", "ffmpeg"]),
        ("apk", ["apk", "add", "--no-cache", "ffmpeg"]),
        ("dnf", ["dnf", "install", "-y", "ffmpeg"]),
    ):
        path = shutil.which(argv[0])
        if path:
            yield mgr, [path] + argv[1:]


def install_ffmpeg():
    """Install ffmpeg with the platform package manager. Blocking.

    Returns {"ok", "manager", "output"} — run this inside a job (the UI does).
    """
    import subprocess
    import stat as _stat

    if os.name == "nt":
        candidates = list(_install_commands_windows())
    else:
        candidates = list(_install_commands_linux())

    if not candidates:
        raise RuntimeError(
            "No package manager found (winget/scoop/choco on Windows, "
            "apt/apk/dnf on Linux). Install ffmpeg manually.")

    last_err = ""
    for mgr, argv in candidates:
        events.log(f"Installing ffmpeg via {mgr}…", "info")
        try:
            proc = subprocess.run(argv, capture_output=True, timeout=600)
        except subprocess.TimeoutExpired:
            last_err = f"{mgr}: install timed out"
            continue
        out = (proc.stdout or b"") + (proc.stderr or b"")
        text = out.decode("utf-8", "replace")[-2000:]
        if proc.returncode == 0 and ffmpeg_available():
            events.log(f"ffmpeg installed via {mgr}", "success")
            return {"ok": True, "manager": mgr, "output": text}
        last_err = f"{mgr} (exit {proc.returncode}): {text[-400:]}"

    raise RuntimeError(f"Automatic install failed. {last_err}")


def _decode(path, rate=ANALYSIS_RATE):
    """Decode any audio file to mono float32 PCM at ``rate`` via ffmpeg.

    Returns (numpy array, effective_rate) or (None, None).
    """
    ff = _ffmpeg_path()
    if not ff:
        return None, None
    cmd = [ff, "-v", "error", "-i", path, "-map", "a:0",
           "-ac", "1", "-ar", str(rate), "-f", "f32le", "-"]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=120)
    except subprocess.TimeoutExpired:
        events.log(f"Audio decode timed out: {path}", "warning")
        return None, None
    if not proc.stdout:
        # Surface ffmpeg's actual complaint so the user isn't left with a
        # generic "decode failed" for corrupt / frame-less files.
        err = (proc.stderr or b"").decode("utf-8", "replace").strip()
        events.log(f"Audio decode produced no samples for {os.path.basename(path)}"
                   + (f": {err}" if err else ""), "warning")
        return None, None
    if np is None:
        events.log("numpy is required for audio analysis", "error")
        return None, None
    return np.frombuffer(proc.stdout, dtype=np.float32), rate


def _db(mag):
    """Magnitude (linear) -> dBFS with a -120 dB floor."""
    if np is None:
        return []
    floor = 1e-6
    m = np.maximum(mag, floor)
    return np.round(20.0 * np.log10(m), 2)


def analyze(path, want_spectrogram=True):
    """Analyze one audio file. Returns a compact, JSON-ready dict."""
    samples, rate = _decode(path)
    if samples is None or len(samples) == 0:
        return {"ok": False, "error": "decode failed (ffmpeg missing or file unreadable)"}

    n = len(samples)
    duration = n / float(rate)

    # --- Waveform (timeline) ---------------------------------------------
    bucket = max(1, n // WAVEFORM_BUCKETS)
    usable = n - (n % bucket)
    if usable > 0:
        frames = samples[:usable].reshape(-1, bucket)
        peaks_min = frames.min(axis=1)
        peaks_max = frames.max(axis=1)
    else:
        peaks_min = peaks_max = samples[:1]

    # --- Spectrum (full range up to Nyquist, e.g. 0..48 kHz) --------------
    seg = samples[: 1 << 20] if n > (1 << 20) else samples  # cap FFT size at 1M
    spec_len = 1
    while spec_len * 2 <= len(seg):
        spec_len *= 2
    windowed = seg[:spec_len] * np.hanning(spec_len)
    fft = np.abs(np.fft.rfft(windowed)) / (spec_len / 2)
    freqs = np.fft.rfftfreq(spec_len, 1.0 / rate)
    db = _db(fft)

    # Smooth-resolve the spectrum to SPECTRUM_BINS linear buckets covering
    # 0 .. 22 kHz (audible range) — higher content is beyond hearing anyway.
    max_hz = min(rate / 2, SPECTRUM_MAX_HZ)
    edges = np.linspace(0, max_hz, SPECTRUM_BINS + 1)
    spec_bins = []
    spec_freqs = []
    for i in range(SPECTRUM_BINS):
        lo, hi = edges[i], edges[i + 1]
        idx = np.where((freqs >= lo) & (freqs < hi))[0]
        val = float(db[idx].max()) if len(idx) else -120.0
        spec_bins.append(val)
        spec_freqs.append(round(float((lo + hi) / 2), 1))
    # DC bin is near-useless; keep it but floor it for display sanity.
    spec_bins[0] = max(spec_bins[0], -120.0)

    result = {
        "ok": True,
        "path": path,
        "sample_rate": rate,
        "duration": round(duration, 3),
        "waveform": {
            "min": [round(float(x), 4) for x in peaks_min],
            "max": [round(float(x), 4) for x in peaks_max],
            "buckets": int(len(peaks_min)),
        },
        "spectrum": {
            "freqs": spec_freqs,
            "db": [round(float(v), 2) for v in spec_bins],
            "nyquist": round(rate / 2, 1),
            "max_hz": round(max_hz, 1),
        },
    }

    # --- Levels -----------------------------------------------------------
    rms = math.sqrt(float(np.mean(np.square(samples))))
    result["levels"] = {
        "peak": round(float(np.max(np.abs(samples))), 4),
        "rms": round(rms, 5),
        "rms_db": round(20 * math.log10(max(rms, 1e-9)), 2),
    }

    # --- Spectrogram (timeline heat grid, 0..22 kHz) ------------------------
    if want_spectrogram:
        frame_size = 2048
        hop = max(1, n // SPECTROGRAM_FRAMES)
        win = np.hanning(frame_size)
        rows = []
        spec_max_hz = min(rate / 2, SPECTRUM_MAX_HZ)
        freq_edges = np.linspace(0, spec_max_hz, SPECTROGRAM_BINS + 1)
        fft_freqs = np.fft.rfftfreq(frame_size, 1.0 / rate)
        for start in range(0, max(1, n - frame_size), hop):
            block = samples[start:start + frame_size]
            if len(block) < frame_size:
                block = np.pad(block, (0, frame_size - len(block)))
            mag = np.abs(np.fft.rfft(block * win)) / (frame_size / 2)
            d = _db(mag)
            row = []
            for i in range(SPECTROGRAM_BINS):
                lo, hi = freq_edges[i], freq_edges[i + 1]
                idx = np.where((fft_freqs >= lo) & (fft_freqs < hi))[0]
                row.append(float(d[idx].max()) if len(idx) else -120.0)
            rows.append([round(v, 1) for v in row])
            if len(rows) >= SPECTROGRAM_FRAMES:
                break
        result["spectrogram"] = {
            "frames": rows,
            "frame_count": len(rows),
            "freq_bins": SPECTROGRAM_BINS,
            "max_hz": round(spec_max_hz, 1),
        }

    return result
