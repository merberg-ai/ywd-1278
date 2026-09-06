#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=lib/ui.sh
source "$SCRIPT_DIR/lib/ui.sh"
require_root

INSTALL_ROOT=/opt/ywd-1278
SOURCE_ROOT="$INSTALL_ROOT/source"
VENV="$INSTALL_ROOT/venv"
CONFIG_DIR=/etc/ywd-1278
CONFIG_FILE="$CONFIG_DIR/config.toml"
STATE_DIR=/var/lib/ywd-1278
BACKUP_DIR="$STATE_DIR/firmware-backups"
LOG_DIR=/var/log/ywd-1278
INSTALL_LOG="$LOG_DIR/install.log"
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
RUNTIME_CONFIG_READY=0

init_log "$INSTALL_LOG"
banner
info "Detailed installation log: $INSTALL_LOG"

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
Set YWD1278_MACHINE_OUTPUT=1 only when raw machine-readable install markers are
required on stdout; normal interactive installs retain them in install.log.
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
record_marker "SOURCE_COMMIT=$commit"
record_marker "SOURCE_VERSION=$version"

stage "1/4  Prepare the Raspberry Pi"
section "Install YWD-1278 files"
STAGING_ROOT="$(mktemp -d /tmp/ywd1278-install.XXXXXX)"
tar -C "$REPO_ROOT" --exclude=.git --exclude='__pycache__' --exclude='*.pyc' -cf - . | tar -C "$STAGING_ROOT" -xf -
ok "Prepared YWD-1278 $version"
hint "Source commit: $commit"

section "Check platform"
[[ -r /proc/device-tree/model ]] || die "Unable to identify Raspberry Pi model"
model="$(tr -d '\0' </proc/device-tree/model)"
[[ "$model" == *"Raspberry Pi"* ]] || die "Unsupported host: $model"
ok "$model"
[[ -r /etc/os-release ]] || die "/etc/os-release not found"
# shellcheck disable=SC1091
source /etc/os-release
case "${ID:-}:${ID_LIKE:-}" in
  debian:*|raspbian:*|*:debian*) ok "${PRETTY_NAME:-Debian-family OS}" ;;
  *) die "Initial installer supports Raspberry Pi OS/Debian-family systems only" ;;
esac

if [[ $SKIP_PACKAGES -eq 0 ]]; then
  section "Install requirements"
  export DEBIAN_FRONTEND=noninteractive
  run_logged "Refreshing package information" apt-get update || die "Could not refresh package information"
  packages=(ca-certificates git python3 python3-venv python3-pip python3-setuptools python3-wheel sqlite3 build-essential pkg-config psmisc)
  apt-cache show raspi-utils >/dev/null 2>&1 && packages+=(raspi-utils)
  [[ $WITH_FIRMWARE_TOOLCHAIN -eq 0 ]] || packages+=(gcc-arm-none-eabi binutils-arm-none-eabi libnewlib-arm-none-eabi libstdc++-arm-none-eabi-dev libstdc++-arm-none-eabi-newlib stm32flash)
  run_logged "Installing required packages" apt-get install -y --no-install-recommends "${packages[@]}" || die "Required package installation failed"
else
  warn "Package installation skipped by request"
fi
for cmd in python3 git systemctl tar sha256sum; do command_exists "$cmd" || die "Required command missing: $cmd"; done
if [[ $WITH_FIRMWARE_TOOLCHAIN -eq 1 ]]; then
  run_logged "Checking firmware build/programming tools" bash "$REPO_ROOT/installer/firmware-toolchain-check.sh" check || die "Firmware toolchain check failed"
fi

section "Prepare filesystem"
install -d -m 0755 "$INSTALL_ROOT" "$CONFIG_DIR" "$STATE_DIR" "$BACKUP_DIR" "$LOG_DIR"
chmod 0700 "$BACKUP_DIR"
ok "System directories ready"

section "Prepare Python runtime"
system_py="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
reuse=0
if [[ -x "$VENV/bin/python" ]]; then
  venv_py="$($VENV/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
  [[ "$venv_py" == "$system_py" ]] && reuse=1
fi
if [[ $reuse -eq 1 ]]; then
  ok "Reusing Python environment ($system_py)"
else
  [[ ! -d "$VENV" ]] || info "Existing Python environment is incompatible; rebuilding it"
  rm -rf "$VENV"
  run_logged "Creating Python environment" python3 -m venv "$VENV" || die "Could not create Python environment"
fi
install_package(){ "$VENV/bin/python" -m pip install --disable-pip-version-check --no-cache-dir --upgrade --force-reinstall "$STAGING_ROOT"; }
step "Installing YWD-1278 Python package"
if [[ -n "$YWD_LOG_FILE" ]]; then
  if ! install_package >>"$YWD_LOG_FILE" 2>&1; then
    if [[ $reuse -eq 1 ]]; then
      warn "Python environment refresh failed; rebuilding it once"
      rm -rf "$VENV"
      run_logged "Recreating Python environment" python3 -m venv "$VENV" || die "Could not recreate Python environment"
      install_package >>"$YWD_LOG_FILE" 2>&1 || die "YWD-1278 Python package installation failed"
    else
      die "YWD-1278 Python package installation failed"
    fi
  fi
