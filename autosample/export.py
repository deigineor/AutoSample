"""Генерація мапінгу інструмента: SFZ та DecentSampler (.dspreset).

Шари експресії (aftertouch / CC) кросфейдяться між собою контролером.
Свел-артикуляція зберігається окремим інструментом «<назва> Swell»."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import quoteattr

from .settings import Settings, note_name, safe_filename

SFZ_CHANAFT = 129   # розширений CC для channel aftertouch у SFZ (ARIA / sfizz / Sforzando)


@dataclass
class SampleResult:
    program: int | None
    note: int
    vel: int
    rr: int
    path: str = ""
    frames: int = 0
    sr: int = 48000
    peak_db: float = -120.0
    raw_peak: float = 0.0
    gain_db: float = 0.0
    loop: tuple[int, int] | None = None
    clipped: bool = False
    detected: float | None = None   # реальна висота (MIDI, дробова) або None для безтональних
    root: int | None = None         # root note, записаний у WAV / мапінг
    expr: int | None = None         # значення aftertouch/CC шару експресії
    art: str = ""                   # "" або "swell"

    @property
    def root_note(self) -> int:
        return self.note if self.root is None else self.root

    @property
    def key(self):
        return (self.program, self.note, self.vel, self.rr, self.expr, self.art)


def instrument_dir(s: Settings, program: int | None) -> Path:
    base = Path(s.output_dir) / safe_filename(s.name)
    if program is None:
        return base
    return base / f"{safe_filename(s.name)}_P{program:03d}"


def sample_filename(s: Settings, program, note, vel, rr, expr=None, art="") -> str:
    expr_tok = ""
    if expr is not None:
        expr_tok = f"at{expr:03d}" if s.expr_mode == "aftertouch" else f"cc{s.expr_cc}-{expr:03d}"
    tokens = {
        "name": s.name, "note": note_name(note, s.note_names_c3), "midi": f"{note:03d}",
        "vel": f"{vel:03d}", "rr": rr, "prog": f"{program:03d}" if program else "",
        "expr": expr_tok, "art": art,
    }
    try:
        base = s.naming.format(**tokens)
    except (KeyError, IndexError, ValueError):
        base = "{name}_{note}_v{vel}_rr{rr}".format(**tokens)
    if expr_tok and "{expr}" not in s.naming:
        base += f"_{expr_tok}"
    if art and "{art}" not in s.naming:
        base += f"_{art}"
    if program is not None and "{prog}" not in s.naming:
        base += f"_P{program:03d}"
    return safe_filename(base) + ".wav"


def _key_ranges(notes: list[int]) -> dict[int, tuple[int, int]]:
    notes = sorted(set(notes))
    if not notes:
        return {}
    if len(notes) == 1:
        return {notes[0]: (0, 127)}
    out = {}
    for i, n in enumerate(notes):
        if i == 0:
            gap = notes[1] - n
            lo = max(0, n - gap // 2)
        else:
            lo = out[notes[i - 1]][1] + 1
        if i == len(notes) - 1:
            gap = n - notes[i - 1]
            hi = min(127, n + gap // 2)
        else:
            hi = n + (notes[i + 1] - n) // 2
        out[n] = (lo, hi)
    return out


def _vel_ranges(vels: list[int]) -> dict[int, tuple[int, int]]:
    vels = sorted(set(vels))
    out, prev = {}, 0
    for v in vels:
        out[v] = (prev + 1, v)
        prev = v
    if vels:
        lo, _ = out[vels[-1]]
        out[vels[-1]] = (lo, 127)
    return out


def _xfade(values: list[int], i: int):
    """(fade_in(lo,hi) | None, fade_out(lo,hi) | None) для i-го шару."""
    fin = (values[i - 1], values[i]) if i > 0 else None
    fout = (values[i], values[i + 1]) if i < len(values) - 1 else None
    return fin, fout


def _ds_table(values: list[int], i: int) -> str:
    """Таблиця гучності групи від значення CC (0..127): трикутник із «рівнопотужною» серединою."""
    pts = []
    fin, fout = _xfade(values, i)
    if fin:
        a, b = fin
        pts += [(0, 0.0), (a, 0.0), ((a + b) / 2, 0.707), (b, 1.0)]
    else:
        pts += [(0, 1.0), (values[i], 1.0)]
    if fout:
        a, b = fout
        pts += [((a + b) / 2, 0.707), (b, 0.0), (127, 0.0)]
    else:
        pts += [(127, 1.0)]
    clean = []
    for x, y in pts:
        if clean and abs(clean[-1][0] - x) < 1e-9:
            clean[-1] = (x, y)
        else:
            clean.append((x, y))
    return ";".join(f"{x:g},{y:g}" for x, y in clean)


def xfade_controllers(s: Settings) -> tuple[int, int]:
    """(CC для SFZ, CC для DecentSampler), яким кросфейдяться шари експресії."""
    if s.expr_xfade_ctrl == "cc1":
        return 1, 1
    if s.expr_mode == "aftertouch":
        return SFZ_CHANAFT, 1          # DecentSampler не вміє aftertouch → мод-колесо
    return s.expr_cc, s.expr_cc


def write_mappings(s: Settings, program: int | None, results: list[SampleResult]) -> list[str]:
    results = [r for r in results if r.program == program and r.path and os.path.exists(r.path)]
    if not results:
        return []
    inst = instrument_dir(s, program)
    title = s.name if program is None else f"{s.name} P{program:03d}"
    written = []
    main = [r for r in results if not r.art]
    swell = [r for r in results if r.art == "swell"]
    if main:
        written += _write_set(s, inst, title, main)
    if swell:
        written += _write_set(s, inst, f"{title} Swell", swell)
    return written


def _write_set(s: Settings, inst: Path, title: str, results: list[SampleResult]) -> list[str]:
    # root для кожної надісланої ноти: найчастіший серед її шарів/rr (захист від помилки детектора)
    groups: dict[int, list[int]] = {}
    for r in results:
        groups.setdefault(r.note, []).append(r.root_note)
    group_root = {n: max(set(v), key=v.count) for n, v in groups.items()}
    if len(set(group_root.values())) != len(group_root):   # колізії — повертаємось до MIDI-нот
        group_root = {n: n for n in group_root}

    def tune_cents(r) -> float:
        if s.root_mode != "detect_tune" or r.detected is None:
            return 0.0
        dev = r.detected - group_root[r.note]
        c = round(-dev * 100, 1)
        return c if abs(dev) < 0.5 and abs(c) >= 0.5 else 0.0

    kr_root = _key_ranges(list(group_root.values()))
    kr = {n: kr_root[group_root[n]] for n in group_root}
    vr = _vel_ranges([r.vel for r in results])
    rr_count = max(r.rr for r in results)
    exprs = sorted({r.expr for r in results if r.expr is not None})
    layered = len(exprs) > 1
    cc_sfz, cc_ds = xfade_controllers(s)
    release = min(max(s.release_s if s.release_mode == "fixed" else 1.0, 0.05), 5.0)
    results.sort(key=lambda r: (r.expr if r.expr is not None else -1, r.note, r.vel, r.rr))
    written = []

    def rel(r):
        return Path(os.path.relpath(r.path, inst)).as_posix()

    if s.export_sfz:
        lines = [f"// {title} — створено AutoSample", ""]
        if layered:
            src = "channel aftertouch" if cc_sfz == SFZ_CHANAFT else f"CC{cc_sfz}"
            lines += [f"// Шари експресії {exprs} кросфейдяться через {src}.", ""]
        lines += ["<control>", "", "<global>", f"ampeg_release={release:.3f}", ""]
        for r in results:
            lo, hi = kr[r.note]
            vlo, vhi = vr[r.vel]
            parts = [f"sample={rel(r)}", f"pitch_keycenter={group_root[r.note]}", f"lokey={lo}", f"hikey={hi}",
                     f"lovel={vlo}", f"hivel={vhi}"]
            if tune_cents(r):
                parts.append(f"tune={tune_cents(r):g}")
            if rr_count > 1:
                parts += [f"seq_length={rr_count}", f"seq_position={r.rr}"]
            if layered and r.expr is not None:
                fin, fout = _xfade(exprs, exprs.index(r.expr))
                if fin:
                    parts += [f"xfin_locc{cc_sfz}={fin[0]}", f"xfin_hicc{cc_sfz}={fin[1]}"]
                if fout:
                    parts += [f"xfout_locc{cc_sfz}={fout[0]}", f"xfout_hicc{cc_sfz}={fout[1]}"]
            if r.loop:
                parts += ["loop_mode=loop_continuous", f"loop_start={r.loop[0]}", f"loop_end={r.loop[1]}"]
            else:
                parts += ["loop_mode=no_loop"]
            lines.append("<region> " + " ".join(parts))
        p = inst / f"{safe_filename(title)}.sfz"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(str(p))

    if s.export_ds:
        seq = ' seqMode="round_robin"' if rr_count > 1 else ""
        x = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<DecentSampler minVersion="1.0.0">',
             '  <ui width="812" height="375" bgColor="FF16181D">',
             '    <tab name="main">',
             f'      <label x="20" y="10" width="770" height="40" text={quoteattr(title)} textColor="FF4FD1C5" textSize="28"/>']
        if layered:
            src = "Mod Wheel" if cc_ds == 1 else f"CC{cc_ds}"
            x.append(f'      <label x="20" y="190" width="770" height="30" text="{src} = expression layers" '
                     f'textColor="FF8A92A3" textSize="16"/>')
        knobs = [("Attack", "ENV_ATTACK", 0.0, 5.0, 0.001), ("Decay", "ENV_DECAY", 0.0, 5.0, 0.0),
                 ("Sustain", "ENV_SUSTAIN", 0.0, 1.0, 1.0), ("Release", "ENV_RELEASE", 0.0, 10.0, release)]
        for i, (lbl, par, mn, mx, val) in enumerate(knobs):
            x.append(f'      <labeled-knob x="{40 + i * 100}" y="80" width="90" textSize="16" label="{lbl}" '
                     f'type="float" minValue="{mn}" maxValue="{mx}" value="{val:.3f}" textColor="FFDDDDDD" trackForegroundColor="FF4FD1C5">')
            x.append(f'        <binding type="amp" level="instrument" position="0" parameter="{par}"/>')
            x.append('      </labeled-knob>')
        x.append(f'      <labeled-knob x="{40 + 4 * 100}" y="80" width="90" textSize="16" label="Volume" type="float" '
                 f'minValue="0" maxValue="1" value="0.8" textColor="FFDDDDDD" trackForegroundColor="FF4FD1C5">')
        x.append('        <binding type="amp" level="instrument" position="0" parameter="AMP_VOLUME"/>')
        x.append('      </labeled-knob>')
        x += ['    </tab>', '  </ui>',
              f'  <groups attack="0.001" decay="0" sustain="1" release="{release:.3f}" volume="0.8">']
        layer_keys = exprs if layered else [None]
        for gi, ev in enumerate(layer_keys):
            name = f' name="Layer {ev}"' if layered else ""
            x.append(f'    <group{name}{seq}>')
            for r in results:
                if layered and r.expr != ev:
                    continue
                lo, hi = kr[r.note]
                vlo, vhi = vr[r.vel]
                a = (f'path={quoteattr(rel(r))} rootNote="{group_root[r.note]}" loNote="{lo}" hiNote="{hi}" '
                     f'loVel="{vlo}" hiVel="{vhi}"')
                if tune_cents(r):
                    a += f' tuning="{tune_cents(r) / 100:.3f}"'
                if rr_count > 1:
                    a += f' seqPosition="{r.rr}"'
                if r.loop:
                    a += f' loopEnabled="true" loopStart="{r.loop[0]}" loopEnd="{r.loop[1]}"'
                x.append(f'      <sample {a}/>')
            x.append('    </group>')
        x.append('  </groups>')
        if layered:
            x += ['  <midi>', f'    <cc number="{cc_ds}">']
            for gi in range(len(exprs)):
                x.append(f'      <binding level="group" type="amp" position="{gi}" parameter="AMP_VOLUME" '
                         f'translation="table" translationTable="{_ds_table(exprs, gi)}"/>')
            x += ['    </cc>', '  </midi>']
        x.append('</DecentSampler>')
        p = inst / f"{safe_filename(title)}.dspreset"
        p.write_text("\n".join(x) + "\n", encoding="utf-8")
        written.append(str(p))
    return written
