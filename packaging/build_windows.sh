#!/usr/bin/env bash
# Build dist/AutoSample-<version>-windows-x64.exe (run from Git Bash; needs requirements-dev.txt installed).
set -euo pipefail
cd "$(dirname "$0")/.."
version=$(python -c "import autosample; print(autosample.__version__)")
python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/autosample.spec
mv dist/AutoSample.exe "dist/AutoSample-${version}-windows-x64.exe"
ls -l dist
