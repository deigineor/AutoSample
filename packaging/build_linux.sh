#!/usr/bin/env bash
# Build dist/AutoSample-<version>-linux-x86_64.AppImage.
# Needs: requirements-dev.txt installed, apt libportaudio2 (+ libxcb-cursor0 for Qt's xcb plugin), curl.
set -euo pipefail
cd "$(dirname "$0")/.."

APPIMAGETOOL_URL=https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage
APPIMAGETOOL_SHA256=ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0

version=$(python -c "import autosample; print(autosample.__version__)")
out="dist/AutoSample-${version}-linux-x86_64.AppImage"

PORTAUDIO_SO=$(PATH="$PATH:/sbin:/usr/sbin" ldconfig -p | awk '/libportaudio\.so\.2 .*x86-64/ {print $NF; exit}')
[ -n "$PORTAUDIO_SO" ] || { echo "libportaudio.so.2 not found: apt install libportaudio2" >&2; exit 1; }
export PORTAUDIO_SO

python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/autosample.spec

# Qt's xcb plugin links libxcb-cursor; many distros lack it, so it must be bundled
compgen -G 'dist/AutoSample/_internal/libxcb-cursor.so*' >/dev/null || { echo "libxcb-cursor0 missing at build time: apt install libxcb-cursor0" >&2; exit 1; }

appdir=build/AutoSample.AppDir
rm -rf "$appdir"
mkdir -p "$appdir/usr/bin"
cp -a dist/AutoSample/. "$appdir/usr/bin/"
cp packaging/autosample.png "$appdir/autosample.png"
cp packaging/autosample.desktop "$appdir/autosample.desktop"
ln -s autosample.png "$appdir/.DirIcon"
cat > "$appdir/AppRun" <<'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/AutoSample" "$@"
APPRUN
chmod +x "$appdir/AppRun"

tool=build/appimagetool-x86_64.AppImage
if [ ! -x "$tool" ]; then
    curl -fsSL -o "$tool" "$APPIMAGETOOL_URL"
    echo "$APPIMAGETOOL_SHA256  $tool" | sha256sum -c -
    chmod +x "$tool"
fi
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$tool" "$appdir" "$out"
ls -l dist
