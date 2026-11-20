import xml.etree.ElementTree as ET

import numpy as np

from autosample.export import SampleResult, _key_ranges, _vel_ranges, instrument_dir, sample_filename, write_mappings
from autosample.settings import Settings
from autosample.wavfile import write_wav


def test_key_ranges_cover_and_do_not_overlap():
    r = _key_ranges([36, 48, 60])
    assert r[36][0] == 30 and r[60][1] == 66
    assert r[36][1] + 1 == r[48][0] and r[48][1] + 1 == r[60][0]
    assert _key_ranges([60]) == {60: (0, 127)}
    assert _key_ranges([]) == {}


def test_vel_ranges():
    assert _vel_ranges([127, 40, 80]) == {40: (1, 40), 80: (41, 80), 127: (81, 127)}


def test_sample_filename():
    s = Settings(name="Syn")
    assert sample_filename(s, None, 60, 127, 1) == "Syn_C3_v127_rr1.wav"
    assert sample_filename(s, 5, 60, 127, 1).endswith("_P005.wav")


def _results(s, notes, vels, rr=1):
    out = []
    for n in notes:
        for v in vels:
            for r in range(1, rr + 1):
                p = str(instrument_dir(s, None) / f"{s.name}_{n}_{v}_{r}.wav")
                write_wav(p, np.zeros((100, 1), np.float32), 48000, "16", root_note=n)
                out.append(SampleResult(program=None, note=n, vel=v, rr=r, path=p, frames=100))
    return out


def test_write_mappings_sfz_and_dspreset(tmp_path):
    s = Settings(name="Syn", output_dir=str(tmp_path))
    res = _results(s, [48, 60], [64, 127], rr=2)
    res[0].loop = (10, 90)
    written = write_mappings(s, None, res)
    assert sorted(p.rsplit(".", 1)[1] for p in written) == ["dspreset", "sfz"]

    sfz = next(p for p in written if p.endswith(".sfz"))
    text = open(sfz, encoding="utf-8").read()
    regions = [ln for ln in text.splitlines() if ln.startswith("<region>")]
    assert len(regions) == 8
    assert "pitch_keycenter=48" in text and "seq_length=2" in text and "loop_start=10 loop_end=90" in text

    ds = next(p for p in written if p.endswith(".dspreset"))
    root = ET.parse(ds).getroot()
    assert root.tag == "DecentSampler"
    samples = root.findall(".//sample")
    assert len(samples) == 8
    assert {x.get("rootNote") for x in samples} == {"48", "60"}
    assert all(not x.get("path").startswith("/") for x in samples)


def test_write_mappings_respects_export_flags_and_missing_files(tmp_path):
    s = Settings(name="Syn", output_dir=str(tmp_path), export_ds=False)
    res = _results(s, [60], [127])
    assert [p.rsplit(".", 1)[1] for p in write_mappings(s, None, res)] == ["sfz"]
    assert write_mappings(s, None, [SampleResult(None, 60, 127, 1, path=str(tmp_path / "nope.wav"))]) == []


def test_expression_layers_crossfade(tmp_path):
    s = Settings(name="Syn", output_dir=str(tmp_path), expr_mode="cc", expr_cc=11, export_ds=False)
    base = _results(s, [60], [127])[0]
    res = [SampleResult(None, 60, 127, 1, path=base.path, expr=e) for e in (0, 127)]
    sfz = write_mappings(s, None, res)[0]
    text = open(sfz, encoding="utf-8").read()
    assert "xfout_locc11=0" in text and "xfin_hicc11=127" in text
