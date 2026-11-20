import numpy as np
import pytest

from autosample.pitch import detect_pitch

SR = 48000


def _sine(f, dur=1.0):
    return np.sin(2 * np.pi * f * np.arange(int(dur * SR)) / SR).astype(np.float32) * 0.5


@pytest.mark.parametrize("freq,midi", [(440.0, 69), (261.6256, 60), (110.0, 45)])
def test_detect_pitch_sine(freq, midi):
    m, conf = detect_pitch(_sine(freq), SR)
    assert m == pytest.approx(midi, abs=0.1)
    assert conf > 0.5


def test_detect_pitch_stereo_input():
    x = np.stack([_sine(440.0)] * 2, axis=1)
    assert detect_pitch(x, SR)[0] == pytest.approx(69, abs=0.1)


def test_detect_pitch_silence_and_noise():
    assert detect_pitch(np.zeros(SR, np.float32), SR) == (None, 0.0)
    noise = np.random.default_rng(0).uniform(-0.5, 0.5, SR).astype(np.float32)
    assert detect_pitch(noise, SR)[0] is None
