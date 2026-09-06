#!/usr/bin/env bash
# shellcheck shell=bash

# Human-facing installer presentation. Machine-readable qualification output is
# deliberately kept separate from the terminal UI and can be retained in the
# installer log through record_marker/log_block.
YWD_LOG_FILE="${YWD_LOG_FILE:-}"

if [[ -t 1 && "${NO_COLOR:-}" == "" ]]; then
  YWD_RESET='\033[0m'
  YWD_BOLD='\033[1m'
  YWD_DIM='\033[2m'
  YWD_CYAN='\033[38;5;51m'
  YWD_BLUE='\033[38;5;39m'
  YWD_PURPLE='\033[38;5;141m'
  YWD_GREEN='\033[38;5;82m'
  YWD_AMBER='\033[38;5;214m'
  YWD_RED='\033[38;5;196m'
  YWD_SILVER='\033[38;5;250m'
  YWD_DARK='\033[38;5;242m'
else
  YWD_RESET='' YWD_BOLD='' YWD_DIM='' YWD_CYAN='' YWD_BLUE=''
  YWD_PURPLE='' YWD_GREEN='' YWD_AMBER='' YWD_RED='' YWD_SILVER='' YWD_DARK=''
fi

_ywd_printf(){ printf '%b\n' "$*"; }
_ywd_timestamp(){ date '+%Y-%m-%dT%H:%M:%S%z'; }

_log_event(){
  local level="$1"; shift
  [[ -n "$YWD_LOG_FILE" ]] || return 0
  printf '%s [%s] %s\n' "$(_ywd_timestamp)" "$level" "$*" >>"$YWD_LOG_FILE"
}

init_log(){
  local path="$1"
  install -d -m 0755 "$(dirname -- "$path")"
  touch "$path"
  chmod 0640 "$path"
  YWD_LOG_FILE="$path"
  export YWD_LOG_FILE
  printf '\n===== YWD-1278 INSTALL %s =====\n' "$(_ywd_timestamp)" >>"$YWD_LOG_FILE"
}

log_block(){
  local label="$1" text="${2:-}"
  [[ -n "$YWD_LOG_FILE" ]] || return 0
  printf '\n--- %s [%s] ---\n' "$label" "$(_ywd_timestamp)" >>"$YWD_LOG_FILE"
  [[ -z "$text" ]] || printf '%s\n' "$text" >>"$YWD_LOG_FILE"
}

record_marker(){
  local marker="$1"
  [[ -z "$YWD_LOG_FILE" ]] || printf '%s\n' "$marker" >>"$YWD_LOG_FILE"
  if [[ "${YWD1278_MACHINE_OUTPUT:-0}" == 1 ]]; then
    printf '%s\n' "$marker"
  fi
  # This helper is informational. Hidden human-mode output must never become a
  # fatal status under callers that intentionally use `set -e`.
  return 0
}

run_logged(){
  local label="$1" rc
  shift
  step "$label"
  if [[ -n "$YWD_LOG_FILE" ]]; then
    if "$@" >>"$YWD_LOG_FILE" 2>&1; then
      ok "$label"
      return 0
    fi
    rc=$?
  else
    if "$@"; then
      ok "$label"
      return 0
    fi
    rc=$?
  fi
  fail "$label failed (exit $rc)"
  [[ -z "$YWD_LOG_FILE" ]] || info "Details: $YWD_LOG_FILE"
  return "$rc"
}

capture_logged(){
  local __var="$1" label="$2" output rc
  shift 2
  if output="$("$@" 2>&1)"; then rc=0; else rc=$?; fi
  log_block "$label" "$output"
  printf -v "$__var" '%s' "$output"
  return "$rc"
}

