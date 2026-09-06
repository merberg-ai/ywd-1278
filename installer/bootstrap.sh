#!/usr/bin/env bash
# Standalone curl-friendly YWD-1278 bootstrap.
set -Eeuo pipefail

REPO_URL="${YWD1278_REPO_URL:-https://github.com/merberg-ai/ywd-1278.git}"
BRANCH="${YWD1278_BRANCH:-main}"
FORWARD=(--setup)
LOG_DIR=/var/log/ywd-1278
INSTALL_LOG="$LOG_DIR/install.log"

while (($#)); do
  case "$1" in
    --branch) BRANCH="${2:?missing branch}"; shift ;;
    --repo) REPO_URL="${2:?missing repo URL}"; shift ;;
    --no-setup) FORWARD=(--no-setup) ;;
    --skip-packages|--no-firmware-toolchain) FORWARD+=("$1") ;;
    -h|--help)
      cat <<EOF
YWD-1278 bootstrap
Usage: curl -fsSL <bootstrap-url> | sudo bash -s -- [--branch main|dev]
EOF
      exit 0 ;;
    *) echo "Unknown bootstrap option: $1" >&2; exit 2 ;;
  esac
  shift
done

[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "YWD-1278 bootstrap must run as root (pipe it to sudo bash)." >&2; exit 1; }

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  C=$'\033[38;5;51m'; P=$'\033[38;5;141m'; G=$'\033[38;5;82m'; A=$'\033[38;5;214m'; E=$'\033[38;5;196m'; S=$'\033[38;5;250m'; R=$'\033[0m'; B=$'\033[1m'
else C=''; P=''; G=''; A=''; E=''; S=''; R=''; B=''; fi

install -d -m 0755 "$LOG_DIR"
touch "$INSTALL_LOG"
chmod 0640 "$INSTALL_LOG"
printf '\n===== YWD-1278 BOOTSTRAP %s =====\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" >>"$INSTALL_LOG"
printf 'REPOSITORY=%s\nCHANNEL=%s\n' "$REPO_URL" "$BRANCH" >>"$INSTALL_LOG"

printf '%b\n' "${C}${B}YWD-1278 — Packet TNC Installer${R}"
printf '%b\n' "${P}${B}━━ Bootstrap ━━${R}"
printf '%b\n' "${C}[INFO]${R} Channel: $BRANCH"
printf '%b\n' "${C}[INFO]${R} Detailed installation log: $INSTALL_LOG"

if ! command -v git >/dev/null 2>&1; then
  command -v apt-get >/dev/null 2>&1 || { printf '%b\n' "${E}[FAIL]${R} git is missing and apt-get is unavailable" >&2; exit 3; }
  export DEBIAN_FRONTEND=noninteractive
  printf '%b\n' "${S}  •${R} Preparing bootstrap requirements"
  if ! { apt-get update && apt-get install -y --no-install-recommends ca-certificates git; } >>"$INSTALL_LOG" 2>&1; then
    printf '%b\n' "${E}[FAIL]${R} Could not install bootstrap requirements" >&2
    printf '%b\n' "${C}[INFO]${R} Details: $INSTALL_LOG"
    exit 3
  fi
  printf '%b\n' "${G}[ OK ]${R} Bootstrap requirements ready"
fi

tmp="$(mktemp -d /tmp/ywd1278-bootstrap.XXXXXX)"
cleanup(){ rm -rf "$tmp"; }
trap cleanup EXIT

printf '%b\n' "${S}  •${R} Fetching YWD-1278"
if ! git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$tmp/repo" >>"$INSTALL_LOG" 2>&1; then
  printf '%b\n' "${E}[FAIL]${R} Could not fetch YWD-1278" >&2
  printf '%b\n' "${C}[INFO]${R} Details: $INSTALL_LOG"
  exit 4
fi
[[ -x "$tmp/repo/installer/install.sh" ]] || { printf '%b\n' "${E}[FAIL]${R} Fetched source has no installer/install.sh" >&2; exit 4; }
printf '%b\n' "${G}[ OK ]${R} YWD-1278 source ready"

# With the supported `curl | sudo bash` entry point, stdin belongs to curl.
# Reattach the full interactive installer to the caller's controlling terminal
# when one exists. This preserves prompt input while keeping non-interactive
# callers fail-closed if no terminal is available.
if { exec 3</dev/tty; } 2>/dev/null; then
  bash "$tmp/repo/installer/install.sh" "${FORWARD[@]}" <&3
  rc=$?
  exec 3<&-
  exit "$rc"
fi

bash "$tmp/repo/installer/install.sh" "${FORWARD[@]}"
