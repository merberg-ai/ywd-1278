#!/usr/bin/env bash
# Run as a child process; never source this file.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1
PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" python3 tools/qualify_0e_p3_lan.py "$@"