else
  install_package || die "YWD-1278 Python package installation failed"
fi
ok "YWD-1278 Python package installed"

if [[ -d "$SOURCE_ROOT" && -n "$(find "$SOURCE_ROOT" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
  old="$INSTALL_ROOT/source.pre-install.$(date +%Y%m%d-%H%M%S)"
  mv "$SOURCE_ROOT" "$old"
  info "Previous installed source preserved at $old"
fi
mv "$STAGING_ROOT" "$SOURCE_ROOT"; STAGING_ROOT=""
printf '%s\n' "$version" >"$INSTALL_ROOT/installed-version"
printf '%s\n' "$commit" >"$INSTALL_ROOT/installed-commit"
ln -sfn "$VENV/bin/ywd1278" "$BIN_LINK"
mapfile -t old_sources < <(ls -1dt "$INSTALL_ROOT"/source.pre-install.* 2>/dev/null || true)
if ((${#old_sources[@]} > 3)); then rm -rf -- "${old_sources[@]:3}"; fi
ok "Installed YWD-1278 $version"

section "Install services"
if [[ ! -f "$CONFIG_FILE" ]]; then
  install -m 0640 "$SOURCE_ROOT/config/ywd-1278.example.toml" "$CONFIG_FILE"
  ok "Installed safe default configuration"
else
  ok "Preserving existing configuration"
fi
install -m 0644 "$SOURCE_ROOT/systemd/ywd-1278.service" "$UNIT_DST"
install -m 0644 "$SOURCE_ROOT/systemd/ywd-1278-install-resume.service" "$RESUME_UNIT_DST"
systemctl daemon-reload
systemctl disable --now ywd-1278.service >/dev/null 2>&1 || true
ok "Services installed; packet service remains safely stopped"

section "Self-test"
run_logged "Checking installed runtime" "$VENV/bin/ywd1278d" --config "$CONFIG_FILE" --framework-self-test || die "Installed runtime self-test failed"

section "Check radio UART"
capture_logged audit "Raspberry Pi UART audit" bash "$SOURCE_ROOT/installer/platform.sh" audit || true
runtime_ready=0; grep -q '^RUNTIME_UART_READY=YES$' <<<"$audit" && runtime_ready=1
reboot_needed=0; grep -q '^REBOOT_REQUIRED=YES$' <<<"$audit" && reboot_needed=1
if [[ $runtime_ready -eq 1 ]]; then
  ok "Radio UART is ready"
else
  warn "Radio UART needs one-time Raspberry Pi setup"
fi
[[ $reboot_needed -eq 0 ]] || info "A reboot will be offered after configuration is saved"

try_detect(){
  local allow="${1:-0}" out rc
  local -a detect_args=(--device /dev/ttyAMA0)
  [[ "$allow" == 1 ]] && detect_args+=(--allow-candidate-release)
  if out="$(YWD1278_SOURCE_ROOT="$SOURCE_ROOT" bash "$SOURCE_ROOT/installer/hardware-detect.sh" "${detect_args[@]}" 2>&1)"; then rc=0; else rc=$?; fi
  log_block "HAT detection" "$out"
  DETECTED_TARGET="$(sed -n 's/^DETECTED_TARGET=//p' <<<"$out" | tail -1)"
  DETECTED_IDENTITY="$(sed -n 's/^DETECTED_IDENTITY=//p' <<<"$out" | tail -1)"
  FIRMWARE_CLASS="$(sed -n 's/^FIRMWARE_CLASS=//p' <<<"$out" | tail -1)"
  FIRMWARE_DESCRIPTION="$(sed -n 's/^FIRMWARE_DESCRIPTION=//p' <<<"$out" | tail -1)"
  return "$rc"
}

check_runtime_readiness(){
  local out rc
  if out="$("$VENV/bin/python" -m ywd1278.install.readiness --config "$CONFIG_FILE" 2>&1)"; then rc=0; else rc=$?; fi
  log_block "Product runtime readiness" "$out"
  return "$rc"
}

stage "2/4  Find the radio HAT"
if [[ $runtime_ready -eq 1 ]]; then
  section "Detect MMDVM HAT"
  if try_detect 0; then detect_rc=0; else detect_rc=$?; fi
  if [[ $detect_rc -eq 0 ]]; then
    ok "Supported MMDVM HAT detected"
    [[ -z "$DETECTED_TARGET" ]] || step "$DETECTED_TARGET"
    [[ -z "$FIRMWARE_CLASS" ]] || info "Firmware state: $FIRMWARE_CLASS"
  elif [[ $detect_rc -eq 20 ]]; then
    warn "The UART is healthy but the HAT did not answer. It may be held in reset by Raspberry Pi GPIO defaults."
    if confirm_yes_no "Try the supported-HAT GPIO release profile?" yes; then
      ALLOW_CANDIDATE_RELEASE=1
      if try_detect 1; then
        ok "Supported MMDVM HAT detected"
        [[ -z "$DETECTED_TARGET" ]] || step "$DETECTED_TARGET"
        [[ -z "$FIRMWARE_CLASS" ]] || info "Firmware state: $FIRMWARE_CLASS"
      else
        warn "No supported HAT was identified yet; setup can continue safely"
      fi
    fi
  elif [[ $detect_rc -eq 22 ]]; then
    warn "A HAT answered, but its firmware identity is not recognized; no firmware action will be taken"
  else
    warn "No supported HAT was identified yet; setup can continue safely"
  fi
else
  info "HAT detection will continue after the UART repair/reboot"
fi

stage "3/4  Configure the station"
if [[ $RUN_SETUP -eq 1 ]]; then
  YWD1278_SOURCE_ROOT="$SOURCE_ROOT" \
  YWD1278_DETECTED_TARGET="$DETECTED_TARGET" \
  YWD1278_DETECTED_IDENTITY="$DETECTED_IDENTITY" \
  YWD1278_FIRMWARE_CLASS="$FIRMWARE_CLASS" \
  YWD1278_FIRMWARE_DESCRIPTION="$FIRMWARE_DESCRIPTION" \
  bash "$SOURCE_ROOT/installer/setup.sh"
else
  info "Interactive station setup skipped by request"
fi

stage "4/4  Final safety checks"
section "Validate configuration"
if check_runtime_readiness; then
  RUNTIME_CONFIG_READY=1
  ok "Configuration is valid and RF transmit remains disabled"
else
  readiness_rc=$?
  case "$readiness_rc" in
    10)
      warn "Configuration is safely incomplete; the packet service will remain stopped"
      ;;
    20)
      die "Configuration is unsafe or invalid; the packet service remains stopped"
      ;;
    *)
      die "Configuration validation failed unexpectedly (rc=$readiness_rc); the packet service remains stopped"
      ;;
  esac
fi

if [[ $reboot_needed -eq 1 ]]; then
  section "Finish Raspberry Pi UART setup"
  warn "The Raspberry Pi needs one boot-setting change before reliable HAT access"
  if confirm_yes_no "Apply the required UART/serial-console changes?" yes; then
    bash "$SOURCE_ROOT/installer/platform.sh" apply >>"$YWD_LOG_FILE" 2>&1
    configured_target="$(python3 - "$CONFIG_FILE" <<'PY'
import sys,tomllib
with open(sys.argv[1],'rb') as f: d=tomllib.load(f)
print(d.get('hardware',{}).get('target',''))
PY
)"
    if [[ -z "$configured_target" && $ALLOW_CANDIDATE_RELEASE -eq 0 ]]; then
      confirm_yes_no "After reboot, allow the installer to try the compatible supported-HAT GPIO release profile if needed?" yes && ALLOW_CANDIDATE_RELEASE=1
    fi
    cat >"$RESUME_STATE" <<EOF
STATE_VERSION=1
DEVICE=/dev/ttyAMA0
ALLOW_CANDIDATE_RELEASE=$ALLOW_CANDIDATE_RELEASE
EOF
    chmod 0600 "$RESUME_STATE"
    systemctl enable ywd-1278-install-resume.service >/dev/null
    ok "Post-reboot continuation saved"
    if confirm_yes_no "Reboot now and continue installation automatically?" yes; then
      info "Rebooting; YWD-1278 will continue automatically after startup"
      sync; sleep 2; systemctl reboot; exit 0
    fi
    warn "Reboot deferred; installation will continue automatically on the next reboot"
    exit 0
  else
    warn "UART setup declined; HAT access may remain unavailable"
  fi
fi

section "Installation complete"
ok "YWD-1278 is installed"
[[ -n "$DETECTED_TARGET" ]] && ok "Radio HAT recognized" || warn "Radio HAT setup is still pending"
if [[ -n "$DETECTED_IDENTITY" ]]; then
  info "Current HAT firmware: ${FIRMWARE_CLASS:-UNKNOWN}"
  step "$DETECTED_IDENTITY"
fi
if [[ $RUNTIME_CONFIG_READY -eq 1 ]]; then
  ok "Station configuration saved and validated"
else
  warn "Station configuration is incomplete"
fi
info "CLI: ywd1278 --version"
info "Config: $CONFIG_FILE"
info "Installation log: $INSTALL_LOG"
info "The packet service is still stopped; radio firmware setup/verification is the next step"

record_marker "YWD1278_INSTALL=PASS"
record_marker "YWD1278_RUNTIME_CONFIG_READY=$([[ $RUNTIME_CONFIG_READY -eq 1 ]] && echo YES || echo NO)"
record_marker "SERVICE_ENABLED=NO"
record_marker "RF_TRANSMITTED=NO"
record_marker "FLASH_WRITTEN=NO"
