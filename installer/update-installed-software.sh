#!/usr/bin/env bash
set -Eeuo pipefail

# 0F-P9 software-only installed appliance update.
# No HAT detection, firmware build/programming, GPIO manipulation, config
# mutation, modem access, or RF operation occurs here.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALL_ROOT=/opt/ywd-1278
SOURCE_ROOT="$INSTALL_ROOT/source"
VENV="$INSTALL_ROOT/venv"
CONFIG=/etc/ywd-1278/config.toml
UNIT_SOURCE_REL=systemd/ywd-1278.service
UNIT_INSTALLED=/etc/systemd/system/ywd-1278.service
SERVICE=ywd-1278.service
EXPECTED_SOURCE_COMMIT=""
DRY_RUN=0

usage(){
  cat <<'EOF'
Usage:
  sudo ./installer/update-installed-software.sh \
    --expected-source-commit SHA

Options:
  --expected-source-commit SHA  Exact checkout commit to install.
  --dry-run                     Print the bounded plan and perform zero writes,
                                service changes, UART access, or RF I/O.

This is a software-only update path for an already-qualified appliance. The
persistent configuration must have radio.tx_enabled=false before the update.
EOF
}

while (($#)); do
  case "$1" in
    --expected-source-commit) EXPECTED_SOURCE_COMMIT="${2:?missing commit}"; shift ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[FAIL] unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

echo "===== YWD-1278 0F-P9 SOFTWARE-ONLY INSTALLED UPDATE ====="
echo "SOURCE_TREE=$REPO_ROOT"
echo "PERSISTENT_TX_REQUIRED=DISABLED"
echo "CONFIG_MUTATION=NO"
echo "FIRMWARE_ACTION=NO"
echo "MODEM_UART_ACCESS=NO"
echo "RF_TRANSMITTED=NO"
if [[ $DRY_RUN -eq 1 ]]; then
  echo "YWD1278_0F_P9_SOFTWARE_UPDATE_DRY_RUN=PASS"
  echo "INSTALLED_SOURCE_MUTATED=NO"
  echo "SYSTEMD_MUTATED=NO"
  echo "PERSISTENT_CONFIG_MUTATED=NO"
  echo "FLASH_WRITTEN=NO"
  echo "OPTION_BYTES_WRITTEN=NO"
  exit 0
fi

[[ $EUID -eq 0 ]] || { echo "[FAIL] root is required" >&2; exit 3; }
[[ "$EXPECTED_SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo "[FAIL] --expected-source-commit must be a full lowercase SHA" >&2; exit 3; }
for path in "$REPO_ROOT/.git" "$REPO_ROOT/pyproject.toml" "$REPO_ROOT/$UNIT_SOURCE_REL" "$CONFIG"; do
  [[ -e "$path" ]] || { echo "[FAIL] required path missing: $path" >&2; exit 4; }
done

actual_source_commit="$(git -C "$REPO_ROOT" rev-parse HEAD)"
[[ "$actual_source_commit" == "$EXPECTED_SOURCE_COMMIT" ]] || {
  echo "[FAIL] checkout commit mismatch: actual=$actual_source_commit expected=$EXPECTED_SOURCE_COMMIT" >&2
  exit 4
}
[[ -z "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=no)" ]] || {
  echo "[FAIL] tracked source tree is dirty; refusing installed update" >&2
  exit 4
}

persistent_tx="$(python3 - "$CONFIG" <<'PY'
import sys,tomllib
with open(sys.argv[1],'rb') as f: d=tomllib.load(f)
v=d.get('radio',{}).get('tx_enabled')
if not isinstance(v,bool): raise SystemExit(2)
print('true' if v else 'false')
PY
)" || { echo "[FAIL] cannot validate persistent radio.tx_enabled" >&2; exit 5; }
[[ "$persistent_tx" == false ]] || { echo "[FAIL] persistent TX must be disabled before software update" >&2; exit 5; }

old_commit="$(tr -d '[:space:]' <"$INSTALL_ROOT/installed-commit" 2>/dev/null || true)"
[[ "$old_commit" =~ ^[0-9a-f]{40}$ ]] || { echo "[FAIL] existing installed-commit is missing or invalid" >&2; exit 5; }
[[ -d "$SOURCE_ROOT" && -x "$VENV/bin/python" ]] || { echo "[FAIL] existing installed source/venv is incomplete" >&2; exit 5; }

work="$(mktemp -d /var/tmp/ywd1278-p9-update.XXXXXX)"
cleanup(){ rm -rf "$work"; }
trap cleanup EXIT
candidate_source="$work/source"
wheel_dir="$work/wheel"
mkdir -p "$candidate_source" "$wheel_dir"
tar -C "$REPO_ROOT" --exclude=.git --exclude='__pycache__' --exclude='*.pyc' -cf - . | tar -C "$candidate_source" -xf -

# Build the candidate artifact before disturbing the running appliance.
"$VENV/bin/python" -m pip wheel --disable-pip-version-check --no-deps --wheel-dir "$wheel_dir" "$candidate_source" >/dev/null
mapfile -t wheels < <(find "$wheel_dir" -maxdepth 1 -type f -name '*.whl' -print)
[[ ${#wheels[@]} -eq 1 ]] || { echo "[FAIL] expected exactly one candidate wheel" >&2; exit 5; }
wheel="${wheels[0]}"

service_was_active="$(systemctl is-active "$SERVICE" 2>/dev/null || true)"
service_was_enabled="$(systemctl is-enabled "$SERVICE" 2>/dev/null || true)"
timestamp="$(date +%Y%m%d-%H%M%S)"
source_backup="$INSTALL_ROOT/source.pre-0f-p9.$timestamp"
venv_backup="$INSTALL_ROOT/venv.pre-0f-p9.$timestamp"
unit_backup="$work/ywd-1278.service.old"
commit_backup="$work/installed-commit.old"
cp -a "$UNIT_INSTALLED" "$unit_backup"
printf '%s\n' "$old_commit" >"$commit_backup"

systemctl stop "$SERVICE" >/dev/null 2>&1 || true
rollback_armed=0
rollback(){
  rc=$?
  if [[ ${rollback_armed:-0} -eq 1 ]]; then
    echo "[ROLLBACK] restoring pre-P9 installed software" >&2
    systemctl stop "$SERVICE" >/dev/null 2>&1 || true
    rm -rf "$SOURCE_ROOT" "$VENV"
    [[ ! -d "$source_backup" ]] || mv "$source_backup" "$SOURCE_ROOT"
    [[ ! -d "$venv_backup" ]] || mv "$venv_backup" "$VENV"
    cp -a "$unit_backup" "$UNIT_INSTALLED"
    cp -a "$commit_backup" "$INSTALL_ROOT/installed-commit"
    systemctl daemon-reload >/dev/null 2>&1 || true
    if [[ "$service_was_enabled" == enabled ]]; then systemctl enable "$SERVICE" >/dev/null 2>&1 || true; else systemctl disable "$SERVICE" >/dev/null 2>&1 || true; fi
    if [[ "$service_was_active" == active ]]; then systemctl start "$SERVICE" >/dev/null 2>&1 || true; else systemctl stop "$SERVICE" >/dev/null 2>&1 || true; fi
  fi
  exit "$rc"
}
trap rollback ERR INT TERM
rollback_armed=1

mv "$SOURCE_ROOT" "$source_backup"
mv "$VENV" "$venv_backup"
mkdir -p "$SOURCE_ROOT"
tar -C "$candidate_source" -cf - . | tar -C "$SOURCE_ROOT" -xf -
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --disable-pip-version-check --no-deps "$wheel" >/dev/null
install -m 0644 "$SOURCE_ROOT/$UNIT_SOURCE_REL" "$UNIT_INSTALLED"
printf '%s\n' "$EXPECTED_SOURCE_COMMIT" >"$INSTALL_ROOT/installed-commit"
systemctl daemon-reload

# Installed-package self-test is still zero modem/RF I/O.
"$VENV/bin/ywd1278d" --config "$CONFIG" --framework-self-test >/dev/null

if [[ "$service_was_enabled" == enabled ]]; then systemctl enable "$SERVICE" >/dev/null; else systemctl disable "$SERVICE" >/dev/null; fi
if [[ "$service_was_active" == active ]]; then
  systemctl start "$SERVICE"
  for _ in {1..50}; do
    [[ "$(systemctl is-active "$SERVICE" 2>/dev/null || true)" == active ]] && break
    sleep 0.1
  done
  [[ "$(systemctl is-active "$SERVICE" 2>/dev/null || true)" == active ]] || { echo "[FAIL] updated RX-safe product service did not become active" >&2; false; }
fi

rollback_armed=0
trap - ERR INT TERM

echo "YWD1278_0F_P9_SOFTWARE_UPDATE=PASS"
echo "PREVIOUS_INSTALLED_COMMIT=$old_commit"
echo "INSTALLED_COMMIT=$EXPECTED_SOURCE_COMMIT"
echo "PERSISTENT_TX_ENABLED=NO"
echo "SERVICE_ACTIVE_AFTER_UPDATE=$([[ "$service_was_active" == active ]] && echo YES || echo NO)"
echo "SERVICE_ENABLED_AFTER_UPDATE=$([[ "$service_was_enabled" == enabled ]] && echo YES || echo NO)"
echo "CONFIG_MUTATED=NO"
echo "FIRMWARE_ACTION=NO"
echo "MODEM_UART_ACCESS=NO"
echo "RF_TRANSMITTED=NO"
echo "FLASH_WRITTEN=NO"
echo "OPTION_BYTES_WRITTEN=NO"
