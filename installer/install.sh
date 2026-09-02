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
BIN_LINK=/usr/local/bin/ywd1278
SKIP_PACKAGES=0
WITH_FIRMWARE_TOOLCHAIN=1
RUN_SETUP=0

usage(){
  cat <<'EOF'
Usage: sudo ./installer/install.sh [options]

Options:
  --skip-packages            Do not run apt-get
  --no-firmware-toolchain    Skip compiler/programmer packages
  --setup                    Run the interactive setup wizard after install
  -h, --help                 Show this help

The alpha0 installer installs the framework and systemd unit but deliberately
leaves ywd-1278.service DISABLED. It does not flash firmware.
EOF
}

while (($#)); do
  case "$1" in
    --skip-packages) SKIP_PACKAGES=1 ;;
    --no-firmware-toolchain) WITH_FIRMWARE_TOOLCHAIN=0 ;;
    --setup) RUN_SETUP=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
  shift
done

section "Platform preflight"
[[ -r /proc/device-tree/model ]] || die "Unable to identify Raspberry Pi model (/proc/device-tree/model missing)"
model="$(tr -d '\0' </proc/device-tree/model)"
[[ "$model" == *"Raspberry Pi"* ]] || die "Unsupported host for the initial YWD-1278 installer: $model"
ok "Detected: $model"

[[ -r /etc/os-release ]] || die "/etc/os-release not found"
# shellcheck disable=SC1091
source /etc/os-release
case "${ID:-}:${ID_LIKE:-}" in
  debian:*|raspbian:*|*:debian*) ok "Debian-family OS: ${PRETTY_NAME:-unknown}" ;;
  *) die "Initial installer supports Raspberry Pi OS/Debian-family systems only: ${PRETTY_NAME:-unknown}" ;;
esac

command_exists systemctl || die "systemd is required"
command_exists python3 || [[ $SKIP_PACKAGES -eq 0 ]] || die "python3 missing and --skip-packages was requested"

if [[ $SKIP_PACKAGES -eq 0 ]]; then
  section "Dependencies"
  export DEBIAN_FRONTEND=noninteractive
  step "Refreshing apt metadata"
  apt-get update
  packages=(
    ca-certificates git python3 python3-venv python3-pip python3-setuptools
    python3-wheel sqlite3 build-essential pkg-config
  )
  if [[ $WITH_FIRMWARE_TOOLCHAIN -eq 1 ]]; then
    packages+=(gcc-arm-none-eabi binutils-arm-none-eabi stm32flash)
  fi
  step "Installing: ${packages[*]}"
  apt-get install -y --no-install-recommends "${packages[@]}"
  ok "Dependencies installed"
else
  warn "Package installation skipped by request"
fi

for cmd in python3 git systemctl tar sha256sum; do
  command_exists "$cmd" || die "Required command missing after dependency step: $cmd"
done

section "Filesystem layout"
install -d -m 0755 "$INSTALL_ROOT" "$SOURCE_ROOT" "$CONFIG_DIR" "$STATE_DIR" "$BACKUP_DIR" "$LOG_DIR"
# Backups can contain the user's original device firmware; keep the directory private.
chmod 0700 "$BACKUP_DIR"

if [[ -d "$SOURCE_ROOT" && -n "$(find "$SOURCE_ROOT" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
  stamp="$(date +%Y%m%d-%H%M%S)"
  old="$INSTALL_ROOT/source.pre-install.$stamp"
  mv "$SOURCE_ROOT" "$old"
  install -d -m 0755 "$SOURCE_ROOT"
  info "Previous installed source preserved at $old"
fi

step "Copying source tree into $SOURCE_ROOT"
tar -C "$REPO_ROOT" --exclude=.git --exclude='__pycache__' --exclude='*.pyc' -cf - . | tar -C "$SOURCE_ROOT" -xf -

version="$(tr -d '[:space:]' <"$REPO_ROOT/VERSION")"
commit="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || printf 'unknown')"
printf '%s\n' "$version" >"$INSTALL_ROOT/installed-version"
printf '%s\n' "$commit" >"$INSTALL_ROOT/installed-commit"

section "Python environment"
rm -rf "$VENV"
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --disable-pip-version-check --no-cache-dir "$SOURCE_ROOT"
ln -sfn "$VENV/bin/ywd1278" "$BIN_LINK"
ok "Installed YWD-1278 $version ($commit)"

section "Configuration"
if [[ ! -f "$CONFIG_FILE" ]]; then
  install -m 0640 "$SOURCE_ROOT/config/ywd-1278.example.toml" "$CONFIG_FILE"
  ok "Installed safe default configuration"
else
  ok "Preserved existing configuration: $CONFIG_FILE"
fi

section "systemd"
install -m 0644 "$SOURCE_ROOT/systemd/ywd-1278.service" "$UNIT_DST"
systemctl daemon-reload
systemctl disable --now ywd-1278.service >/dev/null 2>&1 || true
ok "Installed ywd-1278.service (disabled/inactive by design)"

section "Framework self-test"
"$VENV/bin/ywd1278d" --config "$CONFIG_FILE" --framework-self-test
ok "Framework self-test passed"

section "Firmware safety state"
warn "No firmware was flashed."
warn "The alpha0 flash tool refuses writes until an allowlisted target has a qualified firmware artifact and checksum."
step "Probe/flash tooling: $SOURCE_ROOT/firmware/flash.sh"
step "Stock restore tooling: $SOURCE_ROOT/firmware/restore-stock.sh"
step "Protected firmware backups: $BACKUP_DIR"

if [[ $RUN_SETUP -eq 1 ]]; then
  section "Interactive setup"
  YWD1278_SOURCE_ROOT="$SOURCE_ROOT" bash "$SOURCE_ROOT/installer/setup.sh"
fi

section "Install complete"
ok "YWD-1278 framework installed"
info "CLI: ywd1278 --version"
info "Config: $CONFIG_FILE"
info "Service remains disabled until the packet engine/firmware port is qualified."
info "Run setup later with: sudo $SOURCE_ROOT/installer/setup.sh"
