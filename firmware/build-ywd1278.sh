#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$ROOT/firmware/tooling/build-manifest.json"
BRANDER="$ROOT/firmware/tooling/apply_branding.py"
INSPECTOR="$ROOT/firmware/tooling/inspect_artifact.py"
REPRO_CHECK=1
KEEP_WORK=0
JOBS="${YWD1278_BUILD_JOBS:-$(nproc 2>/dev/null || echo 2)}"

usage(){
  cat <<'EOF'
Usage: ./firmware/build-ywd1278.sh [options]

Build-only 0B-P1 pipeline. It does not access the HAT or Raspberry Pi GPIOs.

Options:
  --single       Build once instead of performing the default two-build
                 byte-for-byte reproducibility check.
  --keep-work    Keep the temporary source/build tree for inspection.
  --jobs N       Parallel make jobs (default: detected CPU count).
  -h, --help     Show this help.
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

for cmd in git make python3 arm-none-eabi-gcc arm-none-eabi-g++ arm-none-eabi-objcopy sha256sum cmp; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "[FAIL] Missing build dependency: $cmd" >&2
    echo "       Run the YWD-1278 installer with firmware toolchain support first." >&2
    exit 2
  }
done
[[ -f "$MANIFEST" && -f "$BRANDER" && -f "$INSPECTOR" ]] || {
  echo "[FAIL] Firmware build tooling is incomplete" >&2
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
TARGET="$(mget target_id)"
UPSTREAM_REPO="$(mget upstream.repository)"
UPSTREAM_COMMIT="$(mget upstream.commit)"
UPSTREAM_SHORT="$(mget upstream.short_commit)"
SUBMODULE_SHA="$(mget upstream.submodules.STM32F10X_Lib)"
CONFIG_TEMPLATE="$(mget upstream.config_template)"
CONFIG_BLOB="$(mget upstream.config_template_blob)"
VERSION_BLOB="$(mget upstream.version_blob)"
MAKE_TARGET="$(mget build.make_target)"
OSC_HZ="$(mget build.osc_hz)"
BINARY_PATH="$(mget build.binary_path)"
FW_VERSION="$(mget branding.firmware_version)"
EXPECTED_IDENTITY="$(mget branding.expected_identity)"

[[ "$(mget safety.hardware_access)" == false ]] || { echo "[FAIL] build manifest permits hardware access" >&2; exit 2; }
[[ "$(mget safety.flash_enabled)" == false ]] || { echo "[FAIL] build manifest unexpectedly enables flashing" >&2; exit 2; }
[[ "$(mget safety.option_bytes_permitted)" == false ]] || { echo "[FAIL] build manifest unexpectedly permits option-byte writes" >&2; exit 2; }
[[ "$(mget safety.rf_transmit_possible)" == false ]] || { echo "[FAIL] build manifest unexpectedly permits RF" >&2; exit 2; }

OUT_DIR="${YWD1278_FIRMWARE_OUT:-$ROOT/firmware/out/$PROFILE}"
mkdir -p "$OUT_DIR"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/ywd1278-fwbuild.XXXXXX")"
if [[ $KEEP_WORK -eq 0 ]]; then
  trap 'rm -rf "$WORK"' EXIT
else
  trap 'echo "[INFO] Build work tree retained at: $WORK"' EXIT
fi

printf '\n=== YWD-1278 0B-P1 FIRMWARE BUILD ===\n'
printf 'Profile          : %s\n' "$PROFILE"
printf 'Target           : %s\n' "$TARGET"
printf 'Upstream commit  : %s\n' "$UPSTREAM_COMMIT"
printf 'F1 library       : %s\n' "$SUBMODULE_SHA"
printf 'Configuration    : %s\n' "$CONFIG_TEMPLATE"
printf 'Oscillator       : %s Hz\n' "$OSC_HZ"
printf 'Firmware identity: %s\n' "$EXPECTED_IDENTITY"
printf 'Hardware access  : NO\n'
printf 'Flash operations : DISABLED\n\n'

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

git -C "$SEED" cat-file -e "$UPSTREAM_COMMIT^{commit}" || { echo "[FAIL] pinned upstream commit object is missing" >&2; exit 1; }
git -C "$SEED" cat-file -e "$UPSTREAM_COMMIT^{tree}" || { echo "[FAIL] pinned upstream tree object is missing" >&2; exit 1; }
git -C "$SEED" checkout --quiet --detach "$UPSTREAM_COMMIT"

echo "==> Fetch exact pinned STM32F10X_Lib submodule"
git -C "$SEED" submodule sync --quiet --recursive
git -C "$SEED" submodule update --init --recursive

actual_commit="$(git -C "$SEED" rev-parse HEAD)"
actual_submodule="$(git -C "$SEED/STM32F10X_Lib" rev-parse HEAD)"
[[ "$actual_commit" == "$UPSTREAM_COMMIT" ]] || { echo "[FAIL] upstream checkout mismatch: $actual_commit" >&2; exit 1; }
[[ "$actual_submodule" == "$SUBMODULE_SHA" ]] || { echo "[FAIL] STM32F10X_Lib checkout mismatch: $actual_submodule" >&2; exit 1; }
[[ "$(git -C "$SEED" hash-object "$CONFIG_TEMPLATE")" == "$CONFIG_BLOB" ]] || { echo "[FAIL] pinned HAT configuration blob mismatch" >&2; exit 1; }
[[ "$(git -C "$SEED" hash-object version.h)" == "$VERSION_BLOB" ]] || { echo "[FAIL] pinned version.h blob mismatch" >&2; exit 1; }
[[ -z "$(git -C "$SEED" status --porcelain --ignore-submodules=none)" ]] || { echo "[FAIL] pinned source seed is not clean" >&2; exit 1; }
echo "[ OK ] Exact upstream source and STM32F10X_Lib submodule verified"

SOURCE_DATE_EPOCH="$(git -C "$SEED" show -s --format=%ct HEAD)"
export SOURCE_DATE_EPOCH TZ=UTC LC_ALL=C
TOOLCHAIN="$(arm-none-eabi-gcc --version | head -n1)"
MAKE_VERSION="$(make --version | head -n1)"
printf 'Toolchain        : %s\n' "$TOOLCHAIN"
printf 'Make             : %s\n' "$MAKE_VERSION"
printf 'SOURCE_DATE_EPOCH: %s\n' "$SOURCE_DATE_EPOCH"

build_one(){
  local label="$1" src="$WORK/$1" artifact="$WORK/$1.bin" log="$OUT_DIR/$1.log"
  echo
  echo "==> Clean build $label"
  cp -a "$SEED" "$src"
  git -C "$src" reset --quiet --hard "$UPSTREAM_COMMIT"
  git -C "$src" clean -qfdx
  [[ "$(git -C "$src/STM32F10X_Lib" rev-parse HEAD)" == "$SUBMODULE_SHA" ]] || {
    echo "[FAIL] $label submodule changed before build" >&2; return 1;
  }

  cp "$src/$CONFIG_TEMPLATE" "$src/Config.h"
  python3 "$BRANDER" "$src" --manifest "$MANIFEST"

  {
    echo "YWD-1278 firmware build $label"
    echo "upstream=$UPSTREAM_COMMIT"
    echo "submodule.STM32F10X_Lib=$SUBMODULE_SHA"
    echo "toolchain=$TOOLCHAIN"
    echo "make=$MAKE_VERSION"
    echo "SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH"
    make -C "$src" clean
    make -C "$src" -j"$JOBS" "$MAKE_TARGET" OSC="$OSC_HZ"
  } >"$log" 2>&1 || {
    echo "[FAIL] $label failed; see $log" >&2
    tail -n 40 "$log" >&2 || true
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
  echo "==> Byte-for-byte reproducibility"
  sha_a="$(sha256sum "$A" | awk '{print $1}')"
  sha_b="$(sha256sum "$B" | awk '{print $1}')"
  printf 'Build A SHA256: %s\n' "$sha_a"
  printf 'Build B SHA256: %s\n' "$sha_b"
  cmp -s "$A" "$B" || { echo "[FAIL] independent clean builds are not byte-identical" >&2; exit 1; }
  [[ "$sha_a" == "$sha_b" ]] || { echo "[FAIL] reproducibility SHA mismatch" >&2; exit 1; }
  REPRO_RESULT="PASS"
  echo "[ OK ] Independent clean builds are byte-identical"
else
  sha_a="$(sha256sum "$A" | awk '{print $1}')"
fi

ARTIFACT_NAME="MMDVM_HS_Hat-YWD-1278-v${FW_VERSION}-${UPSTREAM_SHORT}.bin"
FINAL="$OUT_DIR/$ARTIFACT_NAME"
cp "$A" "$FINAL"
FINAL_SHA="$(sha256sum "$FINAL" | awk '{print $1}')"
FINAL_SIZE="$(stat -c %s "$FINAL")"
META="$OUT_DIR/build-metadata.json"

python3 - "$MANIFEST" "$META" "$FINAL" "$FINAL_SHA" "$FINAL_SIZE" "$TOOLCHAIN" "$MAKE_VERSION" "$SOURCE_DATE_EPOCH" "$REPRO_RESULT" <<'PY'
import json,sys
manifest_path,meta_path,artifact,sha,size,toolchain,make_version,epoch,repro=sys.argv[1:]
with open(manifest_path,encoding='utf-8') as f: m=json.load(f)
out={
  'schema': 1,
  'phase': m['phase'],
  'profile_id': m['profile_id'],
  'target_id': m['target_id'],
  'upstream_commit': m['upstream']['commit'],
  'stm32f10x_lib_commit': m['upstream']['submodules']['STM32F10X_Lib'],
  'config_template_blob': m['upstream']['config_template_blob'],
  'version_blob': m['upstream']['version_blob'],
  'firmware_version': m['branding']['firmware_version'],
  'expected_identity': m['branding']['expected_identity'],
  'artifact': artifact,
  'artifact_size_bytes': int(size),
  'artifact_sha256': sha,
  'toolchain': toolchain,
  'make_version': make_version,
  'source_date_epoch': int(epoch),
  'reproducibility': repro,
  'hardware_accessed': False,
  'rf_transmitted': False,
  'flash_written': False,
  'option_bytes_written': False,
}
with open(meta_path,'w',encoding='utf-8') as f:
    json.dump(out,f,indent=2,sort_keys=True); f.write('\n')
PY

chmod 0444 "$FINAL" "$META"

echo
printf '=== 0B-P1 BUILD RESULT ===\n'
printf 'ARTIFACT=%s\n' "$FINAL"
printf 'ARTIFACT_SIZE_BYTES=%s\n' "$FINAL_SIZE"
printf 'ARTIFACT_SHA256=%s\n' "$FINAL_SHA"
printf 'FIRMWARE_IDENTITY=%s\n' "$EXPECTED_IDENTITY"
printf 'REPRODUCIBILITY=%s\n' "$REPRO_RESULT"
printf 'METADATA=%s\n' "$META"
printf 'HARDWARE_ACCESSED=NO\n'
printf 'RF_TRANSMITTED=NO\n'
printf 'FLASH_WRITTEN=NO\n'
printf 'OPTION_BYTES_WRITTEN=NO\n'
