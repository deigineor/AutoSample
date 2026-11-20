"""Bump __version__ in autosample/__init__.py: `python packaging/bump_version.py patch|minor|major`. Prints the new version."""
import re
import sys
from pathlib import Path

INIT = Path(__file__).resolve().parent.parent / "autosample" / "__init__.py"


def bump(version: str, part: str) -> str:
    major, minor, patch = map(int, version.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unknown part: {part}")


def main(part: str, path: Path = INIT) -> str:
    text = path.read_text()
    m = re.search(r'^__version__ = "(\d+\.\d+\.\d+)"$', text, re.M)
    if not m:
        raise SystemExit(f"no X.Y.Z __version__ in {path}")
    new = bump(m.group(1), part)
    path.write_text(text[:m.start(1)] + new + text[m.end(1):])
    return new


if __name__ == "__main__":
    print(main(sys.argv[1]))
