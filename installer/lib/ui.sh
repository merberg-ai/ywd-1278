#!/usr/bin/env bash
# shellcheck shell=bash

if [[ -t 1 && "${NO_COLOR:-}" == "" ]]; then
  YWD_RESET='\033[0m'
  YWD_BOLD='\033[1m'
  YWD_DIM='\033[2m'
  YWD_CYAN='\033[38;5;51m'
  YWD_BLUE='\033[38;5;39m'
  YWD_GREEN='\033[38;5;82m'
  YWD_AMBER='\033[38;5;214m'
  YWD_RED='\033[38;5;196m'
  YWD_SILVER='\033[38;5;250m'
else
  YWD_RESET='' YWD_BOLD='' YWD_DIM='' YWD_CYAN='' YWD_BLUE=''
  YWD_GREEN='' YWD_AMBER='' YWD_RED='' YWD_SILVER=''
fi

_ywd_printf(){ printf '%b\n' "$*"; }

banner(){
  _ywd_printf "${YWD_CYAN}${YWD_BOLD}╔══════════════════════════════════════════════════════╗${YWD_RESET}"
  _ywd_printf "${YWD_CYAN}${YWD_BOLD}║                      YWD-1278                        ║${YWD_RESET}"
  _ywd_printf "${YWD_CYAN}${YWD_BOLD}║            Modern Raspberry Pi Packet TNC           ║${YWD_RESET}"
  _ywd_printf "${YWD_CYAN}${YWD_BOLD}╚══════════════════════════════════════════════════════╝${YWD_RESET}"
}

section(){ _ywd_printf "\n${YWD_BLUE}${YWD_BOLD}==> $*${YWD_RESET}"; }
info(){ _ywd_printf "${YWD_CYAN}[INFO]${YWD_RESET} $*"; }
ok(){ _ywd_printf "${YWD_GREEN}[ OK ]${YWD_RESET} $*"; }
warn(){ _ywd_printf "${YWD_AMBER}[WARN]${YWD_RESET} $*"; }
fail(){ _ywd_printf "${YWD_RED}[FAIL]${YWD_RESET} $*" >&2; }
die(){ fail "$*"; exit 1; }
step(){ _ywd_printf "${YWD_SILVER}  •${YWD_RESET} $*"; }

prompt_default(){
  local prompt="$1" default="$2" value
  printf '%b' "${YWD_SILVER}${prompt}${YWD_RESET} [${default}]: " >&2
  IFS= read -r value
  printf '%s' "${value:-$default}"
}

confirm_yes_no(){
  local prompt="$1" default="${2:-yes}" answer suffix
  [[ "$default" == yes ]] && suffix='Y/n' || suffix='y/N'
  printf '%b' "${YWD_AMBER}${prompt}${YWD_RESET} [${suffix}]: " >&2
  IFS= read -r answer || answer=''
  answer="${answer,,}"
  if [[ -z "$answer" ]]; then [[ "$default" == yes ]]; return; fi
  [[ "$answer" == y || "$answer" == yes ]]
}

confirm_exact(){
  local expected="$1" prompt="$2" answer
  printf '%b' "${YWD_AMBER}${prompt}${YWD_RESET}\nType ${YWD_BOLD}${expected}${YWD_RESET} to continue: "
  IFS= read -r answer
  [[ "$answer" == "$expected" ]]
}

require_root(){
  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    die "This operation must run as root. Re-run with sudo."
  fi
}

command_exists(){ command -v "$1" >/dev/null 2>&1; }
