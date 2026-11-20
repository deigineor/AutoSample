import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("bump_version", Path(__file__).parent.parent / "packaging" / "bump_version.py")
bv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bv)


@pytest.mark.parametrize("part,expected", [("patch", "1.2.4"), ("minor", "1.3.0"), ("major", "2.0.0")])
def test_bump(part, expected):
    assert bv.bump("1.2.3", part) == expected


def test_bump_unknown():
    with pytest.raises(ValueError):
        bv.bump("1.2.3", "feature")


def test_main_rewrites_only_version(tmp_path):
    f = tmp_path / "__init__.py"
    f.write_text('"""doc"""\n__version__ = "0.9.9"\nX = 1\n')
    assert bv.main("minor", f) == "0.10.0"
    assert f.read_text() == '"""doc"""\n__version__ = "0.10.0"\nX = 1\n'
