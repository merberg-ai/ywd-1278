#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$ROOT/firmware/tooling/packet-build-manifest.json"
BUILDER="$ROOT/firmware/build-packet-ywd1278.sh"

[[ ${EUID:-$(id -u)} -ne 0 ]] || {
  echo "[FAIL] Firmware builds do not require root. Run this command without sudo." >&2
  exit 2
}

for cmd in git python3; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "[FAIL] Missing dependency: $cmd" >&2; exit 2; }
done
[[ -f "$MANIFEST" && -x "$BUILDER" ]] || {
  echo "[FAIL] P10 packet build tooling is incomplete" >&2
  exit 2
}

readarray -t ENG < <(python3 - "$MANIFEST" <<'PY'
import json,sys
m=json.load(open(sys.argv[1],encoding='utf-8'))
print(m['engineering']['repository'])
print(m['engineering']['remote'])
print(m['engineering']['commit'])
PY
)
ENG_NAME="${ENG[0]}"
ENG_DEFAULT_REMOTE="${ENG[1]}"
ENG_COMMIT="${ENG[2]}"
ENGINEERING_REMOTE="${YWD1278_ENGINEERING_REMOTE:-$ENG_DEFAULT_REMOTE}"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/ywd1278-engineering-fetch.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
REPO="$WORK/ywd-mmdvm.git"

echo "=== YWD-1278 P10 FROZEN ENGINEERING SOURCE ==="
echo "Engineering repo   : $ENG_NAME"
echo "Engineering remote : $ENGINEERING_REMOTE"
echo "Engineering commit : $ENG_COMMIT"
echo "Checkout/worktree  : NONE"
echo "Hardware access    : NO"
echo "RF transmit        : IMPOSSIBLE"
echo

git init -q "$REPO"
git -C "$REPO" remote add origin "$ENGINEERING_REMOTE"
export GIT_TERMINAL_PROMPT=0

fetch_ok=0
for attempt in 1 2 3; do
  if git -C "$REPO" fetch --quiet --no-tags --depth=1 origin "$ENG_COMMIT"; then
    fetch_ok=1
    break
  fi
  echo "[WARN] Frozen engineering fetch attempt $attempt failed" >&2
  sleep "$attempt"
done
[[ $fetch_ok -eq 1 ]] || {
  echo "[FAIL] Could not fetch frozen engineering commit $ENG_COMMIT" >&2
  echo "       Remote: $ENGINEERING_REMOTE" >&2
  exit 1
}

git -C "$REPO" cat-file -e "$ENG_COMMIT^{commit}" || {
  echo "[FAIL] Frozen engineering commit object is missing after fetch" >&2
  exit 1
}

actual="$(git -C "$REPO" rev-parse "$ENG_COMMIT^{commit}")"
[[ "$actual" == "$ENG_COMMIT" ]] || {
  echo "[FAIL] Frozen engineering commit mismatch: $actual" >&2
  exit 1
}

echo "FROZEN_ENGINEERING_FETCH=PASS"
echo "ENGINEERING_COMMIT=$actual"
echo "ENGINEERING_CHECKOUT_CREATED=NO"
echo "ENGINEERING_WORKTREE_USED=NO"
echo

"$BUILDER" --engineering-repo "$REPO" "$@"
