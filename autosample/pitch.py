"""Визначення висоти тону (YIN) — щоб перевірити, що синт грає саме ту ноту, яку ми надіслали."""
from __future__ import annotations

import math

import numpy as np

FMIN, FMAX = 25.0, 4200.0


def freq_to_midi(f: float) -> float:
    return 69.0 + 12.0 * math.log2(f / 440.0)


def _yin_frame(x: np.ndarray, W: int, sr: int, thr: float = 0.15):
    x = x - x.mean()
    x2 = np.concatenate([[0.0], np.cumsum(x * x)])
    taus = np.arange(W)
    e0 = x2[W]
    et = x2[taus + W] - x2[taus]
    n = 1 << int(math.ceil(math.log2(3 * W)))
    r = np.fft.irfft(np.conj(np.fft.rfft(x[:W], n)) * np.fft.rfft(x, n), n)[:W]
    d = np.maximum(e0 + et - 2.0 * r, 0.0)
    cm = np.ones(W)
    cs = np.cumsum(d[1:])
    cm[1:] = d[1:] * np.arange(1, W) / np.maximum(cs, 1e-12)
    tmin = max(2, int(sr / FMAX))
    tmax = min(W - 2, int(sr / FMIN))
    seg = cm[tmin:tmax]
    below = np.nonzero(seg < thr)[0]
    if len(below):
        t = tmin + int(below[0])
        while t + 1 < tmax and cm[t + 1] < cm[t]:
            t += 1
    else:
        t = tmin + int(np.argmin(seg))
    a, b, c = cm[t - 1], cm[t], cm[t + 1]
    den = a - 2 * b + c
    tf = t + (0.5 * (a - c) / den if abs(den) > 1e-12 else 0.0)
    return sr / tf, float(b)


def detect_pitch(x: np.ndarray, sr: int, start: int = 0, end: int | None = None):
    """Повертає (midi_float, впевненість 0..1) або (None, 0) для безтональних звуків."""
    if x.ndim == 2:
        x = x.mean(axis=1)
    x = x.astype(np.float64)
    end = len(x) if end is None else min(end, len(x))
    W = int(sr / FMIN) + 2
    if end - start < 2 * W:
        start = max(0, end - 2 * W)
    if end - start < 2 * W:
        return None, 0.0
    starts = np.linspace(start, end - 2 * W, num=min(9, max(1, (end - start) // W))).astype(int)
    found = []
    for s0 in starts:
        fr = x[s0:s0 + 2 * W]
        if np.sqrt(np.mean(fr * fr)) < 1e-4:
            continue
        f, ap = _yin_frame(fr, W, sr)
        if ap < 0.3 and FMIN <= f <= FMAX:
            found.append(freq_to_midi(f))
    if len(found) < max(1, len(starts) // 3):
        return None, 0.0
    found = np.array(found)
    med = float(np.median(found))
    # частка кадрів, що погоджуються з медіаною в межах пів тону
    conf = float(np.mean(np.abs(found - med) < 0.5))
    return med, conf
