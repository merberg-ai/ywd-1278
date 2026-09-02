#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$ROOT/firmware/tooling/packet-build-manifest.json"
BRANDER="$ROOT/firmware/tooling/apply_packet_branding.py"
INSPECTOR="$ROOT/firmware/tooling/inspect_artifact.py"
MATERIALIZER="$ROOT/firmware/tooling/materialize_vendored_engineering.py"
REPRO_CHECK=1
KEEP_WORK=0
JOBS="${YWD1278_BUILD_JOBS:-$(nproc 2>/dev/null || echo 2)}"

usage(){
  cat <<'EOF'
Usage: ./firmware/build-packet-ywd1278.sh [options]

Build-only 0B-P10 packet-capable YWD-1278 AX25R3 firmware pipeline.
It does not open the modem UART, touch GPIO, flash the STM32, or transmit RF.

The exact qualified YWD-MMDVM engineering files are vendored inside YWD-1278
and verified against their original Git blob SHAs before every build. The
YWD-MMDVM repository/commit remains provenance only; no external checkout or
YWD-MMDVM fetch is required.

Options:
  --single                 Build once instead of the default two-build
                           byte-for-byte reproducibility check.
  --keep-work              Keep temporary build trees for inspection.
  --jobs N                 Parallel make jobs.
  -h, --help               Show this help.
EOF
}

while (($#)); do
  case "$1" in
    --single) REPRO_CHECK=0 ;;
    --keep-work) KEEP_WORK=1 ;;
    --jobs) JOBS="${2:?missing job count}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[FAIL] Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

