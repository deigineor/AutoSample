"""WAV writing/reading (16/24-bit PCM, 32-bit float) with an smpl chunk (root note + loop)."""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

from .i18n import tr


def write_wav(path, data: np.ndarray, sr: int, bit_depth: str = "24",
              root_note: int | None = None, loop: tuple[int, int] | None = None):
    data = np.asarray(data, dtype=np.float32)
    if data.ndim == 1:
        data = data[:, None]
    frames, nch = data.shape

    if bit_depth == "32f":
        fmt_tag, bits = 3, 32
        payload = data.astype("<f4").tobytes()
    elif bit_depth == "16":
        fmt_tag, bits = 1, 16
        payload = np.clip(np.round(data * 32767.0), -32768, 32767).astype("<i2").tobytes()
    else:
        fmt_tag, bits = 1, 24
        ints = np.clip(np.round(data.astype(np.float64) * 8388607.0), -8388608, 8388607).astype("<i4")
        payload = ints.reshape(-1).view(np.uint8).reshape(-1, 4)[:, :3].tobytes()

    block_align = nch * bits // 8
    chunks = [b"fmt " + struct.pack("<IHHIIHH", 16, fmt_tag, nch, sr, sr * block_align, block_align, bits)]
    if fmt_tag == 3:
        chunks.append(b"fact" + struct.pack("<II", 4, frames))
    pad = b"\x00" if len(payload) % 2 else b""
    chunks.append(b"data" + struct.pack("<I", len(payload)) + payload + pad)

    if root_note is not None:
        loops = [loop] if loop else []
        body = struct.pack("<9I", 0, 0, int(1e9 / sr), int(root_note), 0, 0, 0, len(loops), 0)
        for i, (ls, le) in enumerate(loops):
            body += struct.pack("<6I", i, 0, int(ls), int(le), 0, 0)
        chunks.append(b"smpl" + struct.pack("<I", len(body)) + body)

    riff = b"WAVE" + b"".join(chunks)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", len(riff)) + riff)


def read_wav(path):
    """Returns (data float32 [frames, ch], sr, meta{root, loop})."""
    raw = Path(path).read_bytes()
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError(tr("Not a WAV file"))
    pos = 12
    fmt = None
    data_bytes = b""
    meta = {"root": None, "loop": None}
    while pos + 8 <= len(raw):
        cid = raw[pos:pos + 4]
        size = struct.unpack("<I", raw[pos + 4:pos + 8])[0]
        body = raw[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            fmt = list(struct.unpack("<HHIIHH", body[:16]))
            if fmt[0] == 0xFFFE and len(body) >= 26:  # WAVE_FORMAT_EXTENSIBLE
                fmt[0] = struct.unpack("<H", body[24:26])[0]
        elif cid == b"data":
            data_bytes = body
        elif cid == b"smpl" and len(body) >= 36:
            v = struct.unpack("<9I", body[:36])
            meta["root"] = v[3]
            if v[7] and len(body) >= 60:
                lp = struct.unpack("<6I", body[36:60])
                meta["loop"] = (lp[2], lp[3])
        pos += 8 + size + (size & 1)
    if fmt is None:
        raise ValueError(tr("No fmt chunk"))
    tag, nch, sr, _, _, bits = fmt
    if tag == 3 and bits == 32:
        x = np.frombuffer(data_bytes, dtype="<f4")
    elif bits == 16:
        x = np.frombuffer(data_bytes, dtype="<i2").astype(np.float32) / 32768.0
    elif bits == 24:
        b = np.frombuffer(data_bytes[: len(data_bytes) // 3 * 3], dtype=np.uint8).reshape(-1, 3)
        ints = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16))
        ints = np.where(ints & 0x800000, ints - 0x1000000, ints)
        x = ints.astype(np.float32) / 8388608.0
    elif bits == 32:
        x = np.frombuffer(data_bytes, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(tr("Unsupported bit depth: {bits}", bits=bits))
    x = x[: len(x) // nch * nch].reshape(-1, nch).astype(np.float32)
    return x, sr, meta
