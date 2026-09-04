#!/usr/bin/env bash
set -Eeuo pipefail

[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "[FAIL] root is required" >&2; exit 2; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
EXPECTED_BASE="1e2ecb162fdd900ca80b8e69ca085f8d591e7aab"

[[ -r /proc/device-tree/model ]] || { echo "[FAIL] Raspberry Pi model is unavailable" >&2; exit 3; }
[[ -r /etc/os-release ]] || { echo "[FAIL] /etc/os-release missing" >&2; exit 3; }
[[ -r /proc/sys/kernel/random/boot_id ]] || { echo "[FAIL] kernel boot ID unavailable" >&2; exit 3; }

model="$(tr -d '\0' </proc/device-tree/model)"
# shellcheck disable=SC1091
source /etc/os-release
boot_id="$(tr -d '[:space:]' </proc/sys/kernel/random/boot_id)"
repo_head="$(git -C "$REPO_ROOT" rev-parse HEAD)"

case "$model" in *"Raspberry Pi"*) ;; *) echo "[FAIL] unsupported host: $model" >&2; exit 3;; esac
case "${ID:-}:${ID_LIKE:-}" in debian:*|raspbian:*|*:debian*) ;; *) echo "[FAIL] unsupported OS: ${PRETTY_NAME:-unknown}" >&2; exit 3;; esac
[[ "$boot_id" =~ ^[0-9a-fA-F-]{36}$ ]] || { echo "[FAIL] invalid boot ID" >&2; exit 3; }

# A fresh-OS qualification must begin before YWD-1278 has installed anything.
for path in /opt/ywd-1278 /etc/ywd-1278 /var/lib/ywd-1278 /var/log/ywd-1278 /etc/systemd/system/ywd-1278.service /etc/systemd/system/ywd-1278-install-resume.service; do
  [[ ! -e "$path" ]] || { echo "[FAIL] pre-existing YWD-1278 appliance state found: $path" >&2; exit 4; }
done
if systemctl list-unit-files ywd-1278.service --no-legend 2>/dev/null | grep -q '^ywd-1278\.service'; then
  echo "[FAIL] pre-existing ywd-1278.service registration found" >&2
  exit 4
fi

printf 'STAGE_H_REPO_HEAD=%s\n' "$repo_head"
printf 'STAGE_H_PARENT_STAGE_G=%s\n' "$EXPECTED_BASE"
printf 'TARGET_MODEL=%s\n' "$model"
printf 'OS_PRETTY_NAME=%s\n' "${PRETTY_NAME:-unknown}"
printf 'KERNEL=%s\n' "$(uname -r)"
printf 'ARCH=%s\n' "$(uname -m)"
printf 'PRE_INSTALL_BOOT_ID=%s\n' "$boot_id"
echo "PREEXISTING_YWD1278_STATE=NO"
echo "PREEXISTING_YWD1278_SERVICE=NO"

echo "===== FRESH-OS UART AUDIT ====="
audit="$(bash "$REPO_ROOT/installer/platform.sh" audit)"
printf '%s\n' "$audit"

if grep -q '^RUNTIME_UART_READY=YES$' <<<"$audit" && grep -q '^SERIAL_CONSOLE_PRESENT=NO$' <<<"$audit"; then
  echo "===== PRE-INSTALL HAT IDENTITY PROBE ====="
  set +e
  detect="$(YWD1278_SOURCE_ROOT="$REPO_ROOT" bash "$REPO_ROOT/installer/hardware-detect.sh" --device /dev/ttyAMA0 2>&1)"
  rc=$?
  set -e
  printf '%s\n' "$detect"
  echo "PRE_INSTALL_HAT_PROBE_RC=$rc"
  if [[ $rc -eq 0 ]]; then
    echo "PRE_INSTALL_HAT_IDENTITY_CAPTURED=YES"
  else
    echo "PRE_INSTALL_HAT_IDENTITY_CAPTURED=NO"
  fi
else
  echo "PRE_INSTALL_HAT_IDENTITY_CAPTURED=NO"
  echo "PRE_INSTALL_HAT_IDENTITY_REASON=UART_REPAIR_REQUIRED"
fi

echo "YWD1278_STAGE_H_FRESH_OS_PREFLIGHT=PASS"
echo "PLATFORM_MUTATED=NO"
echo "SERVICE_ENABLED=NO"
echo "FLASH_WRITTEN=NO"
echo "RF_TRANSMITTED=NO"
