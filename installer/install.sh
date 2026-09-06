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
PENDING_FILE="$STATE_DIR/install-interactive-pending"
BIN_LINK=/usr/local/bin/ywd1278
SKIP_PACKAGES=0
WITH_FIRMWARE_TOOLCHAIN=1
RUN_SETUP=1
STAGING_ROOT=""
BUILD_USER="${YWD1278_BUILD_USER:-${SUDO_USER:-}}"

init_log "$INSTALL_LOG"
banner
info "Detailed installation log: $INSTALL_LOG"

cleanup(){ [[ -z "$STAGING_ROOT" || ! -d "$STAGING_ROOT" ]] || rm -rf "$STAGING_ROOT"; }
trap cleanup EXIT

usage(){
  cat <<'EOF'
Usage: sudo ./installer/install.sh [options]
  --skip-packages            Do not run apt-get
  --no-firmware-toolchain    Do not install compiler/programmer packages
  --setup                    Run station setup after HAT qualification (default)
  --no-setup                 Preserve existing station configuration without prompting
  -h, --help                 Show this help

The guided installer keeps RF transmit disabled. On a stock supported HAT it
will offer one explicit firmware-install confirmation after the Raspberry Pi
UART is ready, preserve a verified stock rollback image, program the exact
qualified AX25R4 image, and independently read it back before station setup.

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

stage "2/4  Prepare the radio UART"
section "Check Raspberry Pi serial configuration"
capture_logged audit "Raspberry Pi UART audit" bash "$SOURCE_ROOT/installer/platform.sh" audit || true
runtime_ready=0; grep -q '^RUNTIME_UART_READY=YES$' <<<"$audit" && runtime_ready=1
serial_console=0; grep -q '^SERIAL_CONSOLE_PRESENT=YES$' <<<"$audit" && serial_console=1

save_resume_state(){
  local quoted_user
  printf -v quoted_user '%q' "$BUILD_USER"
  cat >"$RESUME_STATE" <<EOF
STATE_VERSION=2
DEVICE=/dev/ttyAMA0
RUN_SETUP=$RUN_SETUP
BUILD_USER=$quoted_user
ALLOW_CANDIDATE_RELEASE=0
EOF
  chmod 0600 "$RESUME_STATE"
  touch "$PENDING_FILE"
  chmod 0600 "$PENDING_FILE"
  systemctl enable ywd-1278-install-resume.service >/dev/null
}

if [[ $runtime_ready -ne 1 || $serial_console -eq 1 ]]; then
  warn "The radio UART needs one-time Raspberry Pi boot/serial setup"
  if ! confirm_yes_no "Apply the required UART/serial-console changes?" yes; then
    warn "UART setup declined; firmware and station setup were not started"
    info "Re-run the installer when you are ready to configure the radio UART"
    record_marker "YWD1278_INSTALL=INCOMPLETE"
    record_marker "SERVICE_ENABLED=NO"
    record_marker "RF_TRANSMITTED=NO"
    record_marker "FLASH_WRITTEN=NO"
    exit 0
  fi
  run_logged "Applying Raspberry Pi UART settings" bash "$SOURCE_ROOT/installer/platform.sh" apply || die "Could not apply Raspberry Pi UART settings"
  capture_logged post_apply "Post-apply UART audit" bash "$SOURCE_ROOT/installer/platform.sh" audit || true
  if grep -q '^RUNTIME_UART_READY=YES$' <<<"$post_apply" && grep -q '^SERIAL_CONSOLE_PRESENT=NO$' <<<"$post_apply"; then
    runtime_ready=1
  else
    save_resume_state
    ok "UART repair is staged and the interactive continuation is saved"
    info "After reboot, reconnect and run: sudo $SOURCE_ROOT/installer/resume.sh"
    if confirm_yes_no "Reboot now?" yes; then
      info "Rebooting. The boot-time check will verify the UART only; firmware installation will wait for you to reconnect."
      sync
      sleep 2
      systemctl reboot
      exit 0
    fi
    warn "Reboot deferred. No HAT firmware change has been made."
    info "After the next reboot, run: sudo $SOURCE_ROOT/installer/resume.sh"
    exit 0
  fi
fi

ok "Radio UART is ready"
systemctl disable ywd-1278-install-resume.service >/dev/null 2>&1 || true
rm -f "$RESUME_STATE" "$PENDING_FILE"

continue_args=()
[[ $RUN_SETUP -eq 1 ]] && continue_args+=(--setup) || continue_args+=(--no-setup)
[[ -z "$BUILD_USER" ]] || continue_args+=(--build-user "$BUILD_USER")
YWD1278_SOURCE_ROOT="$SOURCE_ROOT" bash "$SOURCE_ROOT/installer/continue-install.sh" "${continue_args[@]}"