banner(){
  _ywd_printf "${YWD_CYAN}${YWD_BOLD}╔══════════════════════════════════════════════════════╗${YWD_RESET}"
  _ywd_printf "${YWD_CYAN}${YWD_BOLD}║                      YWD-1278                        ║${YWD_RESET}"
  _ywd_printf "${YWD_CYAN}${YWD_BOLD}║            Modern Raspberry Pi Packet TNC           ║${YWD_RESET}"
  _ywd_printf "${YWD_CYAN}${YWD_BOLD}╚══════════════════════════════════════════════════════╝${YWD_RESET}"
}

stage(){
  _log_event STAGE "$*"
  _ywd_printf "\n${YWD_PURPLE}${YWD_BOLD}━━ $* ━━${YWD_RESET}"
}
section(){
  _log_event SECTION "$*"
  _ywd_printf "\n${YWD_BLUE}${YWD_BOLD}==> $*${YWD_RESET}"
}
info(){ _log_event INFO "$*"; _ywd_printf "${YWD_CYAN}[INFO]${YWD_RESET} $*"; }
ok(){ _log_event OK "$*"; _ywd_printf "${YWD_GREEN}[ OK ]${YWD_RESET} $*"; }
warn(){ _log_event WARN "$*"; _ywd_printf "${YWD_AMBER}[WARN]${YWD_RESET} $*"; }
fail(){ _log_event FAIL "$*"; _ywd_printf "${YWD_RED}${YWD_BOLD}[FAIL]${YWD_RESET} $*" >&2; }
die(){ fail "$*"; [[ -z "$YWD_LOG_FILE" ]] || info "Installation log: $YWD_LOG_FILE"; exit 1; }
step(){ _log_event STEP "$*"; _ywd_printf "${YWD_SILVER}  •${YWD_RESET} $*"; }
hint(){ _log_event HINT "$*"; _ywd_printf "${YWD_DARK}    $*${YWD_RESET}"; }

# Interactive installers may be launched by the supported `curl | sudo bash`
# bootstrap. In that case stdin is the curl pipe, not the operator terminal.
# Prefer normal stdin when it is a TTY; otherwise use the controlling terminal
# when available. Non-interactive callers without a controlling terminal still
# fall back to stdin and therefore retain the previous fail-closed behavior.
_ywd_read(){
  local __var="$1" rc
  if [[ -t 0 ]]; then
    IFS= read -r "$__var"
    return
  fi
  if { exec 9</dev/tty; } 2>/dev/null; then
    IFS= read -r "$__var" <&9
    rc=$?
    exec 9<&-
    return "$rc"
  fi
  IFS= read -r "$__var"
}

prompt_default(){
  local prompt="$1" default="$2" value
  printf '%b' "${YWD_SILVER}${prompt}${YWD_RESET} [${default}]: " >&2
  _ywd_read value || value=''
  _log_event INPUT "$prompt=${value:-$default}"
  printf '%s' "${value:-$default}"
}

confirm_yes_no(){
  local prompt="$1" default="${2:-yes}" answer suffix
  [[ "$default" == yes ]] && suffix='Y/n' || suffix='y/N'
  printf '%b' "${YWD_AMBER}${prompt}${YWD_RESET} [${suffix}]: " >&2
  _ywd_read answer || answer=''
  answer="${answer,,}"
  _log_event CONFIRM "$prompt answer=${answer:-default:$default}"
  if [[ -z "$answer" ]]; then [[ "$default" == yes ]]; return; fi
  [[ "$answer" == y || "$answer" == yes ]]
}

confirm_exact(){
  local expected="$1" prompt="$2" answer
  printf '%b' "${YWD_AMBER}${prompt}${YWD_RESET}\nType ${YWD_BOLD}${expected}${YWD_RESET} to continue: "
  _ywd_read answer || return 1
  _log_event CONFIRM "$prompt exact_match=$([[ "$answer" == "$expected" ]] && echo yes || echo no)"
  [[ "$answer" == "$expected" ]]
}

require_root(){
  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    die "This operation must run as root. Re-run with sudo."
  fi
}

command_exists(){ command -v "$1" >/dev/null 2>&1; }
