#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/ui.sh
source "$SCRIPT_DIR/lib/ui.sh"
require_root
banner

INSTALL_ROOT=/opt/ywd-1278
SOURCE_ROOT="$INSTALL_ROOT/source"
VENV="$INSTALL_ROOT/venv"
CONFIG_DIR=/etc/ywd-1278
CONFIG_FILE="$CONFIG_DIR/config.toml"
STATE_DIR=/var/lib/ywd-1278
BACKUP_DIR="$STATE_DIR/firmware-backups"
LOG_DIR=/var/log/ywd-1278
UNIT_DST=/etc/systemd/system/ywd-1278.service
RESUME_UNIT_DST=/etc/systemd/system/ywd-1278-install-resume.service
RESUME_STATE="$STATE_DIR/install-resume.env"
BIN_LINK=/usr/local/bin/ywd1278
SKIP_PACKAGES=0
WITH_FIRMWARE_TOOLCHAIN=1
RUN_SETUP=1
STAGING_ROOT=""
DETECTED_TARGET=""
DETECTED_IDENTITY=""
FIRMWARE_CLASS=""
FIRMWARE_DESCRIPTION=""
ALLOW_CANDIDATE_RELEASE=0

cleanup(){ [[ -z "$STAGING_ROOT" || ! -d "$STAGING_ROOT" ]] || rm -rf "$STAGING_ROOT"; }
trap cleanup EXIT
usage(){
  cat <<'EOF'
Usage: sudo ./installer/install.sh [options]
  --skip-packages            Do not run apt-get
  --no-firmware-toolchain    Skip compiler/programmer packages
  --setup                    Run setup (default)
  --no-setup                 Preserve configuration without prompting
  -h, --help                 Show this help

The installer never flashes firmware and leaves ywd-1278.service disabled.
EOF
}
while (($#)); do
  case "$1" in
    --skip-packages) SKIP_PACKAGES=1 ;;
    --no-firmware-toolchain) WITH_FIRMWARE_TOOLCHAIN=0 ;;
    --setup) RUN_SETUP=1 ;;
    --no-setup) RUN_SETUP=0 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
  shift
done

[[ -f "$REPO_ROOT/VERSION" && -f "$REPO_ROOT/pyproject.toml" ]] || die "Run the installer from a complete YWD-1278 source tree"
version="$(tr -d '[:space:]' <"$REPO_ROOT/VERSION")"
commit="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || printf 'source-tree')"

section "Stage source"
STAGING_ROOT="$(mktemp -d /tmp/ywd1278-install.XXXXXX)"
tar -C "$REPO_ROOT" --exclude=.git --exclude='__pycache__' --exclude='*.pyc' -cf - . | tar -C "$STAGING_ROOT" -xf -
ok "Staged YWD-1278 $version ($commit)"

section "Platform preflight"
[[ -r /proc/device-tree/model ]] || die "Unable to identify Raspberry Pi model"
model="$(tr -d '\0' </proc/device-tree/model)"
[[ "$model" == *"Raspberry Pi"* ]] || die "Unsupported host: $model"
ok "Detected: $model"
[[ -r /etc/os-release ]] || die "/etc/os-release not found"
# shellcheck disable=SC1091
source /etc/os-release
case "${ID:-}:${ID_LIKE:-}" in
  debian:*|raspbian:*|*:debian*) ok "Debian-family OS: ${PRETTY_NAME:-unknown}" ;;
  *) die "Initial installer supports Raspberry Pi OS/Debian-family systems only" ;;
esac

if [[ $SKIP_PACKAGES -eq 0 ]]; then
  section "Dependencies"
  export DEBIAN_FRONTEND=noninteractive
  step "Refreshing apt metadata"; apt-get update
  packages=(ca-certificates git python3 python3-venv python3-pip python3-setuptools python3-wheel sqlite3 build-essential pkg-config)
  apt-cache show raspi-utils >/dev/null 2>&1 && packages+=(raspi-utils)
  [[ $WITH_FIRMWARE_TOOLCHAIN -eq 0 ]] || packages+=(gcc-arm-none-eabi binutils-arm-none-eabi stm32flash)
  step "Installing required packages"; apt-get install -y --no-install-recommends "${packages[@]}"
  ok "Dependencies ready"
else
  warn "Package installation skipped by request"
fi
for cmd in python3 git systemctl tar sha256sum; do command_exists "$cmd" || die "Required command missing: $cmd"; done

