"""Audio: input (level meter + sample capture), input monitoring and sample playback.

If the output is the same device as the input (or both are ASIO), ONE duplex stream is opened.
This matters for ASIO: the driver takes the device exclusively, and a separate MME/WASAPI output
on the same sound card simply stays silent."""
from __future__ import annotations

import threading

import numpy as np
import sounddevice as sd

from .i18n import tr


def _api_names():
    return [a["name"] for a in sd.query_hostapis()]


def input_devices() -> list[dict]:
    apis = _api_names()
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            out.append(dict(index=i, label=f"{apis[d['hostapi']]} · {d['name']}",
                            channels=int(d["max_input_channels"]), sr=d["default_samplerate"]))
    return out


def output_devices() -> list[dict]:
    apis = _api_names()
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_output_channels"] > 0:
            out.append(dict(index=i, label=f"{apis[d['hostapi']]} · {d['name']}",
                            channels=int(d["max_output_channels"])))
    return out


def _resample(x: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    if sr_from == sr_to or len(x) < 2:
        return x
    n = int(round(len(x) * sr_to / sr_from))
    t_new = np.linspace(0, len(x) - 1, n)
    t_old = np.arange(len(x))
    return np.stack([np.interp(t_new, t_old, x[:, c]) for c in range(x.shape[1])], axis=1).astype(np.float32)


class AudioInput:
    BLOCK = 256

    def __init__(self):
        self.stream = None            # input or duplex stream
        self.out_stream = None        # separate output stream (if not duplex)
        self._lock = threading.Lock()
        self._capturing = False
        self._chunks: list[np.ndarray] = []
        self._captured = 0
        self._peak = np.zeros(2, dtype=np.float32)
        self._rms_db = -120.0
        self.sr = 48000
        self.nch = 2
        self._sel = slice(0, 2)
        self.xruns = 0
        self.device_label = ""
        # output
        self.duplex = False
        self.out_sr = 48000
        self.out_ch = 2
        self.out_info = ""
        self.out_error = ""
        self.monitor = False
        self.monitor_gain = 1.0
        self._play: np.ndarray | None = None
        self._play_pos = 0
        self._ring = np.zeros((1, 2), np.float32)
        self._rw = 0
        self._rr = 0

    @property
    def running(self) -> bool:
        return self.stream is not None and self.stream.active

    @property
    def has_output(self) -> bool:
        return self.duplex or self.out_stream is not None

    # ------------------------------------------------------------------
    def start(self, device: int, sr: int, first_ch: int, nch: int, out_device: int | None = None):
        """first_ch is the 0-based index of the first channel, nch is 1 or 2.
        out_device is the output device index or None (no output)."""
        self.stop()
        self.sr, self.nch = int(sr), int(nch)
        self._sel = slice(first_ch, first_ch + nch)
        self._peak = np.zeros(nch, dtype=np.float32)
        self.xruns = 0
        self.out_error = ""
        self.out_info = ""
        self.duplex = False

        apis = _api_names()
        in_info = sd.query_devices(device)
        in_api = apis[in_info["hostapi"]]
        out_info = sd.query_devices(out_device) if out_device is not None else None
        use_duplex = out_info is not None and (
            out_device == device or (in_api == "ASIO" and apis[out_info["hostapi"]] == "ASIO"))

        if use_duplex:
            self.out_ch = max(1, min(2, int(out_info["max_output_channels"])))
            try:
                self.stream = sd.Stream(device=(device, out_device), channels=(first_ch + nch, self.out_ch),
                                        samplerate=self.sr, dtype="float32", blocksize=self.BLOCK,
                                        latency="low", callback=self._duplex_cb)
                self.stream.start()
                self.duplex = True
                self.out_sr = self.sr
                self.out_info = f"{apis[out_info['hostapi']]} · {out_info['name']}"
                return
            except Exception as e:  # noqa: BLE001
                self.stream = None
                self.out_error = tr("Duplex failed ({e}); output disabled.", e=e)
                out_device = None

        self.stream = sd.InputStream(device=device, channels=first_ch + nch, samplerate=self.sr,
                                     dtype="float32", blocksize=self.BLOCK, latency="low",
                                     callback=self._in_cb)
        self.stream.start()

        if out_device is not None:
            self.out_ch = max(1, min(2, int(out_info["max_output_channels"])))
            for rate in (self.sr, int(out_info["default_samplerate"])):
                try:
                    self.out_stream = sd.OutputStream(device=out_device, channels=self.out_ch, samplerate=rate,
                                                      dtype="float32", blocksize=self.BLOCK, latency="low",
                                                      callback=self._out_cb)
                    self.out_stream.start()
                    self.out_sr = rate
                    self.out_info = f"{apis[out_info['hostapi']]} · {out_info['name']}"
                    break
                except Exception as e:  # noqa: BLE001
                    self.out_stream = None
                    self.out_error = str(e)
            if self.out_stream is None:
                hint = tr(" The input runs through ASIO, which takes the sound card exclusively — "
                          "choose the output \"Same as input\".") if in_api == "ASIO" else ""
                self.out_error = tr("Could not open the output: {error}.{hint}", error=self.out_error, hint=hint)
            else:
                self.out_error = ""
                self._ring = np.zeros((self.sr, self.out_ch), np.float32)
                self._rw = self._rr = 0

    def stop(self):
        for st in (self.stream, self.out_stream):
            if st is not None:
                try:
                    st.stop()
                    st.close()
                except Exception:
                    pass
        self.stream = None
        self.out_stream = None
        self.duplex = False
        with self._lock:
            self._capturing = False
            self._chunks = []
            self._play = None

    # ------------------------------------------------------------------
    def _handle_input(self, indata, frames, status):
        if status:
            self.xruns += 1
        x = indata[:, self._sel]
        pk = np.abs(x).max(axis=0)
        rms = float(np.sqrt(np.mean(np.square(x)))) if frames else 0.0
        with self._lock:
            np.maximum(self._peak, pk, out=self._peak)
            self._rms_db = 20.0 * np.log10(rms + 1e-12)
            if self._capturing:
                self._chunks.append(x.copy())
                self._captured += frames
        return x

    def _to_out(self, x: np.ndarray) -> np.ndarray:
        if x.shape[1] == self.out_ch:
            return x
        if x.shape[1] == 1:
            return np.repeat(x, self.out_ch, axis=1)
        return x.mean(axis=1, keepdims=True) if self.out_ch == 1 else x[:, :self.out_ch]

    def _mix_play(self, outdata, frames):
        with self._lock:
            buf = self._play
            if buf is None:
                return
            pos = self._play_pos
            n = min(frames, len(buf) - pos)
            if n > 0:
                outdata[:n] += buf[pos:pos + n]
            self._play_pos = pos + max(n, 0)
            if self._play_pos >= len(buf):
                self._play = None

    def _in_cb(self, indata, frames, t, status):
        x = self._handle_input(indata, frames, status)
        if self.monitor and self.out_stream is not None and self.out_sr == self.sr:
            y = self._to_out(x) * self.monitor_gain
            ring = self._ring
            n = len(ring)
            with self._lock:
                idx = (self._rw + np.arange(frames)) % n
                ring[idx] = y
                self._rw = (self._rw + frames) % n
                # do not let the latency build up (devices have different clocks)
                fill = (self._rw - self._rr) % n
                if fill > 4 * self.BLOCK:
                    self._rr = (self._rw - 2 * self.BLOCK) % n

    def _out_cb(self, outdata, frames, t, status):
        outdata.fill(0)
        if self.monitor and self.out_sr == self.sr:
            ring = self._ring
            n = len(ring)
            with self._lock:
                fill = (self._rw - self._rr) % n
                k = min(frames, fill)
                if k:
                    idx = (self._rr + np.arange(k)) % n
                    outdata[:k] = ring[idx]
                    self._rr = (self._rr + k) % n
        self._mix_play(outdata, frames)

    def _duplex_cb(self, indata, outdata, frames, t, status):
        x = self._handle_input(indata, frames, status)
        if self.monitor:
            outdata[:] = self._to_out(x) * self.monitor_gain
        else:
            outdata.fill(0)
        self._mix_play(outdata, frames)

    # ------------------------------------------------------------------
    def play(self, data: np.ndarray, sr: int):
        if not self.has_output:
            raise RuntimeError(self.out_error or tr("The playback output is not open"))
        if data.ndim == 1:
            data = data[:, None]
        buf = self._to_out(_resample(data.astype(np.float32), sr, self.out_sr))
        with self._lock:
            self._play = np.ascontiguousarray(buf, dtype=np.float32)
            self._play_pos = 0

    def stop_play(self):
        with self._lock:
            self._play = None

    def read_peaks(self) -> np.ndarray:
        with self._lock:
            p = self._peak.copy()
            self._peak[:] = 0
        return p

    @property
    def rms_db(self) -> float:
        return self._rms_db

    # ------------------------------------------------------------------
    def begin_capture(self):
        with self._lock:
            self._chunks = []
            self._captured = 0
            self._capturing = True

    def captured_frames(self) -> int:
        return self._captured

    def snapshot(self) -> list[np.ndarray]:
        with self._lock:
            return list(self._chunks) if self._capturing else []

    def end_capture(self) -> np.ndarray:
        with self._lock:
            self._capturing = False
            chunks, self._chunks = self._chunks, []
        if not chunks:
            return np.zeros((0, self.nch), dtype=np.float32)
        return np.concatenate(chunks, axis=0)
