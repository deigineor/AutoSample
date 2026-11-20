import numpy as np
import pytest

from autosample.dsp import db2lin, find_loop, lin2db, process
from autosample.settings import Settings

SR = 48000


def test_db_conversion():
    assert db2lin(0) == pytest.approx(1.0)
    assert db2lin(-20) == pytest.approx(0.1)
    assert lin2db(0.5) == pytest.approx(-6.0206, abs=1e-3)
    assert lin2db(db2lin(-37.5)) == pytest.approx(-37.5)
    assert lin2db(0) < -200  # clamped, no -inf


def _recording(lead=0.2, tone=1.5, tail=0.5, freq=220.0, amp=0.5):
    n_lead, n_tone, n_tail = (int(x * SR) for x in (lead, tone, tail))
    t = np.arange(n_tone) / SR
    sine = amp * np.sin(2 * np.pi * freq * t)
    x = np.concatenate([np.zeros(n_lead), sine, np.zeros(n_tail)]).astype(np.float32)
    return x[:, None], n_lead, n_lead + n_tone


def test_process_trims_silence_both_ends():
    raw, on, off = _recording()
    s = Settings(trim_start=True, trim_end=True, normalize="off", auto_loop=False)
    out, info = process(raw, SR, s, on, off)
    assert 0 < len(out) < len(raw)
    # leading silence is gone (start within ~a block of the first sound), trailing 0.5 s too
    assert abs(info["start"] - on) < 600
    assert len(out) == pytest.approx(1.5 * SR, abs=0.02 * SR)
    assert info["peak"] == pytest.approx(0.5, abs=0.05)


def test_process_normalize_sample():
    raw, on, off = _recording(amp=0.25)
    s = Settings(normalize="sample", normalize_db=-1.0, auto_loop=False)
    _, info = process(raw, SR, s, on, off)
    assert info["peak"] == pytest.approx(db2lin(-1.0), abs=1e-3)


def test_process_empty_input():
    out, info = process(np.zeros((0, 2), np.float32), SR, Settings(), 0, 0)
    assert out.shape[0] == 0 and info["peak"] == 0.0


def test_find_loop_points_in_range():
    raw, on, off = _recording(tone=3.0, tail=0.0)
    x = raw.copy()
    loop = find_loop(x, SR, off, 0.5, int(0.03 * SR))
    assert loop is not None
    ls, le = loop
    assert 0 <= ls < le < len(x)
    assert le - ls >= 0.5 * SR - 1


def test_find_loop_too_short_returns_none():
    raw, on, off = _recording(lead=0.0, tone=0.2, tail=0.0)
    assert find_loop(raw.copy(), SR, off, 0.5, 0) is None
