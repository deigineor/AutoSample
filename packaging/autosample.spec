# PyInstaller spec, the single source of truth for both platforms.
#   Windows: one-file windowed exe.   Linux: onedir (wrapped into an AppImage by build_linux.sh).
# Linux needs PORTAUDIO_SO=/path/to/libportaudio.so.2 (sounddevice has no bundled PortAudio there).
import os
import sys

root = os.path.abspath(os.path.join(SPECPATH, ".."))
win = sys.platform == "win32"

binaries = []
if not win:
    binaries.append((os.environ["PORTAUDIO_SO"], "."))

a = Analysis(
    [os.path.join(root, "main.py")],
    pathex=[root],
    binaries=binaries,
    datas=[(os.path.join(root, "autosample", "ui", "icons"), "autosample/ui/icons")],
    runtime_hooks=[os.path.join(SPECPATH, "rthook_portaudio.py")],
)
if not win:
    # use the host's ALSA (config and plugins must match the host); libportaudio itself is bundled
    a.binaries = [b for b in a.binaries if not b[0].startswith("libasound.so")]

pyz = PYZ(a.pure)

if win:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="AutoSample", console=False, upx=False)
else:
    exe = EXE(pyz, a.scripts, exclude_binaries=True, name="AutoSample", console=False, upx=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="AutoSample", upx=False)
