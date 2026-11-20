"""sounddevice locates PortAudio via ctypes.util.find_library, which finds nothing inside an AppImage.
Point it at the copy bundled next to the executable."""
import ctypes.util
import os
import sys

_orig = ctypes.util.find_library


def _find_library(name):
    if name == "portaudio":
        bundled = os.path.join(getattr(sys, "_MEIPASS", ""), "libportaudio.so.2")
        if os.path.exists(bundled):
            return bundled
    return _orig(name)


ctypes.util.find_library = _find_library
