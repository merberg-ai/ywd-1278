#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROFILE="$SCRIPT_DIR/product-ax25r4.json"
JOBS="${YWD1278_FIRMWARE_BUILD_JOBS:-}"

if [[ $EUID -eq 0 ]]; then
  echo "[FAIL] Product firmware preparation is build-only and must not run as root." >&2
  exit 2
fi

if [[ -z "$JOBS" ]]; then
  if command -v nproc >/dev/null 2>&1; then JOBS="$(nproc)"; else JOBS=1; fi
fi
[[ "$JOBS" =~ ^[0-9]+$ ]] && (( JOBS >= 1 )) || { echo "[FAIL] invalid YWD1278_FIRMWARE_BUILD_JOBS" >&2; exit 2; }

expected_rel="$(python3 - "$PROFILE" <<'PY'
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8'))
print(p['artifact_relative_path'])
PY
)"
expected_sha="$(python3 - "$PROFILE" <<'PY'
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8'))
print(p['artifact_sha256'])
PY
)"
expected_size="$(python3 - "$PROFILE" <<'PY'
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8'))
print(p['artifact_size_bytes'])
PY
)"
artifact="$ROOT/$expected_rel"

printf '%s\n' "===== YWD-1278 QUALIFIED AX25R4 PREPARATION ====="
printf 'EXPECTED_ARTIFACT=%s\n' "$artifact"
printf 'EXPECTED_SHA256=%s\n' "$expected_sha"
printf 'EXPECTED_SIZE_BYTES=%s\n' "$expected_size"
printf 'HARDWARE_ACCESS=NO\nFLASH_WRITTEN=NO\nRF_TRANSMITTED=NO\n'

python3 "$SCRIPT_DIR/build-packet-rssi-ywd1278.py" --jobs "$JOBS"

PYTHONPATH="$ROOT/src" python3 -m ywd1278.install.firmware_trust \
  --profile "$PROFILE" artifact --firmware "$artifact"

echo "YWD1278_PRODUCT_FIRMWARE_PREPARE=PASS"
echo "PRODUCT_FIRMWARE=$artifact"
echo "PRODUCT_FIRMWARE_SHA256=$expected_sha"
echo "PRODUCT_FIRMWARE_SIZE_BYTES=$expected_size"
echo "HARDWARE_ACCESS=NO"
echo "FLASH_WRITTEN=NO"
echo "RF_TRANSMITTED=NO"
