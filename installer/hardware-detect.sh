#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="${YWD1278_SOURCE_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
# shellcheck source=lib/ui.sh
source "$SCRIPT_DIR/lib/ui.sh"

require_root
CONFIG=/etc/ywd-1278/config.toml
DEVICE=/dev/ttyAMA0
ALLOW_CANDIDATE_RELEASE=0
QUIET=0

while (($#)); do
  case "$1" in
    --device) DEVICE="${2:?missing device}"; shift ;;
    --config) CONFIG="${2:?missing config}"; shift ;;
    --allow-candidate-release) ALLOW_CANDIDATE_RELEASE=1 ;;
    --quiet) QUIET=1 ;;
    *) die "Unknown hardware-detect option: $1" ;;
  esac
  shift
done

TARGETS="$SOURCE_ROOT/firmware/targets.json"
PROBE="$SOURCE_ROOT/firmware/probe_hat.py"
CONTROL="$SOURCE_ROOT/firmware/hat_control.py"
[[ -f "$TARGETS" && -f "$PROBE" && -f "$CONTROL" ]] || die "Firmware detection helpers are incomplete"
[[ -e "$DEVICE" ]] || { echo "HAT_DETECT=NO_UART"; exit 10; }

if fuser "$DEVICE" >/dev/null 2>&1; then
  [[ $QUIET -eq 1 ]] || fail "UART is busy: $DEVICE"
  echo "HAT_DETECT=UART_BUSY"
  exit 11
fi

configured_target="$(python3 - "$CONFIG" <<'PY'
import sys,tomllib
from pathlib import Path
p=Path(sys.argv[1])
if not p.exists():
    print(''); raise SystemExit
with p.open('rb') as f: data=tomllib.load(f)
v=data.get('hardware',{}).get('target','')
print(v if isinstance(v,str) else '')
PY
)"

probe_json(){ python3 "$PROBE" --device "$DEVICE" --targets "$TARGETS" --json 2>/tmp/ywd1278-probe-error.$$; }
parse_result(){
  python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["identity"]); print(d["matched_target_ids"][0] if len(d["matched_target_ids"])==1 else "")'
}

release_used=NO
if result="$(probe_json)"; then
  :
else
  if [[ -n "$configured_target" ]]; then
    [[ $QUIET -eq 1 ]] || info "Configured HAT is silent; releasing its qualified application-state GPIOs"
    python3 "$CONTROL" application-release --targets "$TARGETS" --target "$configured_target"
    release_used=YES
  elif [[ $ALLOW_CANDIDATE_RELEASE -eq 1 ]]; then
    [[ $QUIET -eq 1 ]] || info "Direct probe was silent; trying the authorized compatible HAT application-release profile"
    python3 "$CONTROL" auto-detect-release --targets "$TARGETS"
    release_used=YES
  else
    rm -f /tmp/ywd1278-probe-error.$$
    echo "HAT_DETECT=NEEDS_RELEASE_AUTH"
    exit 20
  fi
  sleep 0.5
  if ! result="$(probe_json)"; then
    [[ $QUIET -eq 1 ]] || { fail "No supported HAT answered after application release"; cat /tmp/ywd1278-probe-error.$$ >&2 || true; }
    rm -f /tmp/ywd1278-probe-error.$$
    echo "HAT_DETECT=NO_RESPONSE"
    exit 21
  fi
fi
rm -f /tmp/ywd1278-probe-error.$$

mapfile -t parsed < <(printf '%s' "$result" | parse_result)
identity="${parsed[0]:-}"
target="${parsed[1]:-}"
[[ -n "$identity" && -n "$target" ]] || { echo "HAT_DETECT=UNSUPPORTED"; exit 22; }

echo "HAT_DETECT=PASS"
echo "DETECTED_TARGET=$target"
echo "DETECTED_IDENTITY=$identity"
echo "APPLICATION_RELEASE_USED=$release_used"
echo "RF_CONFIGURED=NO"
echo "FLASH_WRITTEN=NO"
echo "OPTION_BYTES_WRITTEN=NO"
