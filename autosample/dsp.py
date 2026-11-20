"""Processing of recorded samples: DC removal, trims, fades, normalization, loop search."""
from __future__ import annotations

import numpy as np

from .settings import Settings


def db2lin(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def lin2db(x: float) -> float:
    return float(20.0 * np.log10(max(float(x), 1e-12)))


def peak(x: np.ndarray) -> float:
    return float(np.abs(x).max()) if x.size else 0.0


def process(raw: np.ndarray, sr: int, s: Settings, on_frame: int, off_frame: int):
    """Returns (processed audio, info dict with loop/noteoff/peak/start)."""
    x = np.array(raw, dtype=np.float32, copy=True)
    info = {"loop": None, "noteoff": off_frame, "start": 0}
    if x.shape[0] == 0:
        info["peak"] = info["raw_peak"] = 0.0
        return x, info

    if s.remove_dc:
        # estimate DC from the pre-roll (silence before the note) if present, otherwise from the whole take
        ref = x[: max(on_frame - 64, 0)]
        x -= (ref if len(ref) > 256 else x).mean(axis=0)

    env = np.abs(x).max(axis=1)
    n = len(x)

    # ---- start ----
    latency = int(s.latency_ms * sr / 1000)
    if s.trim_start:
        search_from = max(0, on_frame - 2 * 256)
        above = np.nonzero(env[search_from:] > db2lin(s.trim_start_db))[0]
        if len(above):
            start = max(0, search_from + int(above[0]) - int(s.pre_attack_ms * sr / 1000))
        else:
            start = min(n - 1, on_frame + latency)
    else:
        start = min(n - 1, max(0, on_frame + latency))
    x = x[start:]
    env = env[start:]
    off = max(0, off_frame - start)
    info["start"] = start
    info["noteoff"] = off

    # ---- end ----
    if s.trim_end and len(x):
        above = np.nonzero(env > db2lin(s.trim_end_db))[0]
        if len(above):
            end = min(len(x), int(above[-1]) + 1 + int(0.002 * sr))
            x = x[:max(end, int(0.01 * sr))]

    # ---- loop ----
    if s.auto_loop and len(x):
        fade_out_n = int(s.fade_out_ms * sr / 1000)
        loop = find_loop(x, sr, min(off, len(x) - fade_out_n - 1), s.loop_min_s,
                         int(s.loop_xfade_ms * sr / 1000))
        info["loop"] = loop

    # ---- fades ----
    fi = min(len(x), int(s.fade_in_ms * sr / 1000))
    if fi > 1:
        x[:fi] *= np.linspace(0.0, 1.0, fi, dtype=np.float32)[:, None]
    fo = min(len(x), int(s.fade_out_ms * sr / 1000))
    if fo > 1:
        x[-fo:] *= np.linspace(1.0, 0.0, fo, dtype=np.float32)[:, None] ** 2

    info["raw_peak"] = peak(x)
    if s.normalize == "sample":
        pk = info["raw_peak"]
        if pk > 1e-6:
            x *= db2lin(s.normalize_db) / pk
    info["peak"] = peak(x)
    return x, info


def find_loop(x: np.ndarray, sr: int, noteoff: int, min_s: float, xfade: int):
    """Looks for loop points in the sustained part of the sound (between the attack and note-off).
    Returns (start, end_inclusive) or None. If xfade>0, bakes the crossfade into x."""
    mono = x.mean(axis=1)
    n = len(mono)
    W = max(256, int(0.02 * sr))
    region_end = min(noteoff, n) - int(0.02 * sr)
    region_start = int(max(0.15 * sr, 0.25 * noteoff, W, xfade))
    min_len = int(min_s * sr)
    if region_end - region_start < min_len + W:
        return None

    zc = np.nonzero((mono[:-1] <= 0) & (mono[1:] > 0))[0] + 1
    ends = zc[(zc <= region_end) & (zc + W <= n)]
    if not len(ends):
        return None
    le = int(ends[-1])

    cands = zc[(zc >= region_start) & (zc <= le - min_len)]
    if not len(cands):
        return None
    if len(cands) > 3000:
        cands = cands[np.linspace(0, len(cands) - 1, 3000).astype(int)]

    def _norm(m):
        m = m - m.mean(axis=-1, keepdims=True)
        return m / (np.linalg.norm(m, axis=-1, keepdims=True) + 1e-9)

    offs = np.arange(-W, W)
    segs = mono[cands[:, None] + offs[None, :]]
    ref = mono[le + offs]
    pre = (_norm(segs[:, :W]) * _norm(ref[:W])).sum(axis=1)
    post = (_norm(segs[:, W:]) * _norm(ref[W:])).sum(axis=1)
    rms_c = np.sqrt((segs ** 2).mean(axis=1)) + 1e-9
    rms_r = np.sqrt((ref ** 2).mean()) + 1e-9
    score = pre + post - 0.5 * np.abs(np.log(rms_c / rms_r))
    # small bonus for longer loops
    score += 0.05 * (le - cands) / max(1, le - region_start)
    ls = int(cands[int(np.argmax(score))])

    if xfade > 1 and ls - xfade >= 0:
        a = np.linspace(0.0, 1.0, xfade, dtype=np.float32)[:, None]
        tail = x[le - xfade:le].copy()
        head = x[ls - xfade:ls]
        x[le - xfade:le] = tail * np.sqrt(1 - a) + head * np.sqrt(a)
    return ls, le - 1
