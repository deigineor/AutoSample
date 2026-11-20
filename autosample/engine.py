"""Рушій семплування: окремий потік, що грає ноти, записує, обробляє і зберігає."""
from __future__ import annotations

import time
from dataclasses import dataclass, replace

from PySide6.QtCore import QThread, Signal

from . import dsp
from .audio import AudioInput
from .export import SampleResult, instrument_dir, sample_filename, write_mappings
from .midi import MidiOut, set_timer_resolution
from .pitch import detect_pitch
from .settings import Settings, note_name
from .wavfile import read_wav, write_wav


@dataclass
class Job:
    program: int | None
    note: int
    vel: int
    rr: int
    expr: int | None = None   # значення aftertouch/CC для шару експресії
    art: str = ""             # "" = звичайна нота, "swell" = свел


def build_jobs(s: Settings) -> list[Job]:
    jobs = []
    vels = s.velocity_list()
    for prog in s.programs():
        for note in s.notes():
            for vel in vels:
                for expr in s.expr_list():
                    for rr in range(1, max(1, s.round_robins) + 1):
                        jobs.append(Job(prog, note, vel, rr, expr))
        if s.swell_on:
            for note in s.notes():
                jobs.append(Job(prog, note, vels[-1], 1, None, "swell"))
    return jobs


def expr_label(s: Settings, expr, art="") -> str:
    if art == "swell":
        src = "AT" if s.swell_source == "aftertouch" else f"CC{s.expr_cc}"
        return f"Свел {src} {s.swell_from}→{s.swell_to}"
    if expr is None:
        return "—"
    return f"AT {expr}" if s.expr_mode == "aftertouch" else f"CC{s.expr_cc} {expr}"


