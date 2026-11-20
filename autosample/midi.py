"""MIDI-вихід. На Windows — напряму через winmm (без зовнішніх залежностей),
на інших системах — через mido, якщо встановлено."""
from __future__ import annotations

import sys
import threading


class MidiOut:
    def __init__(self):
        self._lock = threading.Lock()
        self._handle = None
        self._mido_port = None
        self.port_name = ""

    # ------------------------------------------------------------------
    @staticmethod
    def list_ports() -> list[str]:
        if sys.platform == "win32":
            return _winmm_ports()
        try:
            import mido
            return list(mido.get_output_names())
        except Exception:
            return []

    @property
    def is_open(self) -> bool:
        return self._handle is not None or self._mido_port is not None

    def open(self, name: str):
        self.close()
        if not name:
            return
        ports = self.list_ports()
        if name not in ports:
            raise RuntimeError(f"MIDI-порт не знайдено: {name}")
        if sys.platform == "win32":
            import ctypes
            h = ctypes.c_void_p()
            res = _winmm().midiOutOpen(ctypes.byref(h), ports.index(name), 0, 0, 0)
            if res != 0:
                raise RuntimeError(f"Не вдалося відкрити MIDI-порт (код {res}). Можливо, він зайнятий іншою програмою.")
            self._handle = h
        else:
            import mido
            self._mido_port = mido.open_output(name)
        self.port_name = name

    def close(self):
        with self._lock:
            if self._handle is not None:
                w = _winmm()
                w.midiOutReset(self._handle)
                w.midiOutClose(self._handle)
                self._handle = None
            if self._mido_port is not None:
                self._mido_port.close()
                self._mido_port = None
            self.port_name = ""

    # ------------------------------------------------------------------
    def send(self, status: int, d1: int = 0, d2: int = 0, nbytes: int = 3):
        with self._lock:
            if self._handle is not None:
                msg = (status & 0xFF) | ((d1 & 0x7F) << 8) | ((d2 & 0x7F) << 16)
                _winmm().midiOutShortMsg(self._handle, msg)
            elif self._mido_port is not None:
                import mido
                data = [status & 0xFF, d1 & 0x7F, d2 & 0x7F][:nbytes]
                self._mido_port.send(mido.Message.from_bytes(data))

    def note_on(self, ch: int, note: int, vel: int):
        self.send(0x90 | ((ch - 1) & 0x0F), note, vel)

    def note_off(self, ch: int, note: int):
        self.send(0x80 | ((ch - 1) & 0x0F), note, 0)

    def cc(self, ch: int, num: int, val: int):
        self.send(0xB0 | ((ch - 1) & 0x0F), num, val)

    def aftertouch(self, ch: int, val: int):
        """Channel Pressure (моно-aftertouch)."""
        self.send(0xD0 | ((ch - 1) & 0x0F), val, 0, nbytes=2)

    def program_change(self, ch: int, program0: int, bank_msb: int = -1, bank_lsb: int = -1):
        if bank_msb >= 0:
            self.cc(ch, 0, bank_msb)
        if bank_lsb >= 0:
            self.cc(ch, 32, bank_lsb)
        self.send(0xC0 | ((ch - 1) & 0x0F), program0, 0, nbytes=2)

    def panic(self):
        for ch in range(1, 17):
            self.aftertouch(ch, 0)
            self.cc(ch, 64, 0)    # sustain off
            self.cc(ch, 123, 0)   # all notes off
            self.cc(ch, 120, 0)   # all sound off


# ----------------------------------------------------------------------
_WINMM = None


def _winmm():
    global _WINMM
    if _WINMM is None:
        import ctypes
        from ctypes import wintypes
        w = ctypes.WinDLL("winmm")
        w.midiOutGetNumDevs.restype = wintypes.UINT
        w.midiOutOpen.argtypes = [ctypes.POINTER(ctypes.c_void_p), wintypes.UINT,
                                  ctypes.c_size_t, ctypes.c_size_t, wintypes.DWORD]
        w.midiOutOpen.restype = wintypes.UINT
        w.midiOutShortMsg.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        w.midiOutShortMsg.restype = wintypes.UINT
        w.midiOutReset.argtypes = [ctypes.c_void_p]
        w.midiOutClose.argtypes = [ctypes.c_void_p]
        _WINMM = w
    return _WINMM


def _winmm_ports() -> list[str]:
    import ctypes
    from ctypes import wintypes

    class MIDIOUTCAPSW(ctypes.Structure):
        _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD),
                    ("vDriverVersion", wintypes.UINT), ("szPname", wintypes.WCHAR * 32),
                    ("wTechnology", wintypes.WORD), ("wVoices", wintypes.WORD),
                    ("wNotes", wintypes.WORD), ("wChannelMask", wintypes.WORD),
                    ("dwSupport", wintypes.DWORD)]

    w = _winmm()
    out = []
    for i in range(w.midiOutGetNumDevs()):
        caps = MIDIOUTCAPSW()
        if w.midiOutGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps)) == 0:
            name = caps.szPname
            # однакові імена робимо унікальними
            base, k = name, 2
            while name in out:
                name = f"{base} #{k}"
                k += 1
            out.append(name)
    return out


def set_timer_resolution(enable: bool):
    """Точніші sleep() на Windows (1 мс)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        w = ctypes.WinDLL("winmm")
        (w.timeBeginPeriod if enable else w.timeEndPeriod)(1)
    except Exception:
        pass