section "Filesystem layout"
install -d -m 0755 "$INSTALL_ROOT" "$CONFIG_DIR" "$STATE_DIR" "$BACKUP_DIR" "$LOG_DIR"
chmod 0700 "$BACKUP_DIR"

section "Python environment"
system_py="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
reuse=0
if [[ -x "$VENV/bin/python" ]]; then
  venv_py="$($VENV/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
  [[ "$venv_py" == "$system_py" ]] && reuse=1
fi
if [[ $reuse -eq 1 ]]; then
  ok "Reusing existing Python venv ($system_py)"
else
  [[ ! -d "$VENV" ]] || info "Existing venv is missing/incompatible; rebuilding it once"
  rm -rf "$VENV"; python3 -m venv "$VENV"; ok "Created Python venv ($system_py)"
fi
install_package(){ "$VENV/bin/python" -m pip install --disable-pip-version-check --no-cache-dir --upgrade --force-reinstall "$STAGING_ROOT"; }
if ! install_package; then
  [[ $reuse -eq 1 ]] || die "Package installation failed in newly created venv"
  warn "In-place venv refresh failed; rebuilding venv and retrying once"
  rm -rf "$VENV"; python3 -m venv "$VENV"; install_package
fi

if [[ -d "$SOURCE_ROOT" && -n "$(find "$SOURCE_ROOT" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
  old="$INSTALL_ROOT/source.pre-install.$(date +%Y%m%d-%H%M%S)"; mv "$SOURCE_ROOT" "$old"; info "Previous installed source preserved at $old"
fi
mv "$STAGING_ROOT" "$SOURCE_ROOT"; STAGING_ROOT=""
printf '%s\n' "$version" >"$INSTALL_ROOT/installed-version"
printf '%s\n' "$commit" >"$INSTALL_ROOT/installed-commit"
ln -sfn "$VENV/bin/ywd1278" "$BIN_LINK"
mapfile -t old_sources < <(ls -1dt "$INSTALL_ROOT"/source.pre-install.* 2>/dev/null || true)
if ((${#old_sources[@]} > 3)); then rm -rf -- "${old_sources[@]:3}"; fi
ok "Installed YWD-1278 $version ($commit)"

section "Configuration"
if [[ ! -f "$CONFIG_FILE" ]]; then install -m 0640 "$SOURCE_ROOT/config/ywd-1278.example.toml" "$CONFIG_FILE"; ok "Installed safe default configuration"
else ok "Preserving existing configuration and using it as setup defaults"; fi

section "systemd"
install -m 0644 "$SOURCE_ROOT/systemd/ywd-1278.service" "$UNIT_DST"
install -m 0644 "$SOURCE_ROOT/systemd/ywd-1278-install-resume.service" "$RESUME_UNIT_DST"
systemctl daemon-reload
systemctl disable --now ywd-1278.service >/dev/null 2>&1 || true
ok "Installed YWD-1278 services; packet service remains disabled/inactive"

section "Framework self-test"
"$VENV/bin/ywd1278d" --config "$CONFIG_FILE" --framework-self-test
ok "Framework self-test passed"

section "Raspberry Pi UART audit"
audit="$(bash "$SOURCE_ROOT/installer/platform.sh" audit)"; printf '%s\n' "$audit"
runtime_ready=0; grep -q '^RUNTIME_UART_READY=YES$' <<<"$audit" && runtime_ready=1
reboot_needed=0; grep -q '^REBOOT_REQUIRED=YES$' <<<"$audit" && reboot_needed=1

try_detect(){
  local allow="${1:-0}" out rc
  local -a detect_args=(--device /dev/ttyAMA0)
  [[ "$allow" == 1 ]] && detect_args+=(--allow-candidate-release)
  if out="$(YWD1278_SOURCE_ROOT="$SOURCE_ROOT" bash "$SOURCE_ROOT/installer/hardware-detect.sh" "${detect_args[@]}" 2>&1)"; then rc=0; else rc=$?; fi
  printf '%s\n' "$out"
  DETECTED_TARGET="$(sed -n 's/^DETECTED_TARGET=//p' <<<"$out" | tail -1)"
  DETECTED_IDENTITY="$(sed -n 's/^DETECTED_IDENTITY=//p' <<<"$out" | tail -1)"
  FIRMWARE_CLASS="$(sed -n 's/^FIRMWARE_CLASS=//p' <<<"$out" | tail -1)"
  FIRMWARE_DESCRIPTION="$(sed -n 's/^FIRMWARE_DESCRIPTION=//p' <<<"$out" | tail -1)"
  return "$rc"
}

if [[ $runtime_ready -eq 1 ]]; then
  section "Automatic HAT detection"
  if try_detect 0; then detect_rc=0; else detect_rc=$?; fi
  if [[ $detect_rc -eq 20 ]]; then
    warn "The UART is healthy but the HAT did not answer. A supported HAT may be held in reset by Raspberry Pi GPIO defaults."
    if confirm_yes_no "Try the qualified supported-HAT application-release GPIO profile?" yes; then
      ALLOW_CANDIDATE_RELEASE=1
      try_detect 1 || warn "No supported HAT was identified yet; setup can continue safely."
    fi
  elif [[ $detect_rc -eq 22 ]]; then
    warn "A HAT/modem answered GET_VERSION, but its firmware identity is not recognized. No GPIO or firmware action will be taken automatically."
  elif [[ $detect_rc -ne 0 ]]; then
    warn "No supported HAT was identified yet; setup can continue safely."
  fi
else
  warn "UART is not runtime-ready, so HAT detection will resume after platform repair/reboot."
fi

if [[ $RUN_SETUP -eq 1 ]]; then
  section "Interactive setup"
  YWD1278_SOURCE_ROOT="$SOURCE_ROOT" \
  YWD1278_DETECTED_TARGET="$DETECTED_TARGET" \
  YWD1278_DETECTED_IDENTITY="$DETECTED_IDENTITY" \
  YWD1278_FIRMWARE_CLASS="$FIRMWARE_CLASS" \
  YWD1278_FIRMWARE_DESCRIPTION="$FIRMWARE_DESCRIPTION" \
  bash "$SOURCE_ROOT/installer/setup.sh"
fi

if [[ $reboot_needed -eq 1 ]]; then
  section "Platform repair"
  warn "Raspberry Pi boot/UART settings need a one-time repair before reliable HAT access."
  if confirm_yes_no "Apply the required UART/serial-console changes?" yes; then
    bash "$SOURCE_ROOT/installer/platform.sh" apply
    configured_target="$(python3 - "$CONFIG_FILE" <<'PY'
import sys,tomllib
with open(sys.argv[1],'rb') as f: d=tomllib.load(f)
print(d.get('hardware',{}).get('target',''))
PY
)"
    if [[ -z "$configured_target" && $ALLOW_CANDIDATE_RELEASE -eq 0 ]]; then
      confirm_yes_no "After reboot, allow the installer to try the single compatible supported-HAT GPIO release profile if the direct probe is silent?" yes && ALLOW_CANDIDATE_RELEASE=1
    fi
    cat >"$RESUME_STATE" <<EOF
STATE_VERSION=1
DEVICE=/dev/ttyAMA0
ALLOW_CANDIDATE_RELEASE=$ALLOW_CANDIDATE_RELEASE
EOF
    chmod 0600 "$RESUME_STATE"
    systemctl enable ywd-1278-install-resume.service >/dev/null
    ok "Post-reboot continuation checkpoint saved"
    if confirm_yes_no "Reboot now and continue installation automatically?" yes; then
      info "Saving files and rebooting. After boot, ywd-1278-install-resume.service continues from this checkpoint."
      sync; sleep 2; systemctl reboot; exit 0
    fi
    warn "Reboot deferred. The resume service is armed and will continue automatically on your next reboot."
    exit 0
  else
    warn "Platform repair declined; installation is safe but HAT access may remain unavailable."
  fi
fi

section "Install complete"
ok "YWD-1278 host framework installed"
[[ -n "$DETECTED_TARGET" ]] && ok "Supported HAT: $DETECTED_TARGET" || warn "Supported HAT detection is still pending"
if [[ -n "$DETECTED_IDENTITY" ]]; then
  info "HAT firmware: ${FIRMWARE_CLASS:-UNKNOWN}"
  step "$DETECTED_IDENTITY"
fi
info "CLI: ywd1278 --version"
info "Config: $CONFIG_FILE"
info "Packet service remains disabled until the packet engine/firmware port is qualified."
echo "YWD1278_INSTALL=PASS"
echo "RF_TRANSMITTED=NO"
echo "FLASH_WRITTEN=NO"
