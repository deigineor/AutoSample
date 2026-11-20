import numpy as np
import pytest

from autosample.wavfile import read_wav, write_wav

SR = 48000
TOL = {"16": 1 / 32767, "24": 1 / 8388607, "32f": 0}


@pytest.mark.parametrize("depth", ["16", "24", "32f"])
@pytest.mark.parametrize("nch", [1, 2])
def test_roundtrip(tmp_path, depth, nch):
    t = np.arange(1000) / SR
    data = np.stack([0.5 * np.sin(2 * np.pi * 440 * t * (c + 1)) for c in range(nch)], axis=1).astype(np.float32)
    p = tmp_path / "a.wav"
    write_wav(p, data, SR, depth)
    out, sr, meta = read_wav(p)
    assert sr == SR
    assert out.shape == data.shape
    assert np.abs(out - data).max() <= TOL[depth] + 1e-7
    assert meta == {"root": None, "loop": None}


def test_smpl_root_and_loop(tmp_path):
    p = tmp_path / "a.wav"
    write_wav(p, np.zeros((500, 1), np.float32), SR, "24", root_note=60, loop=(100, 400))
    _, _, meta = read_wav(p)
    assert meta == {"root": 60, "loop": (100, 400)}


def test_root_without_loop(tmp_path):
    p = tmp_path / "a.wav"
    write_wav(p, np.zeros((500, 1), np.float32), SR, "16", root_note=72)
    assert read_wav(p)[2] == {"root": 72, "loop": None}


def test_read_rejects_non_wav(tmp_path):
    p = tmp_path / "x.wav"
    p.write_bytes(b"not a wav file at all")
    with pytest.raises(ValueError):
        read_wav(p)
