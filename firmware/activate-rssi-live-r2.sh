#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BASE_HARNESS="$SCRIPT_DIR/activate-rssi-live.sh"

[[ -f "$BASE_HARNESS" ]] || { echo "[FAIL] Base P2 activation harness is missing: $BASE_HARNESS" >&2; exit 1; }

# P2 activation attempt 1 proved that stm32flash 0.7 emits informational
# readback text on stdout. The base harness correctly computes sha256sum after
# each read, but because readback_prefix_sha() itself is called in command
# substitution, stm32flash stdout contaminated the returned hash string.
#
# Preserve the attempt-1 harness byte-for-byte. For R2, interpose only the
# stm32flash process boundary: read operations (-r) keep their diagnostics
# visible on stderr, while writes/probes retain their original stdout behavior.
# No arguments, flash policy, rollback policy, RF setup, or modem operation is
# changed by this wrapper.

YWD1278_REAL_STM32FLASH="$(command -v stm32flash || true)"
[[ -n "$YWD1278_REAL_STM32FLASH" ]] || { echo "[FAIL] stm32flash is required" >&2; exit 1; }
export YWD1278_REAL_STM32FLASH

stm32flash() {
  local arg is_read=0
  for arg in "$@"; do
    if [[ "$arg" == "-r" ]]; then
      is_read=1
      break
    fi
  done

  if (( is_read == 1 )); then
    command "$YWD1278_REAL_STM32FLASH" "$@" >&2
  else
    command "$YWD1278_REAL_STM32FLASH" "$@"
  fi
}
export -f stm32flash

exec bash "$BASE_HARNESS" "$@"
