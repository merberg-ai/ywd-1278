#!/usr/bin/env python3
"""Guarded 0F-P5d one-event physical beacon acceptance harness.

Dry-run is the default and performs zero device or service I/O. Physical mode
temporarily runs the P5c2 source graph, arms one 10-second runtime beacon through
the actual classic Telnet console, observes exactly one dispatch, immediately
cancels the schedule, and restores the unchanged persistent no-TX appliance.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import qualify_stage_i_single_tx as stage_i  # noqa: E402
from ywd1278.ax25 import parse_frame  # noqa: E402
from ywd1278.kiss.framing import DATA, KISSStreamDecoder  # noqa: E402
from ywd1278.service.appliance import load_product_packet_engine_config  # noqa: E402
from ywd1278.service.classic_tx_console import load_product_classic_tx_config  # noqa: E402


EXPECTED_HOST_COMMIT = "9c9dd3ad30a872b66c7a71e5239c9d85d8948be6"
TEMP_ROOT = Path("/run/ywd-1278-0f-p5d")
TEMP_CONFIG = TEMP_ROOT / "config.toml"
TEMP_LOG = TEMP_ROOT / "daemon.log"
TEMP_KISS_PORT = 18201
TEMP_CONSOLE_PORT = 18210
TEMP_PTY = "/run/ywd-1278-0f-p5d/tnc"

AUTHORIZATION_TOKEN = "0F-P5D-BEACON-145050-ONE"
ARM_PHRASE = "TRANSMIT-0F-P5D-BEACON-ONE"
EXTERNAL_PHRASE = "EXTERNAL-BEACON-DECODE-MATCH-ONE"
DESTINATION = "BEACON"
INFORMATION = "YWD-1278 0F-P5D BEACON 1/1"
INTERVAL_SECONDS = 10
NO_DUPLICATE_HOLD_SECONDS = 12.0
POST_TX_RX_TIMEOUT_SECONDS = 120.0

FROZEN_BLOBS = {
    "src/ywd1278/console/classic_beacon.py": "26b69b2272bf9277cff80e8dfc6c62465e378dad",
    "src/ywd1278/service/classic_beacon.py": "8e1173a58545d3eb88d7afdd839c0746ba53fd2f",
    "src/ywd1278/service/beacon_scheduler.py": "2dab60bdb6289b1f5fbe90a004e7d371f45d7451",
    "src/ywd1278/service/product_beacon_console.py": "5b21ba853c978e9c3e268e47ca6fb24a7f6aa081",
    "src/ywd1278/daemon.py": "565ceb2fb04c3e4a73d66b23a06a3adb2c1aadf8",
    "src/ywd1278/service/appliance.py": "fa1b086d6d8fa40b537c002dbeec34fdc6532396",
    "src/ywd1278/kiss/tx_path.py": "44f4b6c0bddd6ac0977646ac417e448c9a1398ea",
}


def _blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def validate_frozen_capability_blobs() -> None:
    for relative, expected in FROZEN_BLOBS.items():
        actual = _blob(ROOT / relative)
        if actual != expected:
            raise RuntimeError(f"frozen P5d capability mismatch: {relative} actual={actual}")


def make_temporary_tx_config(original: str) -> str:
    text = stage_i.replace_toml_key(original, "radio", "tx_power", str(stage_i.TX_POWER))
    text = stage_i.replace_toml_key(text, "radio", "tx_enabled", "true")
    text = stage_i.replace_toml_key(text, "kiss", "port", str(TEMP_KISS_PORT))
    text = stage_i.replace_toml_key(text, "console", "port", str(TEMP_CONSOLE_PORT))
    text = stage_i.replace_toml_key(text, "console", "pty_link", f'"{TEMP_PTY}"')
    return text


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
    raise RuntimeError(f"console timed out waiting for {needle!r}: {bytes(data)!r}")


def console_command(sock: socket.socket, command: str) -> str:
    sock.sendall(command.encode("ascii") + b"\r\n")
    return _recv_until(sock, b"cmd:").decode("utf-8", "replace")


def wait_for_one_dispatch(console: socket.socket) -> str:
    deadline = time.monotonic() + INTERVAL_SECONDS + stage_i.DISPATCH_TIMEOUT_SECONDS
    last = ""
    while time.monotonic() < deadline:
        last = console_command(console, "STATUS")
        runtime = stage_i.parse_status_mapping(last, "RUNTIME")
        count = stage_i._status_int(runtime, "tx_dispatches")
        if count > 1:
            raise RuntimeError("more than one P5d beacon dispatch occurred")
        if count == 1:
            stage_i.assert_single_shot_status(last, require_dispatched=True)
            return last
        time.sleep(0.1)
    raise RuntimeError(f"timed out waiting for one P5d beacon dispatch: {last!r}")


def recv_post_tx_packet(kiss: socket.socket, *, tx_source: str, timeout: float) -> tuple[bytes, str]:
    decoder = KISSStreamDecoder(max_body_bytes=4096)
    deadline = time.monotonic() + timeout
    kiss.settimeout(0.5)
    while time.monotonic() < deadline:
        try:
            chunk = kiss.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            raise RuntimeError("KISS observer closed while waiting for post-beacon RX")
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
    raise RuntimeError("timed out waiting for a non-qualification post-beacon RX packet")


def expected_external_decode(source: str = "KJ6YWD-10") -> str:
    return f"{source}>{DESTINATION}:{INFORMATION}"


def print_plan(source: str = "KJ6YWD-10") -> None:
    print("===== YWD-1278 0F-P5D ONE-EVENT BEACON ACCEPTANCE =====")
    print(f"HOST_CHECKPOINT={EXPECTED_HOST_COMMIT}")
    print(f"SOURCE={source}")
    print(f"DESTINATION={DESTINATION}")
    print("PATH=DIRECT")
    print(f"INFORMATION={INFORMATION}")
    print(f"EXPECTED_EXTERNAL_DECODE={expected_external_decode(source)}")
    print("TX_FREQUENCY_HZ=145050000")
    print("TX_POWER=200")
    print(f"BEACON_INTERVAL_SECONDS={INTERVAL_SECONDS}")
    print("SCHEDULED_BEACON_EVENTS_MAX=1")
    print("INTERNAL_TX_DISPATCHES_MAX=1")
    print("AUTOMATIC_TX_RETRY=NO")
    print("BEACON_OFF_AFTER_FIRST_DISPATCH=REQUIRED")
    print("PERSISTENT_CONFIG_MUTATED=NO")
    print("CONNECTED_MODE_TX=NO")
    print("FLASH_WRITTEN=NO")
    print("OPTION_BYTES_WRITTEN=NO")


def main() -> int:
    ap = argparse.ArgumentParser(description="0F-P5d guarded one-event physical beacon")
    ap.add_argument("--transmit", action="store_true")
    ap.add_argument("--authorize", default="")
    ap.add_argument("--firmware", type=Path)
    ap.add_argument("--post-rx-timeout", type=float, default=POST_TX_RX_TIMEOUT_SECONDS)
    args = ap.parse_args()

    print_plan()
    if not args.transmit:
        print("YWD1278_0F_P5D_DRY_RUN=PASS")
        print("SERVICE_MUTATED=NO")
        print("MODEM_UART_OPENED=NO")
        print("BEACON_SCHEDULE_ARMED=NO")
        print("RF_TRANSMITTED=NO")
        return 0

    if os.geteuid() != 0:
        raise SystemExit("[FAIL] physical P5d requires root")
    if args.authorize != AUTHORIZATION_TOKEN:
        raise SystemExit(f"[FAIL] exact authorization required: --authorize {AUTHORIZATION_TOKEN}")
    if args.firmware is None:
        raise SystemExit("[FAIL] --firmware is required")
    if args.post_rx_timeout <= 0:
        raise SystemExit("[FAIL] --post-rx-timeout must be positive")

    validate_frozen_capability_blobs()
    ancestry = stage_i._run(
        ["git", "merge-base", "--is-ancestor", EXPECTED_HOST_COMMIT, "HEAD"],
        check=False,
    )
    if ancestry.returncode != 0:
        raise SystemExit("[FAIL] source checkout does not descend from the P5c2 host checkpoint")
    for path in (stage_i.PERSISTENT_CONFIG, stage_i.INSTALLED_COMMIT, stage_i.VENV_PYTHON, stage_i.ELIGIBILITY):
        if not path.exists():
            raise SystemExit(f"[FAIL] required qualified-appliance path missing: {path}")
    installed = stage_i.INSTALLED_COMMIT.read_text(encoding="utf-8").strip()
    if installed != stage_i.EXPECTED_INSTALLED_COMMIT:
        raise SystemExit(f"[FAIL] installed appliance commit mismatch: {installed}")
    if stage_i._systemctl_state("is-enabled") != "enabled" or stage_i._systemctl_state("is-active") != "active":
        raise SystemExit("[FAIL] normal appliance must be enabled and active")

    original_bytes = stage_i.PERSISTENT_CONFIG.read_bytes()
    original_hash = hashlib.sha256(original_bytes).hexdigest()
    original_text = original_bytes.decode("utf-8")
    source = stage_i.validate_persistent_config(tomllib.loads(original_text))
    stage_i._check_firmware(args.firmware)
    stage_i._verify_eligibility(args.firmware)

    print("===== P5D PRE-ARM QUALIFIED STATE =====")
    print(f"PERSISTENT_CONFIG_SHA256={original_hash}")
    print("PERSISTENT_TX_ENABLED=NO")
    print("PERSISTENT_BEACON_ENABLED=NO")
    typed = input(f"Type exactly {ARM_PHRASE} to arm ONE scheduled RF beacon: ").strip()
    if typed != ARM_PHRASE:
        raise SystemExit("[FAIL] P5d interactive arm phrase did not match")

    daemon: subprocess.Popen[str] | None = None
    log_handle = None
    service_stopped = False
    tx_dispatched = False
    cleanup_error: BaseException | None = None
    pty_leaked = False
    try:
        stage_i._run(["systemctl", "stop", stage_i.SERVICE])
        service_stopped = True
        if stage_i._systemctl_state("is-active") not in ("inactive", "failed", "unknown"):
            raise RuntimeError("normal service did not stop")
        if Path("/run/ywd-1278/tnc").exists():
            raise RuntimeError("normal PTY leaked after service stop")
        if stage_i._run(["fuser", stage_i.DEVICE], check=False).returncode == 0:
            raise RuntimeError("UART remained owned after normal service stop")
        stage_i._verify_hardware_identity()
        if TEMP_ROOT.exists():
            raise RuntimeError(f"stale P5d runtime directory exists: {TEMP_ROOT}")
        TEMP_ROOT.mkdir(mode=0o700, parents=True)
        TEMP_CONFIG.write_text(make_temporary_tx_config(original_text), encoding="utf-8")
        os.chmod(TEMP_CONFIG, 0o600)
        packet_cfg = load_product_packet_engine_config(TEMP_CONFIG)
        classic_cfg = load_product_classic_tx_config(TEMP_CONFIG)
        if not packet_cfg.tx_enabled or packet_cfg.tx_power != stage_i.TX_POWER or packet_cfg.frequency_hz != stage_i.EXPECTED_FREQUENCY_HZ:
            raise RuntimeError("temporary P5d TX profile failed validation")
        if not classic_cfg.configured or str(classic_cfg.source) != source:
            raise RuntimeError("temporary P5d station identity failed validation")

        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        log_handle = TEMP_LOG.open("w", encoding="utf-8")
        daemon = subprocess.Popen(
            [sys.executable, "-m", "ywd1278.daemon", "--config", str(TEMP_CONFIG)],
            cwd=str(ROOT), env=env, stdout=log_handle, stderr=subprocess.STDOUT, text=True,
        )
        stage_i._wait_port(TEMP_KISS_PORT, 6.0)
        stage_i._wait_port(TEMP_CONSOLE_PORT, 6.0)
        if daemon.poll() is not None:
            raise RuntimeError(f"temporary P5d daemon exited early rc={daemon.returncode}")

        with socket.create_connection(("127.0.0.1", TEMP_KISS_PORT), timeout=3.0) as kiss, socket.create_connection(("127.0.0.1", TEMP_CONSOLE_PORT), timeout=3.0) as console:
            if "TELNET TNC CONSOLE" not in _recv_until(console, b"cmd:").decode("utf-8", "replace"):
                raise RuntimeError("actual classic Telnet console was not reached")
            stage_i.assert_single_shot_status(console_command(console, "STATUS"), require_dispatched=False)

            reply = console_command(console, f"BTEXT {INFORMATION}")
            if "BTEXT SET BYTES=26" not in reply:
                raise RuntimeError(f"BTEXT setup failed: {reply!r}")
            reply = console_command(console, f"UNPROTO {DESTINATION}")
            if f"UNPROTO DEST={DESTINATION} VIA=DIRECT" not in reply:
                raise RuntimeError(f"UNPROTO setup failed: {reply!r}")
            reply = console_command(console, f"BEACON EVERY {INTERVAL_SECONDS}")
            if "TX-ELIGIBLE" not in reply:
                raise RuntimeError(f"BEACON arm failed: {reply!r}")
            print("BEACON_RUNTIME_ARMED=YES")

            wait_for_one_dispatch(console)
            tx_dispatched = True
            reply = console_command(console, "BEACON OFF")
            if "BEACON OFF" not in reply:
                raise RuntimeError("BEACON OFF failed after first dispatch")
            print("P5D_AUTHORIZATION_CONSUMED=YES")
            print("TX_DISPATCHES=1")
            print("BEACON_OFF_AFTER_FIRST_DISPATCH=PASS")

            time.sleep(NO_DUPLICATE_HOLD_SECONDS)
            stage_i.assert_single_shot_status(console_command(console, "STATUS"), require_dispatched=True)
            print("NO_SECOND_DISPATCH_AFTER_FULL_INTERVAL=PASS")

            print(f"EXPECTED_EXTERNAL_DECODE={expected_external_decode(source)}")
            external = input(f"After an independent receiver decoded that exact frame ONCE, type {EXTERNAL_PHRASE}: ").strip()
            if external != EXTERNAL_PHRASE:
                raise RuntimeError("independent exact beacon decode not confirmed; no retry permitted")
            print("INDEPENDENT_EXTERNAL_DECODE_COUNT=1")

            print("Generate or wait for one different normal 145.050 packet.")
            rx_body, rx_source = recv_post_tx_packet(kiss, tx_source=source, timeout=float(args.post_rx_timeout))
            print("POST_TX_RX_RESUMED=PASS")
            print(f"POST_TX_RX_FRAME_BYTES={len(rx_body)}")
            print(f"POST_TX_RX_SOURCE={rx_source}")
            stage_i.assert_single_shot_status(console_command(console, "STATUS"), require_dispatched=True)
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
                stage_i._restore_service(original_hash)
            except BaseException as exc:
                cleanup_error = exc
        if pty_leaked and cleanup_error is None:
            cleanup_error = RuntimeError("temporary P5d PTY leaked")
        if cleanup_error is not None:
            raise cleanup_error

    if not tx_dispatched:
        raise SystemExit("[FAIL] P5d ended without its one dispatch")
    if stage_i._systemctl_state("is-enabled") != "enabled" or stage_i._systemctl_state("is-active") != "active":
        raise SystemExit("[FAIL] normal no-TX appliance was not restored")
    restored = stage_i.PERSISTENT_CONFIG.read_bytes()
    if hashlib.sha256(restored).hexdigest() != original_hash:
        raise SystemExit("[FAIL] persistent config changed during P5d")
    stage_i.validate_persistent_config(tomllib.loads(restored.decode("utf-8")))

    print("YWD1278_0F_P5D_ONE_EVENT_BEACON=PASS")
    print("SCHEDULED_BEACON_EVENTS=1")
    print("INTERNAL_TX_DISPATCHES=1")
    print("AUTOMATIC_TX_RETRY=NO")
    print("BEACON_ENABLED_FINAL=NO")
    print("PERSISTENT_TX_ENABLED=NO")
    print("PERSISTENT_CONFIG_MUTATED=NO")
    print("NORMAL_SERVICE_RESTORED=YES")
    print("POST_TX_RX_RESUMED=PASS")
    print("FLASH_WRITTEN=NO")
    print("OPTION_BYTES_WRITTEN=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
