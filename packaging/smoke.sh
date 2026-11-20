#!/usr/bin/env bash
# Start the GUI headless; it must still be running after 10 s (exit 124 = killed by timeout = ok).
# Usage: smoke.sh <executable> [args...]
set -u
QT_QPA_PLATFORM=offscreen timeout 10 "$@"
rc=$?
if [ "$rc" -eq 124 ]; then echo "smoke ok: still running after 10s"; exit 0; fi
echo "smoke FAILED: exited early with code $rc" >&2
exit 1
