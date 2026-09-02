#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$ROOT/firmware/tooling/packet-build-manifest.json"
BUILDER="$ROOT/firmware/build-packet-ywd1278.sh"
MATERIALIZER="$ROOT/firmware/tooling/materialize_vendored_engineering.py"

[[ ${EUID:-$(id -u)} -ne 0 ]] || {
  echo "[FAIL] Firmware builds do not require root. Run this command without sudo." >&2
  exit 2
}

for cmd in git python3; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "[FAIL] Missing dependency: $cmd" >&2; exit 2; }
done
[[ -f "$MANIFEST" && -x "$BUILDER" && -f "$MATERIALIZER" ]] || {
  echo "[FAIL] P10 packet build tooling is incomplete" >&2
  exit 2
}

readarray -t ENG < <(python3 - "$MANIFEST" <<'PY'
import json,sys
m=json.load(open(sys.argv[1],encoding='utf-8'))
print(m['engineering']['source'])
print(m['engineering']['repository'])
print(m['engineering']['commit'])
print(m['engineering']['vendored_root'])
PY
)
ENG_SOURCE="${ENG[0]}"
ENG_NAME="${ENG[1]}"
ENG_COMMIT="${ENG[2]}"
ENG_VENDOR="${ENG[3]}"

[[ "$ENG_SOURCE" == vendored ]] || {
  echo "[FAIL] P10 engineering source is not vendored" >&2
  exit 1
}
[[ -d "$ROOT/$ENG_VENDOR" ]] || {
  echo "[FAIL] Vendored engineering source is missing: $ROOT/$ENG_VENDOR" >&2
  exit 1
}

echo "=== YWD-1278 P10 FROZEN ENGINEERING SOURCE ==="
echo "Engineering repo   : $ENG_NAME (provenance only)"
echo "Engineering commit : $ENG_COMMIT (provenance only)"
echo "Engineering source : $ENG_VENDOR"
echo "External checkout  : NOT REQUIRED"
echo "External fetch     : NOT REQUIRED"
echo "Hardware access    : NO"
echo "RF transmit        : IMPOSSIBLE"
echo
echo "FROZEN_ENGINEERING_VENDOR=PASS"
echo "ENGINEERING_COMMIT=$ENG_COMMIT"
echo "ENGINEERING_EXTERNAL_REPO_REQUIRED=NO"
echo "ENGINEERING_NETWORK_FETCH_REQUIRED=NO"
echo "ENGINEERING_WORKTREE_USED=NO"
echo

exec "$BUILDER" "$@"
