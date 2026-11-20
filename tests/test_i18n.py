import ast
import string
from pathlib import Path

import pytest

from autosample import i18n
from autosample.i18n import UK, set_language, tr
from autosample.settings import Settings

ROOT = Path(__file__).resolve().parent.parent


def _tr_literals() -> dict[str, str]:
    """Every first-argument string of a tr(...) call in the sources, mapped to where it was found."""
    found = {}
    for path in [*ROOT.glob("autosample/**/*.py"), ROOT / "main.py"]:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr":
                arg = node.args[0] if node.args else None
                assert isinstance(arg, ast.Constant) and isinstance(arg.value, str), \
                    f"{path.name}:{node.lineno}: tr() needs a string literal"
                found.setdefault(arg.value, f"{path.name}:{node.lineno}")
    return found


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}


@pytest.fixture(autouse=True)
def _reset_language():
    yield
    set_language("en")


def test_catalog_values_not_empty():
    assert all(v.strip() for v in UK.values())


def test_every_tr_literal_is_translated():
    missing = {k: where for k, where in _tr_literals().items() if k not in UK}
    assert not missing, f"add to i18n.UK: {missing}"


def test_catalog_has_no_unused_entries():
    unused = set(UK) - set(_tr_literals())
    assert not unused, f"unused i18n.UK entries: {unused}"


def test_placeholders_match():
    bad = [k for k, v in UK.items() if _fields(k) != _fields(v)]
    assert not bad, bad


def test_fallback_and_format():
    assert tr("Samples: {n}", n=3) == "Samples: 3"           # English by default
    set_language("uk")
    assert tr("Samples: {n}", n=3) == UK["Samples: {n}"].format(n=3)
    assert tr("not in the catalog {x}", x=1) == "not in the catalog 1"   # unknown text falls back to English
    set_language("xx")                                        # unknown language code -> English
    assert i18n.language() == "en"


def test_old_config_without_language_loads():
    assert Settings.from_dict({"name": "Old"}).language == "en"
