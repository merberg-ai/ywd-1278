#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# The helper must emit only the selected value on stdout while the human-facing
# prompt remains visible on stderr. This is what allows setup.sh to use
# command-substitution without hiding the question from the operator.
value="$(printf '\n' | NO_COLOR=1 bash -c 'source "$1"; prompt_default "Station callsign (without SSID)" "N0CALL"' _ "$ROOT/installer/lib/ui.sh" 2>"$TMP/prompt")"

[[ "$value" == "N0CALL" ]] || {
  echo "FAIL: default value capture was '$value'" >&2
  exit 1
}

grep -Fq 'Station callsign (without SSID) [N0CALL]:' "$TMP/prompt" || {
  echo "FAIL: setup prompt was not emitted on the visible stream" >&2
  cat "$TMP/prompt" >&2 || true
  exit 1
}

value="$(printf 'KJ6YWD\n' | NO_COLOR=1 bash -c 'source "$1"; prompt_default "Station callsign (without SSID)" "N0CALL"' _ "$ROOT/installer/lib/ui.sh" 2>"$TMP/prompt2")"
[[ "$value" == "KJ6YWD" ]] || {
  echo "FAIL: entered value capture was '$value'" >&2
  exit 1
}

echo 'SETUP_PROMPT_VISIBILITY=PASS'
