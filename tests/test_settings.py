import pytest

from autosample.settings import (
    Settings,
    note_name,
    parse_note,
    parse_values,
    parse_velocities,
    safe_filename,
)


def test_parse_velocities():
    assert parse_velocities("127, 64 32;32") == [32, 64, 127]
    assert parse_velocities("0, 200, abc") == [127]  # out of range / junk -> default
    assert parse_velocities("") == [127]


def test_parse_values():
    assert parse_values("0, 64, 127, 300", 0, 127) == [0, 64, 127]
    assert parse_values("x", 0, 127) == []


@pytest.mark.parametrize("c3", [True, False])
def test_note_name_roundtrip(c3):
    for n in range(128):
        assert parse_note(note_name(n, c3), c3) == n


def test_note_name_conventions():
    assert note_name(60, c3=True) == "C3"
    assert note_name(60, c3=False) == "C4"
    assert parse_note("Db3") == 61
    assert parse_note("60") == 60
    assert parse_note("C9") is None  # > 127
    assert parse_note("zzz") is None


def test_safe_filename():
    assert safe_filename('a<b>c:d"e/f\\g|h?i*j') == "a_b_c_d_e_f_g_h_i_j"
    assert safe_filename("   ") == "sample"


def test_settings_json_roundtrip(tmp_path):
    s = Settings(name="Synth", note_start=40, velocities="32, 127", auto_loop=True, hold_s=1.5)
    p = tmp_path / "sub" / "s.json"
    s.save(p)
    assert Settings.load(p) == s


def test_from_dict_ignores_unknown_and_bad_values():
    s = Settings.from_dict({"note_start": "abc", "bogus": 1, "round_robins": "3"})
    assert s.note_start == Settings().note_start
    assert s.round_robins == 3


def test_counts():
    s = Settings(note_start=36, note_end=48, note_step=3, velocities="64,127", round_robins=2)
    assert s.notes() == [36, 39, 42, 45, 48]
    assert s.main_samples() == 5 * 2 * 2
