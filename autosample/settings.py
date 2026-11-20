"""Sampling session settings + note/velocity utilities."""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, fields
from pathlib import Path

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


@dataclass
class Settings:
    # --- audio ---
    audio_device: str = ""
    sample_rate: int = 48000
    bit_depth: str = "24"          # "16" | "24" | "32f"
    stereo: bool = True
    first_channel: int = 1         # 1-based
    monitor_device: str = ""       # "" = same device as the input
    monitor_on: bool = False
    # --- MIDI ---
    midi_port: str = ""
    midi_channel: int = 1          # 1..16
    # --- notes ---
    note_start: int = 36
    note_end: int = 96
    note_step: int = 3
    velocities: str = "127"
    round_robins: int = 1
    hold_s: float = 3.0
    release_mode: str = "fixed"    # "fixed" | "silence"
    release_s: float = 2.0
    release_max_s: float = 10.0
    silence_db: float = -60.0
    preroll_ms: int = 100
    gap_ms: int = 300
    # --- expression: aftertouch / CC layers ---
    expr_mode: str = "off"         # "off" | "aftertouch" | "cc"
    expr_cc: int = 1               # CC number (for cc mode and for swell via CC)
    expr_values: str = "0, 64, 127"
    expr_settle_ms: int = 50       # pause after CC before the note
    expr_xfade_ctrl: str = "same"  # controller used to crossfade layers in the sampler: "same" | "cc1"
    # --- swell ---
    swell_on: bool = False
    swell_source: str = "aftertouch"   # "aftertouch" | "cc"
    swell_from: int = 0
    swell_to: int = 127
    swell_delay_s: float = 0.0
    swell_ramp_s: float = 3.0
    # --- programs ---
    send_program: bool = False
    bank_msb: int = -1             # -1 = do not send
    bank_lsb: int = -1
    program_start: int = 1         # 1..128
    program_end: int = 1
    program_wait_s: float = 1.0
    # --- processing ---
    trim_start: bool = True
    trim_start_db: float = -50.0
    pre_attack_ms: float = 1.0
    latency_ms: float = 0.0
    trim_end: bool = True
    trim_end_db: float = -60.0
    fade_in_ms: float = 0.5
    fade_out_ms: float = 30.0
    remove_dc: bool = True
    normalize: str = "off"         # "off" | "sample" | "instrument"
    normalize_db: float = -1.0
    root_mode: str = "midi"        # "midi" | "detect" | "detect_tune"
    auto_loop: bool = False
    loop_min_s: float = 0.5
    loop_xfade_ms: float = 30.0
    # --- export ---
    name: str = "MySynth"
    output_dir: str = ""
    naming: str = "{name}_{note}_v{vel}_rr{rr}"
    note_names_c3: bool = True     # True: C3 = 60 (Yamaha/Ableton), False: C4 = 60
    export_sfz: bool = True
    export_ds: bool = True
    # --- interface ---
    language: str = "en"           # "en" | "uk"

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Settings":
        s = cls()
        names = {f.name: f.type for f in fields(cls)}
        for k, v in (d or {}).items():
            if k in names:
                default = getattr(s, k)
                try:
                    if isinstance(default, bool):
                        v = bool(v)
                    elif isinstance(default, int):
                        v = int(v)
                    elif isinstance(default, float):
                        v = float(v)
                    else:
                        v = str(v)
                    setattr(s, k, v)
                except (TypeError, ValueError):
                    pass
        return s

    def save(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Settings":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    # ------------------------------------------------------------------
    def notes(self) -> list[int]:
        lo, hi = sorted((self.note_start, self.note_end))
        return list(range(lo, hi + 1, max(1, self.note_step)))

    def velocity_list(self) -> list[int]:
        return parse_velocities(self.velocities)

    def programs(self) -> list[int | None]:
        if not self.send_program:
            return [None]
        lo, hi = sorted((self.program_start, self.program_end))
        return list(range(lo, hi + 1))

    def expr_list(self) -> list[int | None]:
        if self.expr_mode == "off":
            return [None]
        return parse_values(self.expr_values, 0, 127) or [0, 127]

    def swell_hold_s(self) -> float:
        return max(self.hold_s, self.swell_delay_s + self.swell_ramp_s + 0.5)

    def main_samples(self) -> int:
        return (len(self.notes()) * len(self.velocity_list()) * len(self.expr_list())
                * max(1, self.round_robins) * len(self.programs()))

    def swell_samples(self) -> int:
        return len(self.notes()) * len(self.programs()) if self.swell_on else 0

    def total_samples(self) -> int:
        return self.main_samples() + self.swell_samples()

    def seconds_per_sample(self, hold: float | None = None) -> float:
        rel = self.release_s if self.release_mode == "fixed" else self.release_max_s * 0.5
        settle = self.expr_settle_ms / 1000 if self.expr_mode == "cc" else 0.0
        return (self.preroll_ms / 1000 + (self.hold_s if hold is None else hold) + rel
                + self.gap_ms / 1000 + settle + 0.05)

    def estimated_seconds(self) -> float:
        progs = self.programs()
        t = (self.main_samples() * self.seconds_per_sample()
             + self.swell_samples() * self.seconds_per_sample(self.swell_hold_s()))
        if progs[0] is not None:
            t += len(progs) * self.program_wait_s
        return t


# ----------------------------------------------------------------------
def default_output_dir() -> str:
    return str(Path.home() / "Music" / "AutoSample")


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "AutoSample"


def parse_velocities(text: str) -> list[int]:
    vals = set()
    for tok in re.split(r"[,\s;]+", text or ""):
        if not tok:
            continue
        try:
            v = int(float(tok))
        except ValueError:
            continue
        if 1 <= v <= 127:
            vals.add(v)
    return sorted(vals) or [127]


def parse_values(text: str, lo: int, hi: int) -> list[int]:
    vals = set()
    for tok in re.split(r"[,\s;]+", text or ""):
        try:
            v = int(float(tok))
        except ValueError:
            continue
        if lo <= v <= hi:
            vals.add(v)
    return sorted(vals)


def even_expr(n: int) -> list[int]:
    n = max(1, min(8, n))
    if n == 1:
        return [127]
    return [round(127 * i / (n - 1)) for i in range(n)]


def even_velocities(n: int) -> list[int]:
    n = max(1, min(16, n))
    return [max(1, round(127 * (i + 1) / n)) for i in range(n)]


def is_black(note: int) -> bool:
    return note % 12 in (1, 3, 6, 8, 10)


def note_name(note: int, c3: bool = True) -> str:
    octave = note // 12 - (2 if c3 else 1)
    return f"{NOTE_NAMES[note % 12]}{octave}"


def parse_note(text: str, c3: bool = True) -> int | None:
    text = text.strip().upper().replace("♯", "#")
    m = re.match(r"^([A-G])(#|B)?(-?\d+)", text)
    if m:
        base = NOTE_NAMES.index(m.group(1))
        if m.group(2) == "#":
            base += 1
        elif m.group(2) == "B":
            base -= 1
        n = (int(m.group(3)) + (2 if c3 else 1)) * 12 + base
        return n if 0 <= n <= 127 else None
    m = re.search(r"(\d+)", text)
    if m:
        n = int(m.group(1))
        return n if 0 <= n <= 127 else None
    return None


def safe_filename(s: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s).strip() or "sample"
