#!/usr/bin/env python3
"""0F-P4 guarded one-shot classic-console physical TX qualification.

Default invocation is a zero-I/O dry run. Physical mode is intentionally narrow:
validate the frozen 0F P1/P2/P3 implementation and the qualified no-TX appliance,
stop the normal service, launch the exact checkout product daemon against a
root-only temporary /run config with the qualified 145.050 MHz / power-200 TX
profile, use one persistent classic Telnet session to set a DIRECT UNPROTO,
enter CONVERSE, submit exactly one fixed text line, immediately return to
COMMAND mode, prove exactly one internal dispatch and no duplicate after a hold,
require operator confirmation of one exact independent over-air decode, prove a
later RX packet, then tear the temporary runtime down and restore the unchanged
persistent no-TX service.

The persistent /etc/ywd-1278/config.toml is never modified. This harness sends no
KISS DATA, owns no firmware-flash/GPIO/reset/option-byte path, has no beacon or
connected-mode path, and has no automatic TX retry.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.ax25 import parse_frame  # noqa: E402
from ywd1278.kiss.framing import DATA, KISSStreamDecoder  # noqa: E402
from ywd1278.service.appliance import load_product_packet_engine_config  # noqa: E402
from ywd1278.service.classic_tx_console import load_product_classic_tx_config  # noqa: E402

HOST_QUALIFIED_CHECKPOINT = "3b9bc5c7e212872606ba36d7fa30338b00cd9ce3"
EXPECTED_INSTALLED_COMMIT = "2f5299e65add072fea6ee55a54dc421faf00c276"
EXPECTED_TARGET = "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"
EXPECTED_IDENTITY = (
    "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz "
    "ADF7021 FW based on CA6JAU GitID #7ff74ed"
)
EXPECTED_FIRMWARE_SHA256 = "b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616"
EXPECTED_FIRMWARE_SIZE = 59892
EXPECTED_FREQUENCY_HZ = 145_050_000
TX_POWER = 200
SERVICE = "ywd-1278.service"
PERSISTENT_CONFIG = Path("/etc/ywd-1278/config.toml")
INSTALLED_COMMIT = Path("/opt/ywd-1278/installed-commit")
VENV_PYTHON = Path("/opt/ywd-1278/venv/bin/python")
INSTALLED_SOURCE = Path("/opt/ywd-1278/source")
ELIGIBILITY = Path("/var/lib/ywd-1278/firmware-ready.json")
DEVICE = "/dev/ttyAMA0"
NORMAL_KISS_PORT = 8001
NORMAL_CONSOLE_PORT = 8010
TEMP_ROOT = Path("/run/ywd-1278-0f-p4")
TEMP_CONFIG = TEMP_ROOT / "config.toml"
TEMP_LOG = TEMP_ROOT / "daemon.log"
TEMP_KISS_PORT = 18101
TEMP_CONSOLE_PORT = 18110
TEMP_PTY = "/run/ywd-1278-0f-p4/tnc"
AUTHORIZATION_TOKEN = "0F-P4-TX-145050-ONE"
ARM_PHRASE = "TRANSMIT-0F-P4-ONE"
EXTERNAL_PHRASE = "EXTERNAL-DECODE-MATCH-ONE"
DESTINATION = "YWD127"
INFORMATION = "YWD-1278 0F-P4 CLASSIC TX 1/1"
DISPATCH_TIMEOUT_SECONDS = 45.0
NO_DUPLICATE_HOLD_SECONDS = 2.0
POST_TX_RX_TIMEOUT_SECONDS = 120.0

# These are the host-qualified P1/P2/P3 capability owners.  P4 refuses to run
# if any of them differs from the frozen checkpoint even if unrelated staging
# files have moved the branch HEAD forward.
FROZEN_BLOBS = {
    "src/ywd1278/console/classic.py": "4d6dfd5d439fb5dfd6ff586c2a47c37724381b2e",
    "src/ywd1278/console/classic_tx.py": "e920bf5d26a0b7b2005a374384b3dda68996fc4c",
    "src/ywd1278/service/classic_tx_console.py": "579cab015b20556dd9354e91edfd307e3120db8c",
    "src/ywd1278/service/appliance.py": "fa1b086d6d8fa40b537c002dbeec34fdc6532396",
    "src/ywd1278/ax25/codec.py": "866a500d9f3a5d3fc80f6918d07ff83a6672ad64",
    "src/ywd1278/kiss/tx_path.py": "44f4b6c0bddd6ac0977646ac417e448c9a1398ea",
}


def _git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def _run(args: list[str], *, check: bool = True, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=None if cwd is None else str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=check,
    )


def _systemctl_state(kind: str) -> str:
    return _run(["systemctl", kind, SERVICE], check=False).stdout.strip()


def _bool(root: dict, table: str, key: str) -> bool:
    value = root.get(table, {}).get(key) if isinstance(root.get(table), dict) else None
    if not isinstance(value, bool):
        raise ValueError(f"invalid [{table}] {key}")
    return value


def _station_source(root: dict) -> str:
    station = root.get("station")
    if not isinstance(station, dict):
        raise ValueError("missing [station]")
    callsign = station.get("callsign")
    ssid = station.get("ssid")
    if not isinstance(callsign, str) or not callsign.strip():
        raise ValueError("invalid station.callsign")
    if isinstance(ssid, bool) or not isinstance(ssid, int) or not 0 <= ssid <= 15:
        raise ValueError("invalid station.ssid")
    call = callsign.strip().upper()
    return call if ssid == 0 else f"{call}-{ssid}"


def validate_persistent_config(root: dict) -> str:
    hardware = root.get("hardware")
    radio = root.get("radio")
    firmware = root.get("firmware")
    beacon = root.get("beacon")
    console = root.get("console")
    if not all(isinstance(item, dict) for item in (hardware, radio, firmware, beacon, console)):
        raise ValueError("required product config tables are missing")
    if hardware.get("target") != EXPECTED_TARGET:
        raise ValueError("unexpected hardware target")
    if radio.get("device") != DEVICE:
        raise ValueError("unexpected modem UART")
    if float(radio.get("frequency_mhz", 0.0)) != 145.05:
        raise ValueError("frequency is not 145.050 MHz")
    if _bool(root, "radio", "tx_enabled"):
        raise ValueError("persistent TX must be disabled before 0F-P4")
    if _bool(root, "firmware", "allow_automatic_flash"):
        raise ValueError("automatic flash must remain disabled")
    if _bool(root, "beacon", "enabled"):
        raise ValueError("beacon must remain disabled")
    if not _bool(root, "console", "enabled"):
        raise ValueError("classic console must be enabled")
    if console.get("listen") != "127.0.0.1":
        raise ValueError("0F-P4 requires loopback classic Telnet")
    source = _station_source(root)
    if source != "KJ6YWD-10":
        raise ValueError(f"0F-P4 fixed source requires KJ6YWD-10, got {source}")
    return source


def replace_toml_key(text: str, section: str, key: str, rendered_value: str) -> str:
    lines = text.splitlines(keepends=True)
    current = ""
    changed = 0
    out: list[str] = []
    section_re = re.compile(r"^\s*\[([^]]+)\]\s*(?:#.*)?(?:\r?\n)?$")
    key_re = re.compile(rf"^(\s*){re.escape(key)}\s*=.*?(\r?\n)?$")
    for line in lines:
        section_match = section_re.match(line)
        if section_match:
            current = section_match.group(1).strip()
            out.append(line)
            continue
        key_match = key_re.match(line)
        if current == section and key_match:
            newline = key_match.group(2) or "\n"
            out.append(f"{key_match.group(1)}{key} = {rendered_value}{newline}")
            changed += 1
        else:
            out.append(line)
    if changed != 1:
        raise ValueError(f"expected exactly one [{section}] {key}, changed={changed}")
    return "".join(out)


def make_temporary_tx_config(original: str) -> str:
    text = original
    text = replace_toml_key(text, "radio", "tx_power", str(TX_POWER))
    text = replace_toml_key(text, "radio", "tx_enabled", "true")
    text = replace_toml_key(text, "kiss", "port", str(TEMP_KISS_PORT))
    text = replace_toml_key(text, "console", "port", str(TEMP_CONSOLE_PORT))
    text = replace_toml_key(text, "console", "pty_link", f'"{TEMP_PTY}"')
    return text


def validate_checkout() -> str:
    if _run(["git", "status", "--porcelain"], cwd=ROOT).stdout.strip():
        raise RuntimeError("0F-P4 requires a clean checkout")
    head = _run(["git", "rev-parse", "HEAD"], cwd=ROOT).stdout.strip()
    ancestry = _run(
        ["git", "merge-base", "--is-ancestor", HOST_QUALIFIED_CHECKPOINT, head],
        check=False,
        cwd=ROOT,
    )
    if ancestry.returncode != 0:
        raise RuntimeError("checkout does not descend from frozen 0F host-qualified checkpoint")
    for relative, expected in FROZEN_BLOBS.items():
        actual = _git_blob(ROOT / relative)
        if actual != expected:
            raise RuntimeError(f"frozen 0F capability blob mismatch: {relative} actual={actual}")
    return head


def _check_firmware(firmware: Path) -> None:
    if not firmware.is_file():
        raise RuntimeError(f"firmware artifact missing: {firmware}")
    data = firmware.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if len(data) != EXPECTED_FIRMWARE_SIZE or digest != EXPECTED_FIRMWARE_SHA256:
        raise RuntimeError("firmware artifact size/hash mismatch")


def _verify_eligibility(firmware: Path) -> None:
    proc = _run(
        [
            str(VENV_PYTHON),
            "-m",
            "ywd1278.install.firmware_trust",
            "--profile",
            str(INSTALLED_SOURCE / "firmware/product-ax25r4.json"),
            "check-eligibility",
            "--config",
            str(PERSISTENT_CONFIG),
            "--firmware",
            str(firmware),
            "--record",
            str(ELIGIBILITY),
        ]
    )
    print(proc.stdout, end="")
    if "SERVICE_ELIGIBLE=YES" not in proc.stdout:
        raise RuntimeError("Stage-F firmware/service eligibility did not revalidate")


def _verify_hardware_identity() -> None:
    proc = _run(
        [
            "bash",
            str(INSTALLED_SOURCE / "installer/hardware-detect.sh"),
            "--device",
            DEVICE,
            "--config",
            str(PERSISTENT_CONFIG),
        ]
    )
    print(proc.stdout, end="")
    target = identity = ""
    for line in proc.stdout.splitlines():
        if line.startswith("DETECTED_TARGET="):
            target = line.split("=", 1)[1]
        elif line.startswith("DETECTED_IDENTITY="):
            identity = line.split("=", 1)[1]
    if target != EXPECTED_TARGET or identity != EXPECTED_IDENTITY:
        raise RuntimeError("exact qualified HAT target/identity recheck failed")


def _wait_port(port: int, timeout: float = 6.0) -> None:
    deadline = time.monotonic() + timeout
    last: OSError | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError as exc:
            last = exc
            time.sleep(0.1)
    raise RuntimeError(f"loopback port {port} did not become ready: {last}")


def _recv_until(sock: socket.socket, needle: bytes, timeout: float = 4.0) -> bytes:
    sock.settimeout(0.5)
    deadline = time.monotonic() + timeout
    data = bytearray()
    while time.monotonic() < deadline:
        if needle in data:
            return bytes(data)
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            break
        data.extend(chunk)
    raise RuntimeError(f"classic console closed/timed out waiting for {needle!r}: {bytes(data)!r}")


def console_command(sock: socket.socket, command: str) -> str:
    sock.sendall(command.encode("ascii") + b"\r\n")
    return _recv_until(sock, b"cmd:", 4.0).decode("utf-8", "replace")


def parse_status_mapping(text: str, label: str) -> dict[str, str]:
    prefix = label.upper() + " "
    for raw in text.replace("\r", "\n").split("\n"):
        line = raw.strip()
        if line.startswith(prefix):
            result: dict[str, str] = {}
            for token in line[len(prefix):].split():
                if "=" in token:
                    key, value = token.split("=", 1)
                    result[key] = value
            return result
    raise ValueError(f"STATUS did not contain {label}")


def _status_int(mapping: dict[str, str], key: str) -> int:
    try:
        return int(mapping[key])
    except (KeyError, ValueError) as exc:
        raise RuntimeError(f"missing/invalid STATUS field {key}: {mapping}") from exc


def assert_single_shot_status(text: str, *, require_dispatched: bool) -> None:
    runtime = parse_status_mapping(text, "RUNTIME")
    ingress = parse_status_mapping(text, "INGRESS")
    queue = parse_status_mapping(text, "QUEUE")
    backend = parse_status_mapping(text, "BACKEND")
    dispatches = _status_int(runtime, "tx_dispatches")
    accepted = _status_int(queue, "tx_queue_accepted")
    dispatched = _status_int(queue, "tx_dispatched")
    depth = _status_int(queue, "tx_queue_depth")
    received = _status_int(ingress, "data_messages_received")
    admitted = _status_int(ingress, "data_admitted")
    expected = (1, 1, 1, 0, 1, 1) if require_dispatched else (0, 0, 0, 0, 0, 0)
    actual = (dispatches, accepted, dispatched, depth, received, admitted)
    if actual != expected:
        raise RuntimeError(f"0F-P4 single-shot accounting mismatch expected={expected} actual={actual}")
    for key in ("tx_invalid_rejections", "tx_queue_full_drops", "tx_access_timeouts", "tx_downstream_failures"):
        if _status_int(queue, key) != 0:
            raise RuntimeError(f"unexpected queue failure counter {key}")
    for key in ("data_invalid_rejections", "data_queue_full_drops", "data_time_rejections", "data_other_rejections"):
        if _status_int(ingress, key) != 0:
            raise RuntimeError(f"unexpected ingress failure counter {key}")
    if _status_int(backend, "subscriber_drops") != 0:
        raise RuntimeError("subscriber drops are non-zero")
    if runtime.get("failure", "") not in ("", "-"):
        raise RuntimeError(f"runtime failure is non-empty: {runtime.get('failure')}")


def wait_for_one_dispatch(console: socket.socket, timeout: float = DISPATCH_TIMEOUT_SECONDS) -> str:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        last = console_command(console, "STATUS")
        tx = _status_int(parse_status_mapping(last, "RUNTIME"), "tx_dispatches")
        if tx > 1:
            raise RuntimeError("more than one 0F-P4 TX dispatch occurred")
        if tx == 1:
            assert_single_shot_status(last, require_dispatched=True)
            return last
        time.sleep(0.1)
    raise RuntimeError(f"timed out waiting for one 0F-P4 TX dispatch; last={last!r}")


def recv_post_tx_non_qualification(kiss: socket.socket, *, tx_source: str, timeout: float) -> tuple[bytes, str]:
    decoder = KISSStreamDecoder(max_body_bytes=4096)
    deadline = time.monotonic() + timeout
    kiss.settimeout(0.5)
    while time.monotonic() < deadline:
        try:
            chunk = kiss.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            raise RuntimeError("KISS RX observer closed while waiting for post-TX RX")
        for message in decoder.feed(chunk):
            if message.port != 0 or message.command != DATA or not message.frame:
                continue
            try:
                parsed = parse_frame(message.frame, has_fcs=False)
            except ValueError:
                continue
            source = str(parsed["source"])
            info = bytes(parsed["info"])
            if source == tx_source and info == INFORMATION.encode("ascii"):
                continue
            return message.frame, source
    raise RuntimeError("timed out waiting for a later non-qualification RX packet")


def _restore_service(original_hash: str) -> None:
    if hashlib.sha256(PERSISTENT_CONFIG.read_bytes()).hexdigest() != original_hash:
        raise RuntimeError("persistent config changed during 0F-P4; normal service left stopped fail-closed")
    _run(["systemctl", "start", SERVICE])
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        if _systemctl_state("is-active") == "active":
            try:
                _wait_port(NORMAL_KISS_PORT, 0.5)
                _wait_port(NORMAL_CONSOLE_PORT, 0.5)
                return
            except RuntimeError:
                pass
        time.sleep(0.1)
    raise RuntimeError("normal no-TX service did not recover after 0F-P4")


def expected_external_decode(source: str = "KJ6YWD-10") -> str:
    return f"{source}>{DESTINATION}:{INFORMATION}"


def print_plan(source: str = "KJ6YWD-10") -> None:
    print("===== YWD-1278 0F-P4 CLASSIC CONSOLE SINGLE-SHOT TX =====")
    print(f"SOURCE={source}")
    print(f"DESTINATION={DESTINATION}")
    print("PATH=DIRECT")
    print(f"INFORMATION={INFORMATION}")
    print(f"EXPECTED_EXTERNAL_DECODE={expected_external_decode(source)}")
    print("TX_FREQUENCY_HZ=145050000")
    print("TX_POWER=200")
    print("TX_ORIGIN=CLASSIC_TELNET_CONVERSE")
    print("KISS_TX_MESSAGES=0")
    print("MAX_INTERNAL_TX_DISPATCHES=1")
    print("AUTOMATIC_TX_RETRY=NO")
    print("PERSISTENT_CONFIG_MUTATED=NO")
    print("BEACON_ENABLED=NO")
    print("CONNECTED_MODE=NO")
    print("FLASH_PERMITTED=NO")
    print("OPTION_BYTES_PERMITTED=NO")


def main() -> int:
    ap = argparse.ArgumentParser(description="0F-P4 guarded classic-console single-shot physical TX")
    ap.add_argument("--transmit", action="store_true")
    ap.add_argument("--authorize", default="")
    ap.add_argument("--firmware", type=Path)
    ap.add_argument("--post-rx-timeout", type=float, default=POST_TX_RX_TIMEOUT_SECONDS)
    args = ap.parse_args()

    print_plan()
    if not args.transmit:
        print("YWD1278_0F_P4_DRY_RUN=PASS")
        print("SERVICE_MUTATED=NO")
        print("MODEM_UART_OPENED=NO")
        print("CLASSIC_TX_LINE_SENT=NO")
        print("KISS_DATA_SENT=NO")
        print("RF_TRANSMITTED=NO")
        return 0

    if os.geteuid() != 0:
        raise SystemExit("[FAIL] physical 0F-P4 requires root")
    if args.authorize != AUTHORIZATION_TOKEN:
        raise SystemExit(f"[FAIL] exact authorization required: --authorize {AUTHORIZATION_TOKEN}")
    if args.firmware is None:
        raise SystemExit("[FAIL] --firmware is required in physical mode")
    if args.post_rx_timeout <= 0:
        raise SystemExit("[FAIL] --post-rx-timeout must be positive")

    checkout_head = validate_checkout()
    for path in (PERSISTENT_CONFIG, INSTALLED_COMMIT, VENV_PYTHON, ELIGIBILITY):
        if not path.exists():
            raise SystemExit(f"[FAIL] required qualified-appliance path missing: {path}")
    installed = INSTALLED_COMMIT.read_text(encoding="utf-8").strip()
    if installed != EXPECTED_INSTALLED_COMMIT:
        raise SystemExit(f"[FAIL] installed product commit mismatch: {installed}")
    if _systemctl_state("is-enabled") != "enabled" or _systemctl_state("is-active") != "active":
        raise SystemExit("[FAIL] qualified normal service must be enabled and active before 0F-P4")

    original_bytes = PERSISTENT_CONFIG.read_bytes()
    original_hash = hashlib.sha256(original_bytes).hexdigest()
    original_text = original_bytes.decode("utf-8")
    persistent_root = tomllib.loads(original_text)
    source = validate_persistent_config(persistent_root)
    _check_firmware(args.firmware)
    _verify_eligibility(args.firmware)

    print("===== 0F-P4 PRE-ARM QUALIFIED STATE =====")
    print(f"CHECKOUT_HEAD={checkout_head}")
    print(f"HOST_QUALIFIED_ANCESTOR={HOST_QUALIFIED_CHECKPOINT}")
    print(f"INSTALLED_APPLIANCE_COMMIT={installed}")
    print(f"PERSISTENT_CONFIG_SHA256={original_hash}")
    print("PERSISTENT_TX_ENABLED=NO")
    print("PERSISTENT_BEACON_ENABLED=NO")
    print(f"EXPECTED_EXTERNAL_DECODE={expected_external_decode(source)}")
    typed = input(f"Type exactly {ARM_PHRASE} to arm ONE 0F-P4 RF frame: ").strip()
    if typed != ARM_PHRASE:
        raise SystemExit("[FAIL] 0F-P4 interactive TX arm phrase did not match")

    daemon: subprocess.Popen[str] | None = None
    log_handle = None
    service_stopped = False
    tx_dispatched = False
    cleanup_error: BaseException | None = None
    pty_leaked = False
    try:
        _run(["systemctl", "stop", SERVICE])
        service_stopped = True
        if _systemctl_state("is-active") not in ("inactive", "failed", "unknown"):
            raise RuntimeError("normal service did not stop")
        if Path("/run/ywd-1278/tnc").exists():
            raise RuntimeError("normal PTY leaked after service stop")
        if _run(["fuser", DEVICE], check=False).returncode == 0:
            raise RuntimeError("UART remained owned after normal service stop")
        _verify_hardware_identity()

        if TEMP_ROOT.exists():
            raise RuntimeError(f"stale 0F-P4 runtime directory exists: {TEMP_ROOT}")
        TEMP_ROOT.mkdir(mode=0o700, parents=True)
        temp_text = make_temporary_tx_config(original_text)
        TEMP_CONFIG.write_text(temp_text, encoding="utf-8")
        os.chmod(TEMP_CONFIG, 0o600)
        packet_cfg = load_product_packet_engine_config(TEMP_CONFIG)
        classic_cfg = load_product_classic_tx_config(TEMP_CONFIG, tx_enabled=packet_cfg.tx_enabled)
        if not packet_cfg.tx_enabled or packet_cfg.tx_power != TX_POWER or packet_cfg.frequency_hz != EXPECTED_FREQUENCY_HZ:
            raise RuntimeError("temporary 0F-P4 TX profile failed product config validation")
        if not classic_cfg.enabled or str(classic_cfg.source) != source:
            raise RuntimeError("temporary 0F-P4 classic console identity failed validation")

        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        log_handle = TEMP_LOG.open("w", encoding="utf-8")
        daemon = subprocess.Popen(
            [sys.executable, "-m", "ywd1278.daemon", "--config", str(TEMP_CONFIG)],
            cwd=str(ROOT),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        _wait_port(TEMP_KISS_PORT, 6.0)
        _wait_port(TEMP_CONSOLE_PORT, 6.0)
        if daemon.poll() is not None:
            raise RuntimeError(f"temporary 0F product daemon exited early rc={daemon.returncode}")

        with socket.create_connection(("127.0.0.1", TEMP_KISS_PORT), timeout=3.0) as kiss, socket.create_connection(("127.0.0.1", TEMP_CONSOLE_PORT), timeout=3.0) as console:
            banner = _recv_until(console, b"cmd:", 3.0).decode("utf-8", "replace")
            if "TELNET TNC CONSOLE" not in banner:
                raise RuntimeError("did not reach actual product classic Telnet console")
            baseline = console_command(console, "STATUS")
            assert_single_shot_status(baseline, require_dispatched=False)
            print("0F_P4_TEMP_PRODUCT_DAEMON=RUNNING")
            print("PRODUCT_TX=ENABLED_TEMPORARILY")
            print("KISS_TX_MESSAGES=0")

            unproto = console_command(console, f"UNPROTO {DESTINATION}")
            if f"UNPROTO DEST={DESTINATION} VIA=DIRECT" not in unproto:
                raise RuntimeError(f"UNPROTO direct setup failed: {unproto!r}")
            converse = console_command(console, "CONVERSE")
            if f"CONVERSE MODE DEST={DESTINATION} VIA=DIRECT" not in converse:
                raise RuntimeError(f"CONVERSE entry failed: {converse!r}")
            print("CLASSIC_UNPROTO_DIRECT=PASS")
            print("CLASSIC_CONVERSE_ENTERED=PASS")

            # The one and only frame-producing operation in P4. There is no
            # retry around this command and this harness never sends KISS DATA.
            queued = console_command(console, INFORMATION)
            if "TX QUEUED REQUEST=" not in queued or f"DEST={DESTINATION}" not in queued or "VIA=DIRECT" not in queued:
                raise RuntimeError(f"classic converse line was not admitted: {queued!r}")
            print("CLASSIC_CONVERSE_TX_LINE_SENT=ONE")

            command_mode = console_command(console, "COMMAND")
            if "COMMAND MODE" not in command_mode:
                raise RuntimeError("classic console did not return to command mode immediately")
            print("CLASSIC_COMMAND_MODE_RESTORED=PASS")

            status = wait_for_one_dispatch(console)
            tx_dispatched = True
            print("0F_P4_AUTHORIZATION_CONSUMED=YES")
            runtime = parse_status_mapping(status, "RUNTIME")
            queue = parse_status_mapping(status, "QUEUE")
            ingress = parse_status_mapping(status, "INGRESS")
            print(f"TX_DISPATCHES={runtime['tx_dispatches']}")
            print(f"TX_QUEUE_ACCEPTED={queue['tx_queue_accepted']}")
            print(f"TX_QUEUE_DISPATCHED={queue['tx_dispatched']}")
            print(f"BACKEND_DATA_ADMITTED={ingress['data_admitted']}")
            print("KISS_TX_MESSAGES=0")
            print("AUTOMATIC_TX_RETRY=NO")

            time.sleep(NO_DUPLICATE_HOLD_SECONDS)
            stable = console_command(console, "STATUS")
            assert_single_shot_status(stable, require_dispatched=True)
            print("NO_SECOND_INTERNAL_DISPATCH_AFTER_HOLD=PASS")

            print("===== INDEPENDENT OVER-AIR DECODE GATE =====")
            print(f"EXPECTED_EXTERNAL_DECODE={expected_external_decode(source)}")
            external = input(
                f"After an independent receiver decoded that exact frame ONCE, type {EXTERNAL_PHRASE}: "
            ).strip()
            if external != EXTERNAL_PHRASE:
                raise RuntimeError("independent exact external decode was not confirmed; no retry is permitted")
            print("INDEPENDENT_EXTERNAL_DECODE_CONFIRMED=YES")
            print("INDEPENDENT_EXTERNAL_DECODE_COUNT=1")

            print("===== POST-TX RX-RESUME GATE =====")
            print("WAITING_FOR_LATER_NON_QUALIFICATION_PACKET_145050=YES")
            print("Generate or wait for one normal 145.050 packet that is not the 0F-P4 TX frame.")
            rx_body, rx_source = recv_post_tx_non_qualification(
                kiss, tx_source=source, timeout=float(args.post_rx_timeout)
            )
            print("POST_TX_RX_RESUMED=PASS")
            print(f"POST_TX_RX_FRAME_BYTES={len(rx_body)}")
            print(f"POST_TX_RX_SOURCE={rx_source}")

            final = console_command(console, "STATUS")
            assert_single_shot_status(final, require_dispatched=True)
            runtime_final = parse_status_mapping(final, "RUNTIME")
            if _status_int(runtime_final, "decoded_rx_frames") < 1:
                raise RuntimeError("runtime did not account a decoded RX frame after 0F-P4 TX")
            print("FINAL_TX_DISPATCHES=1")
            print("TX_QUEUE_DEPTH_FINAL=0")
            print("SUBSCRIBER_DROPS_FINAL=0")
            print("TX_ACCESS_TIMEOUTS_FINAL=0")
            print("TX_DOWNSTREAM_FAILURES_FINAL=0")

    finally:
        if daemon is not None and daemon.poll() is None:
            daemon.send_signal(signal.SIGTERM)
            try:
                daemon.wait(timeout=8.0)
            except subprocess.TimeoutExpired:
                daemon.kill()
                daemon.wait(timeout=2.0)
        if log_handle is not None:
            log_handle.close()
        pty_leaked = Path(TEMP_PTY).exists()
        if TEMP_ROOT.exists():
            shutil.rmtree(TEMP_ROOT)
        if service_stopped:
            try:
                _restore_service(original_hash)
            except BaseException as exc:
                cleanup_error = exc
        if pty_leaked and cleanup_error is None:
            cleanup_error = RuntimeError("temporary 0F-P4 PTY leaked after daemon teardown")
        if cleanup_error is not None:
            raise cleanup_error

    if not tx_dispatched:
        raise SystemExit("[FAIL] 0F-P4 physical path ended without a TX dispatch")
    if _systemctl_state("is-enabled") != "enabled" or _systemctl_state("is-active") != "active":
        raise SystemExit("[FAIL] normal no-TX service was not restored")
    restored_bytes = PERSISTENT_CONFIG.read_bytes()
    if hashlib.sha256(restored_bytes).hexdigest() != original_hash:
        raise SystemExit("[FAIL] persistent config hash changed during 0F-P4")
    validate_persistent_config(tomllib.loads(restored_bytes.decode("utf-8")))

    print("===== 0F-P4 CLASSIC CONSOLE SINGLE-SHOT TX COMPLETE =====")
    print("YWD1278_0F_P4_CLASSIC_TX=PASS")
    print("CLASSIC_UNPROTO_TO_CONVERSE_TO_PRODUCT_TX=PASS")
    print("CLASSIC_CONVERSE_TX_LINES=1")
    print("KISS_TX_MESSAGES=0")
    print("INTERNAL_TX_DISPATCH_COUNT=1")
    print("INDEPENDENT_EXTERNAL_DECODE_COUNT=1")
    print("AUTOMATIC_TX_RETRY=NO")
    print("POST_TX_RX_RESUMED=PASS")
    print("PERSISTENT_TX_ENABLED=NO")
    print("PERSISTENT_CONFIG_MUTATED=NO")
    print("NORMAL_SERVICE_RESTORED=YES")
    print("BEACON_TX=NO")
    print("CONNECTED_MODE_TX=NO")
    print("FLASH_WRITTEN=NO")
    print("OPTION_BYTES_WRITTEN=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