class SamplingEngine(QThread):
    progress = Signal(int, int, float)       # готово, всього, ETA (с)
    sampleDone = Signal(object)              # SampleResult
    noteActive = Signal(int)                 # нота, що звучить (-1 = жодна)
    message = Signal(str, str)               # рівень (info/ok/warn/err), текст
    finishedRun = Signal(bool)               # True = завершено повністю

    def __init__(self, s: Settings, audio: AudioInput, midi: MidiOut, jobs: list[Job],
                 existing: dict, parent=None):
        super().__init__(parent)
        self.s = s
        self.audio = audio
        self.midi = midi
        self.jobs = jobs
        self.existing = dict(existing)       # key -> SampleResult (зі старих проходів)
        self._stop = False
        self._shifts: list[int] = []
        self.phase = ""

    def stop(self):
        self._stop = True

    # ------------------------------------------------------------------
    def _wait(self, seconds: float) -> bool:
        end = time.perf_counter() + max(0.0, seconds)
        while True:
            if self._stop:
                return False
            rem = end - time.perf_counter()
            if rem <= 0:
                return True
            time.sleep(min(0.005, rem))

    def _log(self, text, level="info"):
        self.message.emit(level, text)

    # ------------------------------------------------------------------
    def run(self):
        set_timer_resolution(True)
        ok = False
        try:
            ok = self._run()
        except Exception as e:  # noqa: BLE001
            self._log(f"Помилка: {e}", "err")
        finally:
            try:
                self.midi.panic()
            except Exception:
                pass
            self.noteActive.emit(-1)
            set_timer_resolution(False)
            self.finishedRun.emit(ok)

    def _run(self) -> bool:
        s = self.s
        ch = s.midi_channel
        sr = self.audio.sr
        total = len(self.jobs)
        new_results: list[SampleResult] = []
        t0 = time.perf_counter()
        current_prog = object()

        for i, job in enumerate(self.jobs):
            if self._stop:
                self._log("Зупинено користувачем.", "warn")
                return False

            if job.program is not None and job.program != current_prog:
                self.midi.program_change(ch, job.program - 1, s.bank_msb, s.bank_lsb)
                self._log(f"Program Change → {job.program}", "info")
                current_prog = job.program
                if not self._wait(s.program_wait_s):
                    continue

            label = f"{note_name(job.note, s.note_names_c3)} v{job.vel} rr{job.rr}"
            if job.expr is not None or job.art:
                label += f" [{expr_label(s, job.expr, job.art)}]"
            if job.program is not None:
                label = f"P{job.program:03d} " + label
            swell = job.art == "swell"
            use_at = (job.expr is not None and s.expr_mode == "aftertouch") or (swell and s.swell_source == "aftertouch")
            use_cc_swell = swell and s.swell_source == "cc"

            # CC виставляємо ДО ноти, щоб синт встиг відреагувати
            pre_cc = None
            if job.expr is not None and s.expr_mode == "cc":
                pre_cc = job.expr
            elif use_cc_swell:
                pre_cc = s.swell_from
            if pre_cc is not None:
                self.midi.cc(ch, s.expr_cc, pre_cc)
                if not self._wait(s.expr_settle_ms / 1000):
                    break
            self.noteActive.emit(job.note)

            # --- запис ---
            self.audio.begin_capture()
            if not self._wait(s.preroll_ms / 1000):
                break
            on_frame = self.audio.captured_frames()
            self.midi.note_on(ch, job.note, job.vel)
            if job.expr is not None and s.expr_mode == "aftertouch":
                self.midi.aftertouch(ch, job.expr)
            completed = self._swell(ch) if swell else self._wait(s.hold_s)
            off_frame = self.audio.captured_frames()
            self.midi.note_off(ch, job.note)
            if use_at:
                self.midi.aftertouch(ch, 0)
            if use_cc_swell:
                self.midi.cc(ch, s.expr_cc, s.swell_from)
            self.noteActive.emit(-1)
            if not completed:
                self.audio.end_capture()
                break

            if s.release_mode == "fixed":
                if not self._wait(s.release_s):
                    self.audio.end_capture()
                    break
            else:
                if not self._wait_silence():
                    self.audio.end_capture()
                    break
            raw = self.audio.end_capture()

            # --- обробка ---
            ps = replace(s, auto_loop=False) if swell else s   # свел не лупимо — рух же
            y, info = dsp.process(raw, sr, ps, on_frame, off_frame)
            if len(y) == 0 or info["raw_peak"] < 1e-5:
                self._log(f"{label}: тиша — перевір вхід/MIDI.", "warn")
            clipped = dsp.peak(raw) >= 0.999
            if clipped:
                self._log(f"{label}: КЛІП на вході! Зменш рівень.", "err")

            # --- реальна висота тону ---
            off = info["noteoff"]
            detected, conf = detect_pitch(y, sr, min(int(0.05 * sr), off // 4), off)
            if conf < 0.6:
                detected = None
            root = job.note
            if detected is not None:
                shift = detected - job.note
                if abs(shift) >= 0.5:
                    self._shifts.append(round(shift))
                    if len(self._shifts) <= 3:
                        self._log(f"{label}: надіслано {note_name(job.note, s.note_names_c3)} ({job.note}), "
                                  f"а звучить {note_name(round(detected), s.note_names_c3)} "
                                  f"({shift:+.1f} півт.)", "warn")
                if s.root_mode != "midi" and 0 <= round(detected) <= 127:
                    root = int(round(detected))

            inst = instrument_dir(s, job.program)
            path = inst / "Samples" / sample_filename(s, job.program, job.note, job.vel, job.rr, job.expr, job.art)
            write_wav(path, y, sr, s.bit_depth, root_note=root, loop=info["loop"])
            res = SampleResult(job.program, job.note, job.vel, job.rr, str(path), len(y), sr,
                               dsp.lin2db(info["peak"]), info["raw_peak"],
                               dsp.lin2db(info["peak"] / info["raw_peak"]) if info["raw_peak"] > 1e-9 else 0.0,
                               info["loop"], clipped, detected, root, job.expr, job.art)
            new_results.append(res)
            self.existing[res.key] = res
            self.sampleDone.emit(res)

            done = i + 1
            el = time.perf_counter() - t0
            self.progress.emit(done, total, el / done * (total - done))
            self._log(f"{label}  ✓  {len(y) / sr:.2f} с, пік {res.peak_db:.1f} dB"
                      + ("  ⟲ луп" if info["loop"] else ""), "ok")

            if not self._wait(s.gap_ms / 1000):
                break

        if self._stop:
            self._log("Зупинено користувачем.", "warn")
        complete = not self._stop
        self._report_shifts(len(new_results))

        # --- нормалізація по інструменту ---
        if s.normalize == "instrument" and new_results:
            self._normalize_instrument(new_results)

        # --- мапінг ---
        progs = sorted({r.program for r in self.existing.values()}, key=lambda p: -1 if p is None else p)
        for p in progs:
            files = write_mappings(s, p, list(self.existing.values()))
            for f in files:
                self._log(f"Збережено: {f}", "info")
        return complete

    def _swell(self, ch: int) -> bool:
        """Тримає ноту й плавно веде aftertouch/CC від swell_from до swell_to."""
        s = self.s
        if s.swell_source == "aftertouch":
            def send(v):
                self.midi.aftertouch(ch, v)
        else:
            def send(v):
                self.midi.cc(ch, s.expr_cc, v)
        t0 = time.perf_counter()
        send(s.swell_from)
        if not self._wait(s.swell_delay_s):
            return False
        ramp = max(0.01, s.swell_ramp_s)
        tr = time.perf_counter()
        last = s.swell_from
        while True:
            if self._stop:
                return False
            k = min(1.0, (time.perf_counter() - tr) / ramp)
            v = int(round(s.swell_from + (s.swell_to - s.swell_from) * k))
            if v != last:
                send(v)
                last = v
            if k >= 1.0:
                break
            time.sleep(0.004)
        return self._wait(s.swell_hold_s() - (time.perf_counter() - t0))

    def _report_shifts(self, n: int):
        if not self._shifts:
            return
        common = max(set(self._shifts), key=self._shifts.count)
        cnt = self._shifts.count(common)
        if cnt >= max(2, n // 2):
            oct_txt = f" ({common / 12:+g} окт.)" if common % 12 == 0 else ""
            fix = ("Root note вже виставлено за реальною висотою — інструмент гратиме правильно."
                   if self.s.root_mode != "midi" else
                   "Перевір Octave / Transpose на синті, або в «Обробка → Висота тону» вибери "
                   "«За реальною висотою», і перезапиши.")
            self._log(f"Синт стабільно звучить на {common:+d} півт.{oct_txt} відносно надісланих нот "
                      f"({cnt} із {n} семплів). {fix}", "warn")
        else:
            self._log(f"У {len(self._shifts)} семплах висота відрізняється від надісланої ноти.", "warn")

    def _wait_silence(self) -> bool:
        s = self.s
        start = time.perf_counter()
        quiet_since = None
        if not self._wait(0.05):
            return False
        while time.perf_counter() - start < s.release_max_s:
            if self._stop:
                return False
            if self.audio.rms_db < s.silence_db:
                quiet_since = quiet_since or time.perf_counter()
                if time.perf_counter() - quiet_since >= 0.15:
                    return True
            else:
                quiet_since = None
            time.sleep(0.005)
        return True

    def _normalize_instrument(self, new_results: list[SampleResult]):
        s = self.s
        target = dsp.db2lin(s.normalize_db)
        new_keys = {r.key for r in new_results}
        by_prog: dict = {}
        for r in new_results:
            by_prog.setdefault(r.program, []).append(r)
        for prog, items in by_prog.items():
            old = [r for r in self.existing.values() if r.program == prog and r.key not in new_keys]
            if old:
                gain_db = old[0].gain_db          # тримаємо ту саму гучність, що й решта інструмента
            else:
                pk = max(r.raw_peak for r in items)
                gain_db = dsp.lin2db(target / pk) if pk > 1e-6 else 0.0
            g = dsp.db2lin(gain_db)
            for r in items:
                data, sr, meta = read_wav(r.path)
                data = data * g
                write_wav(r.path, data, sr, s.bit_depth, root_note=r.root_note, loop=r.loop)
                r.gain_db = gain_db
                r.peak_db = dsp.lin2db(dsp.peak(data))
                self.existing[r.key] = r
                self.sampleDone.emit(r)
            self._log(f"Нормалізація інструмента: {gain_db:+.1f} dB", "info")
