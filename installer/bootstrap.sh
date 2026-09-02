#!/usr/bin/env bash
# Standalone curl-friendly YWD-1278 bootstrap.
set -Eeuo pipefail

REPO_URL="${YWD1278_REPO_URL:-https://github.com/merberg-ai/ywd-1278.git}"
BRANCH="${YWD1278_BRANCH:-main}"
FORWARD=(--setup)

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
  C=$'\033[38;5;51m'; G=$'\033[38;5;82m'; A=$'\033[38;5;214m'; R=$'\033[0m'; B=$'\033[1m'
else C=''; G=''; A=''; R=''; B=''; fi
printf '%b\n' "${C}${B}YWD-1278 — bootstrap installer${R}"
printf '%b\n' "${A}Repository:${R} $REPO_URL"
printf '%b\n' "${A}Channel:${R}    $BRANCH"

if ! command -v git >/dev/null 2>&1; then
  command -v apt-get >/dev/null 2>&1 || { echo "git is missing and apt-get is unavailable" >&2; exit 3; }
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-install-recommends ca-certificates git
fi

tmp="$(mktemp -d /tmp/ywd1278-bootstrap.XXXXXX)"
cleanup(){ rm -rf "$tmp"; }
trap cleanup EXIT

echo "Fetching YWD-1278..."
git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$tmp/repo"
[[ -x "$tmp/repo/installer/install.sh" ]] || { echo "Fetched source has no installer/install.sh" >&2; exit 4; }

printf '%b\n' "${G}[ OK ]${R} Source fetched; starting full installer"
bash "$tmp/repo/installer/install.sh" "${FORWARD[@]}"