[[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || { echo "[FAIL] --jobs must be a positive integer" >&2; exit 2; }
[[ ${EUID:-$(id -u)} -ne 0 ]] || {
  echo "[FAIL] Firmware builds do not require root. Run this command without sudo." >&2
  exit 2
}

for cmd in git make python3 arm-none-eabi-gcc arm-none-eabi-g++ arm-none-eabi-objcopy sha256sum cmp grep stat; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "[FAIL] Missing build dependency: $cmd" >&2; exit 2; }
done
[[ -f "$MANIFEST" && -f "$BRANDER" && -f "$INSPECTOR" && -f "$MATERIALIZER" ]] || {
  echo "[FAIL] Packet firmware build tooling is incomplete" >&2
  exit 2
}

mget(){
  python3 - "$MANIFEST" "$1" <<'PY'
import json,sys
with open(sys.argv[1], encoding='utf-8') as f: value=json.load(f)
for part in sys.argv[2].split('.'):
    value=value[part]
if isinstance(value,bool): print('true' if value else 'false')
else: print(value)
PY
}

PROFILE="$(mget profile_id)"
PHASE="$(mget phase)"
TARGET="$(mget target_id)"
UPSTREAM_REPO="$(mget upstream.repository)"
UPSTREAM_COMMIT="$(mget upstream.commit)"
UPSTREAM_SHORT="$(mget upstream.short_commit)"
SUBMODULE_SHA="$(mget upstream.submodules.STM32F10X_Lib)"
CONFIG_TEMPLATE="$(mget upstream.config_template)"
CONFIG_BLOB="$(mget upstream.config_template_blob)"
VERSION_BLOB="$(mget upstream.version_blob)"
MAKEFILE_BLOB="$(mget upstream.makefile_blob)"
UPSTREAM_BUILD_SCRIPT="$(mget upstream.build_script)"
UPSTREAM_BUILD_SCRIPT_BLOB="$(mget upstream.build_script_blob)"
ENG_NAME="$(mget engineering.repository)"
ENG_COMMIT="$(mget engineering.commit)"
ENG_SOURCE="$(mget engineering.source)"
MAKE_TARGET="$(mget build.make_target)"
STM32_HSE_HZ="$(mget build.stm32_hse_hz)"
OSC_OVERRIDE="$(mget build.osc_override)"
RF_TCXO_HZ="$(mget rf.tcxo_hz)"
BINARY_PATH="$(mget build.binary_path)"
FW_VERSION="$(mget branding.firmware_version)"
EXPECTED_IDENTITY="$(mget branding.expected_identity)"
EXPECTED_INFO="$(mget branding.expected_info)"

[[ "$(mget safety.hardware_access)" == false ]] || { echo "[FAIL] packet build manifest permits hardware access" >&2; exit 2; }
[[ "$(mget safety.flash_enabled)" == false ]] || { echo "[FAIL] packet build manifest unexpectedly enables flashing" >&2; exit 2; }
[[ "$(mget safety.option_bytes_permitted)" == false ]] || { echo "[FAIL] packet build manifest permits option-byte writes" >&2; exit 2; }
[[ "$(mget safety.rf_transmit_possible)" == false ]] || { echo "[FAIL] packet build manifest permits RF" >&2; exit 2; }
[[ "$ENG_SOURCE" == vendored ]] || { echo "[FAIL] packet engineering source is not vendored" >&2; exit 2; }
[[ "$OSC_OVERRIDE" == false ]] || { echo "[FAIL] packet HAT build must not pass OSC=" >&2; exit 2; }
[[ "$STM32_HSE_HZ" == 8000000 ]] || { echo "[FAIL] packet HAT build requires STM32 HSE 8000000 Hz" >&2; exit 2; }
[[ "$RF_TCXO_HZ" == 14745600 ]] || { echo "[FAIL] expected ADF7021 TCXO is 14745600 Hz" >&2; exit 2; }

OUT_DIR="${YWD1278_PACKET_FIRMWARE_OUT:-$ROOT/firmware/out/$PROFILE}"
mkdir -p "$OUT_DIR"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/ywd1278-packet-fwbuild.XXXXXX")"
if [[ $KEEP_WORK -eq 0 ]]; then
  trap 'rm -rf "$WORK"' EXIT
else
  trap 'echo "[INFO] Packet build work tree retained at: $WORK"' EXIT
fi
TRANSFORMS="$WORK/engineering"
mkdir -p "$TRANSFORMS"

printf '\n=== YWD-1278 %s PACKET FIRMWARE BUILD ===\n' "$PHASE"
printf 'Profile             : %s\n' "$PROFILE"
printf 'Target              : %s\n' "$TARGET"
printf 'Upstream commit     : %s\n' "$UPSTREAM_COMMIT"
printf 'Engineering repo    : %s (provenance only)\n' "$ENG_NAME"
printf 'Engineering commit  : %s (provenance only)\n' "$ENG_COMMIT"
printf 'Engineering source  : vendored inside YWD-1278\n'
printf 'External eng. repo  : NOT REQUIRED\n'
printf 'STM32 HSE           : %s Hz (upstream default; no OSC override)\n' "$STM32_HSE_HZ"
printf 'ADF7021 TCXO        : %s Hz\n' "$RF_TCXO_HZ"
printf 'Firmware identity   : %s\n' "$EXPECTED_IDENTITY"
printf 'Packet info         : %s\n' "$EXPECTED_INFO"
printf 'Hardware access     : NO\n'
printf 'Flash operations    : DISABLED\n'
printf 'RF transmit         : IMPOSSIBLE DURING BUILD\n\n'

python3 "$MATERIALIZER" --manifest "$MANIFEST" --dest "$TRANSFORMS"

SEED="$WORK/upstream"
echo "==> Fetch exact pinned upstream source"
git init -q "$SEED"
git -C "$SEED" remote add origin "$UPSTREAM_REPO"
export GIT_TERMINAL_PROMPT=0
fetch_ok=0
for attempt in 1 2 3; do
  if git -C "$SEED" fetch --quiet --no-tags --depth=1 origin "$UPSTREAM_COMMIT"; then
    fetch_ok=1
    break
  fi
  echo "[WARN] Exact upstream fetch attempt $attempt failed" >&2
  sleep "$attempt"
done
[[ $fetch_ok -eq 1 ]] || { echo "[FAIL] Could not fetch pinned upstream commit $UPSTREAM_COMMIT" >&2; exit 1; }

git -C "$SEED" cat-file -e "$UPSTREAM_COMMIT^{commit}"
git -C "$SEED" cat-file -e "$UPSTREAM_COMMIT^{tree}"
git -C "$SEED" checkout --quiet --detach "$UPSTREAM_COMMIT"

echo "==> Fetch exact pinned STM32F10X_Lib submodule"
git -C "$SEED" submodule sync --quiet --recursive
git -C "$SEED" submodule update --init --recursive

[[ "$(git -C "$SEED" rev-parse HEAD)" == "$UPSTREAM_COMMIT" ]] || { echo "[FAIL] upstream checkout mismatch" >&2; exit 1; }
[[ "$(git -C "$SEED/STM32F10X_Lib" rev-parse HEAD)" == "$SUBMODULE_SHA" ]] || { echo "[FAIL] submodule mismatch" >&2; exit 1; }
[[ "$(git -C "$SEED" hash-object "$CONFIG_TEMPLATE")" == "$CONFIG_BLOB" ]] || { echo "[FAIL] HAT configuration blob mismatch" >&2; exit 1; }
[[ "$(git -C "$SEED" hash-object version.h)" == "$VERSION_BLOB" ]] || { echo "[FAIL] version.h blob mismatch" >&2; exit 1; }
[[ "$(git -C "$SEED" hash-object Makefile)" == "$MAKEFILE_BLOB" ]] || { echo "[FAIL] Makefile blob mismatch" >&2; exit 1; }
[[ "$(git -C "$SEED" hash-object "$UPSTREAM_BUILD_SCRIPT")" == "$UPSTREAM_BUILD_SCRIPT_BLOB" ]] || { echo "[FAIL] upstream HAT build recipe blob mismatch" >&2; exit 1; }
[[ -z "$(git -C "$SEED" status --porcelain --ignore-submodules=none)" ]] || { echo "[FAIL] upstream seed is not clean" >&2; exit 1; }

grep -Eq '^CLK_DEF=8000000$' "$SEED/Makefile" || { echo "[FAIL] upstream STM32 HSE default changed" >&2; exit 1; }
grep -q '^#define ADF7021_14_7456$' "$SEED/$CONFIG_TEMPLATE" || { echo "[FAIL] HAT config no longer selects 14.7456 MHz ADF7021 TCXO" >&2; exit 1; }
python3 - "$SEED/$UPSTREAM_BUILD_SCRIPT" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text(encoding='utf-8')
needle='cp ~/MMDVM_HS/configs/MMDVM_HS_Hat.h ~/MMDVM_HS/Config.h\nmake -j4\n'
if needle not in s:
    raise SystemExit('[FAIL] pinned HAT recipe is not the expected no-OSC-override invocation')
print('UPSTREAM_HAT_BUILD_RECIPE=PASS')
PY

echo "[ OK ] Exact upstream source, clocks, target config, and submodule verified"

SOURCE_DATE_EPOCH="$(git -C "$SEED" show -s --format=%ct HEAD)"
export SOURCE_DATE_EPOCH TZ=UTC LC_ALL=C
TOOLCHAIN="$(arm-none-eabi-gcc --version | head -n1)"
MAKE_VERSION="$(make --version | head -n1)"
printf 'Toolchain           : %s\n' "$TOOLCHAIN"
printf 'Make                : %s\n' "$MAKE_VERSION"
printf 'SOURCE_DATE_EPOCH   : %s\n' "$SOURCE_DATE_EPOCH"

mapfile -t TRANSFORM_ORDER < <(python3 - "$MANIFEST" <<'PY'
import json,sys
m=json.load(open(sys.argv[1],encoding='utf-8'))
for path in m['engineering']['transform_order']:
    print(path)
PY
)

build_one(){
  local label="$1" src="$WORK/$1" artifact="$WORK/$1.bin" log="$OUT_DIR/$1.log"
  echo
  echo "==> Clean packet build $label"
  cp -a "$SEED" "$src"
  git -C "$src" reset --quiet --hard "$UPSTREAM_COMMIT"
  git -C "$src" clean -qfdx
  [[ "$(git -C "$src/STM32F10X_Lib" rev-parse HEAD)" == "$SUBMODULE_SHA" ]] || {
    echo "[FAIL] $label submodule changed before transform" >&2; return 1;
  }

  cp "$src/$CONFIG_TEMPLATE" "$src/Config.h"

  for rel in "${TRANSFORM_ORDER[@]}"; do
    echo "    transform: $rel"
    python3 "$TRANSFORMS/$rel" "$src"
  done

  python3 "$BRANDER" "$src" --manifest "$MANIFEST"

  {
    echo "YWD-1278 packet firmware build $label"
    echo "upstream=$UPSTREAM_COMMIT"
    echo "engineering=$ENG_COMMIT"
    echo "engineering_source=vendored"
    echo "toolchain=$TOOLCHAIN"
    echo "make=$MAKE_VERSION"
    echo "SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH"
    echo "stm32_hse_hz=$STM32_HSE_HZ"
    echo "adf7021_tcxo_hz=$RF_TCXO_HZ"
    echo "osc_override=false"
    make -C "$src" clean
    # Do not pass OSC=. 8 MHz is the STM32 HSE; 14.7456 MHz belongs only to
    # the ADF7021 TCXO selected by Config.h.
    make -C "$src" -j"$JOBS" "$MAKE_TARGET"
  } >"$log" 2>&1 || {
    echo "[FAIL] $label failed; see $log" >&2
    tail -n 60 "$log" >&2 || true
    return 1
  }

  [[ -f "$src/$BINARY_PATH" ]] || { echo "[FAIL] $label did not produce $BINARY_PATH" >&2; return 1; }
  cp "$src/$BINARY_PATH" "$artifact"
  python3 "$INSPECTOR" "$artifact" --manifest "$MANIFEST"
  echo "[ OK ] $label complete"
}

build_one build-a
A="$WORK/build-a.bin"
REPRO_RESULT="NOT_RUN"
if [[ $REPRO_CHECK -eq 1 ]]; then
  build_one build-b
  B="$WORK/build-b.bin"
  echo
  echo "==> Byte-for-byte packet firmware reproducibility"
  sha_a="$(sha256sum "$A" | awk '{print $1}')"
  sha_b="$(sha256sum "$B" | awk '{print $1}')"
  printf 'Build A SHA256: %s\n' "$sha_a"
  printf 'Build B SHA256: %s\n' "$sha_b"
  cmp -s "$A" "$B" || { echo "[FAIL] independent packet builds are not byte-identical" >&2; exit 1; }
  [[ "$sha_a" == "$sha_b" ]] || { echo "[FAIL] reproducibility SHA mismatch" >&2; exit 1; }
  REPRO_RESULT="PASS"
  echo "[ OK ] Independent packet builds are byte-identical"
else
  sha_a="$(sha256sum "$A" | awk '{print $1}')"
fi

ARTIFACT_NAME="MMDVM_HS_Hat-YWD-1278-AX25R3-v${FW_VERSION}-${UPSTREAM_SHORT}-hse8m.bin"
FINAL="$OUT_DIR/$ARTIFACT_NAME"
META="$OUT_DIR/build-metadata.json"
FINAL_TMP="$OUT_DIR/.${ARTIFACT_NAME}.tmp.$$"
META_TMP="$OUT_DIR/.build-metadata.json.tmp.$$"

cp "$A" "$FINAL_TMP"
FINAL_SHA="$(sha256sum "$FINAL_TMP" | awk '{print $1}')"
FINAL_SIZE="$(stat -c %s "$FINAL_TMP")"

python3 - "$MANIFEST" "$META_TMP" "$FINAL" "$FINAL_SHA" "$FINAL_SIZE" "$TOOLCHAIN" "$MAKE_VERSION" "$SOURCE_DATE_EPOCH" "$REPRO_RESULT" <<'PY'
import json,sys
manifest_path,meta_path,artifact,sha,size,toolchain,make_version,epoch,repro=sys.argv[1:]
with open(manifest_path,encoding='utf-8') as f: m=json.load(f)
out={
  'schema':1,
  'phase':m['phase'],
  'profile_id':m['profile_id'],
  'target_id':m['target_id'],
  'upstream_commit':m['upstream']['commit'],
  'engineering_source':'vendored',
  'engineering_repository':m['engineering']['repository'],
  'engineering_commit':m['engineering']['commit'],
  'engineering_files':m['engineering']['files'],
  'transform_order':m['engineering']['transform_order'],
  'firmware_version':m['branding']['firmware_version'],
  'expected_identity':m['branding']['expected_identity'],
  'expected_info':m['branding']['expected_info'],
  'stm32_hse_hz':m['build']['stm32_hse_hz'],
  'osc_override':m['build']['osc_override'],
  'adf7021_tcxo_hz':m['rf']['tcxo_hz'],
  'artifact':artifact,
  'artifact_size_bytes':int(size),
  'artifact_sha256':sha,
  'toolchain':toolchain,
  'make':make_version,
  'source_date_epoch':int(epoch),
  'reproducibility':repro,
  'hardware_accessed':False,
  'rf_transmitted':False,
  'flash_written':False,
  'option_bytes_written':False,
}
with open(meta_path,'w',encoding='utf-8') as f:
    json.dump(out,f,indent=2,sort_keys=True)
    f.write('\n')
PY

chmod 0444 "$FINAL_TMP"
mv -f "$FINAL_TMP" "$FINAL"
chmod 0444 "$META_TMP"
mv -f "$META_TMP" "$META"
echo "ATOMIC_PUBLISH=PASS"

echo
echo "=== 0B-P10 PACKET FIRMWARE BUILD RESULT ==="
echo "ARTIFACT=$FINAL"
echo "ARTIFACT_SIZE_BYTES=$FINAL_SIZE"
echo "ARTIFACT_SHA256=$FINAL_SHA"
echo "FIRMWARE_IDENTITY=$EXPECTED_IDENTITY"
echo "PACKET_INFO=$EXPECTED_INFO"
echo "ENGINEERING_COMMIT=$ENG_COMMIT"
echo "ENGINEERING_SOURCE=VENDORED_IN_YWD1278"
echo "ENGINEERING_EXTERNAL_REPO_REQUIRED=NO"
echo "ENGINEERING_WORKTREE_USED=NO"
echo "STM32_HSE_HZ=$STM32_HSE_HZ"
echo "ADF7021_TCXO_HZ=$RF_TCXO_HZ"
echo "OSC_OVERRIDE=NO"
echo "REPRODUCIBILITY=$REPRO_RESULT"
echo "METADATA=$META"
echo "HARDWARE_ACCESSED=NO"
echo "MODEM_UART_OPENED=NO"
echo "RF_TRANSMITTED=NO"
echo "FLASH_WRITTEN=NO"
echo "OPTION_BYTES_WRITTEN=NO"
