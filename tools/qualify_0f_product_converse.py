#!/usr/bin/env python3
"""Guarded physical qualification of the permanent product converse session.

Dry-run is the default and performs no device, service, UART, or RF I/O.
Physical mode uses the current checkout's product daemon against a temporary
root-only config while the installed qualified no-TX service is stopped. It
permits exactly one classic converse text line to enter the existing product TX
admission path, requires an independent exact over-air decode, proves a later
live RX frame is rendered back inside that same converse session, exits with
/CMD, verifies single-shot accounting/no drops, then restores the byte-identical
persistent no-TX service.

The persistent config, firmware, option bytes, and installed source are never
modified by this harness.
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
sys.path.insert(0, str(ROOT / "tools"))

import qualify_stage_i_single_tx as stage_i  # noqa: E402
from ywd1278.service.appliance import load_product_packet_engine_config  # noqa: E402
from ywd1278.service.classic_tx_console import load_product_classic_tx_config  # noqa: E402


TEMP_ROOT = Path("/run/ywd-1278-0f-product-converse")
TEMP_CONFIG = TEMP_ROOT / "config.toml"
TEMP_LOG = TEMP_ROOT / "daemon.log"
TEMP_KISS_PORT = 18201
TEMP_CONSOLE_PORT = 18210
TEMP_PTY = "/run/ywd-1278-0f-product-converse/tnc"
AUTHORIZATION_TOKEN = "0F-PRODUCT-CONVERSE-TX-145050-ONE"
ARM_PHRASE = "TRANSMIT-0F-PRODUCT-CONVERSE-ONE"
EXTERNAL_PHRASE = "EXTERNAL-DECODE-MATCH-ONE"
DESTINATION = "YWD127"
INFORMATION = "YWD-1278 PRODUCT CONVERSE 1/1"
NO_DUPLICATE_HOLD_SECONDS = 2.0
LIVE_RX_TIMEOUT_SECONDS = 120.0

# Product/session implementation frozen at the host-qualified dev composition.
FROZEN_PRODUCT_BLOBS = {
    "src/ywd1278/console/product_session.py": "591aff36d2b403f4e7792ce05ac0b33400051ce1",
    "src/ywd1278/service/product_converse_console.py": "797262d60529d1c234b9dc5c453916b471411d76",
    "src/ywd1278/daemon.py": "dddf39c4a45ae542f618cbf649fd5b10746c1555",
    "src/ywd1278/monitor/stream.py": "703b7e803d39d915b60d79c30c154151e3820098",
    "src/ywd1278/console/classic_tx.py": "e920bf5d26a0b7b2005a374384b3dda68996fc4c",
    "src/ywd1278/service/classic_tx_console.py": "579cab015b20556dd9354e91edfd307e3120db8c",
    "src/ywd1278/service/appliance.py": "fa1b086d6d8fa40b537c002dbeec34fdc6532396",
}


def _blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def validate_product_blobs() -> None:
    for relative, expected in FROZEN_PRODUCT_BLOBS.items():
        actual = _blob(ROOT / relative)
        if actual != expected:
            raise RuntimeError(
                f"product capability blob mismatch: {relative} actual={actual} expected={expected}"
            )


def make_temporary_tx_config(original: str) -> str:
    text = stage_i.replace_toml_key(original, "radio", "tx_power", str(stage_i.TX_POWER))
    text = stage_i.replace_toml_key(text, "radio", "tx_enabled", "true")
    text = stage_i.replace_toml_key(text, "kiss", "port", str(TEMP_KISS_PORT))
    text = stage_i.replace_toml_key(text, "console", "port", str(TEMP_CONSOLE_PORT))
    text = stage_i.replace_toml_key(text, "console", "pty_link", f'"{TEMP_PTY}"')
    return text


def expected_external_decode(source: str = "KJ6YWD-10") -> str:
    return f"{source}>{DESTINATION}:{INFORMATION}"


def _recv_until(sock: socket.socket, needle: bytes, timeout: float = 4.0) -> bytes:
    sock.settimeout(0.25)
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


def _recv_quiet(sock: socket.socket, duration: float = 0.25) -> bytes:
    deadline = time.monotonic() + duration
    data = bytearray()
    sock.settimeout(0.05)
    while time.monotonic() < deadline:
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data)


def command_with_prompt(sock: socket.socket, command: str) -> str:
    sock.sendall(command.encode("ascii") + b"\r\n")
    return _recv_until(sock, b"cmd:").decode("utf-8", "replace")


def enter_converse(sock: socket.socket) -> str:
    sock.sendall(b"CONVERSE\r\n")
    data = _recv_until(sock, b"PRE-CONVERSE HISTORY NOT REPLAYED\r\n")
    data += _recv_quiet(sock)
    text = data.decode("utf-8", "replace")
    if "cmd:" in text:
        raise RuntimeError("product prompt was not suppressed in converse mode")
    if "LIVE RX DISPLAY ENABLED" not in text:
        raise RuntimeError(f"live RX was not enabled entering converse: {text!r}")
    return text


def send_one_converse_line(sock: socket.socket) -> str:
    sock.sendall(INFORMATION.encode("ascii") + b"\r\n")
    data = _recv_until(sock, b"TX QUEUED REQUEST=")
    data += _recv_quiet(sock)
    text = data.decode("utf-8", "replace")
    if "cmd:" in text:
        raise RuntimeError("product prompt appeared after converse TX line")
    if f"DEST={DESTINATION}" not in text or "VIA=DIRECT" not in text:
        raise RuntimeError(f"converse TX admission reply was incomplete: {text!r}")
    return text


def wait_live_rx(sock: socket.socket, *, timeout: float) -> str:
    data = _recv_until(sock, b"RX ", timeout=timeout)
    text = data.decode("utf-8", "replace")
    for raw in text.replace("\r", "\n").split("\n"):
        line = raw.strip()
        if line.startswith("RX "):
            return line
    raise RuntimeError(f"RX marker arrived without a complete monitor line: {text!r}")


def exit_converse(sock: socket.socket) -> str:
    sock.sendall(b"/CMD\r\n")
    text = _recv_until(sock, b"cmd:").decode("utf-8", "replace")
    if "COMMAND MODE" not in text:
        raise RuntimeError(f"/CMD did not restore command mode: {text!r}")
    return text


def print_plan(source: str = "KJ6YWD-10") -> None:
    print("===== YWD-1278 PRODUCT CONVERSE PHYSICAL QUALIFIER =====")
    print(f"SOURCE={source}")
    print(f"DESTINATION={DESTINATION}")
    print("PATH=DIRECT")
    print(f"INFORMATION={INFORMATION}")
    print(f"EXPECTED_EXTERNAL_DECODE={expected_external_decode(source)}")
    print("TX_FREQUENCY_HZ=145050000")
    print(f"TX_POWER={stage_i.TX_POWER}")
    print("TX_ORIGIN=PRODUCT_TELNET_CONVERSE")
    print("CLASSIC_CONVERSE_TX_LINES_MAX=1")
    print("LIVE_RX_REQUIRED_IN_SAME_SESSION=YES")
    print("PRE_CONVERSE_HISTORY_REPLAY=NO")
    print("PRINTABLE_ESCAPE=/CMD")
    print("AUTOMATIC_TX_RETRY=NO")
    print("PERSISTENT_TX_ENABLED=NO")
    print("PERSISTENT_CONFIG_MUTATED=NO")
    print("INSTALLED_SOURCE_MUTATED=NO")
    print("FLASH_WRITTEN=NO")
    print("OPTION_BYTES_WRITTEN=NO")


def _valid_commit(text: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{40}", text))


def main() -> int:
    ap = argparse.ArgumentParser(description="guarded product converse live-session physical qualification")
    ap.add_argument("--transmit", action="store_true")
    ap.add_argument("--authorize", default="")
    ap.add_argument("--firmware", type=Path)
    ap.add_argument("--live-rx-timeout", type=float, default=LIVE_RX_TIMEOUT_SECONDS)
    args = ap.parse_args()

    print_plan()
    validate_product_blobs()
    if not args.transmit:
        print("YWD1278_0F_PRODUCT_CONVERSE_DRY_RUN=PASS")
        print("SERVICE_MUTATED=NO")
        print("MODEM_UART_OPENED=NO")
        print("CONVERSE_TX_LINE_SENT=NO")
        print("RF_TRANSMITTED=NO")
        return 0

    if os.geteuid() != 0:
        raise SystemExit("[FAIL] physical product converse qualification requires root")
    if args.authorize != AUTHORIZATION_TOKEN:
        raise SystemExit(f"[FAIL] exact authorization required: --authorize {AUTHORIZATION_TOKEN}")
    if args.firmware is None:
        raise SystemExit("[FAIL] --firmware is required in physical mode")
    if args.live_rx_timeout <= 0:
        raise SystemExit("[FAIL] --live-rx-timeout must be positive")

    required = (
        stage_i.PERSISTENT_CONFIG,
        stage_i.INSTALLED_COMMIT,
        stage_i.VENV_PYTHON,
        stage_i.ELIGIBILITY,
    )
    for path in required:
        if not path.exists():
            raise SystemExit(f"[FAIL] required qualified-appliance path missing: {path}")
    installed_baseline = stage_i.INSTALLED_COMMIT.read_text(encoding="utf-8").strip()
    if not _valid_commit(installed_baseline):
        raise SystemExit(f"[FAIL] invalid installed baseline commit marker: {installed_baseline!r}")
    if stage_i._systemctl_state("is-enabled") != "enabled" or stage_i._systemctl_state("is-active") != "active":
        raise SystemExit("[FAIL] qualified normal service must be enabled and active before test")

    original_bytes = stage_i.PERSISTENT_CONFIG.read_bytes()
    original_hash = hashlib.sha256(original_bytes).hexdigest()
    original_text = original_bytes.decode("utf-8")
    source = stage_i.validate_persistent_config(tomllib.loads(original_text))
    stage_i._check_firmware(args.firmware)
    stage_i._verify_eligibility(args.firmware)

    print("===== PRE-ARM QUALIFIED BASELINE =====")
    print(f"INSTALLED_BASELINE_COMMIT={installed_baseline}")
    print(f"PERSISTENT_CONFIG_SHA256={original_hash}")
    print("PERSISTENT_TX_ENABLED=NO")
    print("PERSISTENT_BEACON_ENABLED=NO")
    print(f"EXPECTED_EXTERNAL_DECODE={expected_external_decode(source)}")
    typed = input(f"Type exactly {ARM_PHRASE} to arm ONE product-converse RF frame: ").strip()
    if typed != ARM_PHRASE:
        raise SystemExit("[FAIL] interactive TX arm phrase did not match")

    daemon: subprocess.Popen[str] | None = None
    log_handle = None
    service_stopped = False
    tx_dispatched = False
    cleanup_error: BaseException | None = None
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
            raise RuntimeError(f"stale qualification runtime directory exists: {TEMP_ROOT}")
        TEMP_ROOT.mkdir(mode=0o700, parents=True)
        TEMP_CONFIG.write_text(make_temporary_tx_config(original_text), encoding="utf-8")
        os.chmod(TEMP_CONFIG, 0o600)
        packet_cfg = load_product_packet_engine_config(TEMP_CONFIG)
        classic_cfg = load_product_classic_tx_config(TEMP_CONFIG)
        if (
            not packet_cfg.tx_enabled
            or packet_cfg.tx_power != stage_i.TX_POWER
            or packet_cfg.frequency_hz != stage_i.EXPECTED_FREQUENCY_HZ
        ):
            raise RuntimeError("temporary product-converse TX profile failed validation")
        if not classic_cfg.configured or str(classic_cfg.source) != source:
            raise RuntimeError("temporary product classic identity failed validation")

        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join((str(ROOT / "src"), str(ROOT / "tools")))
        log_handle = TEMP_LOG.open("w", encoding="utf-8")
        daemon = subprocess.Popen(
            [sys.executable, "-m", "ywd1278.daemon", "--config", str(TEMP_CONFIG)],
            cwd=str(ROOT),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        stage_i._wait_port(TEMP_KISS_PORT, 6.0)
        stage_i._wait_port(TEMP_CONSOLE_PORT, 6.0)
        if daemon.poll() is not None:
            raise RuntimeError(f"temporary current-source daemon exited early rc={daemon.returncode}")

        with socket.create_connection(("127.0.0.1", TEMP_CONSOLE_PORT), timeout=3.0) as console:
            banner = _recv_until(console, b"cmd:").decode("utf-8", "replace")
            if "product command/converse mode" not in banner:
                raise RuntimeError(f"current product session banner missing: {banner!r}")
            baseline = command_with_prompt(console, "STATUS")
            stage_i.assert_single_shot_status(baseline, require_dispatched=False)
            reply = command_with_prompt(console, f"UNPROTO {DESTINATION}")
            if f"UNPROTO DEST={DESTINATION} VIA=DIRECT" not in reply:
                raise RuntimeError(f"UNPROTO setup failed: {reply!r}")

            enter_converse(console)
            print("PRODUCT_CONVERSE_ENTERED=PASS")
            print("COMMAND_PROMPT_SUPPRESSED=PASS")
            print("LIVE_RX_SUBSCRIBER_ATTACHED=PASS")

            send_one_converse_line(console)
            print("PRODUCT_CONVERSE_TX_LINE_SENT=ONE")
            print("KISS_TX_MESSAGES=0")

            print("===== INDEPENDENT OVER-AIR DECODE GATE =====")
            print(f"EXPECTED_EXTERNAL_DECODE={expected_external_decode(source)}")
            external = input(
                f"After an independent receiver decoded that exact frame ONCE, type {EXTERNAL_PHRASE}: "
            ).strip()
            if external != EXTERNAL_PHRASE:
                raise RuntimeError("independent exact decode not confirmed; harness never retries")
            print("INDEPENDENT_EXTERNAL_DECODE_CONFIRMED=YES")

            print("===== SAME-SESSION LIVE RX GATE =====")
            print("Generate or wait for one normal 145.050 packet now; it must appear as RX in this converse session.")
            live_line = wait_live_rx(console, timeout=float(args.live_rx_timeout))
            print("PRODUCT_CONVERSE_LIVE_RX=PASS")
            print(f"PRODUCT_CONVERSE_LIVE_RX_LINE={live_line}")

            exit_converse(console)
            print("PRINTABLE_CMD_ESCAPE=PASS")
            print("COMMAND_PROMPT_RESTORED=PASS")

            status = command_with_prompt(console, "STATUS")
            stage_i.assert_single_shot_status(status, require_dispatched=True)
            tx_dispatched = True
            print("TX_DISPATCHES=1")
            print("TX_QUEUE_ACCEPTED=1")
            print("TX_QUEUE_DISPATCHED=1")
            print("SUBSCRIBER_DROPS=0")

            time.sleep(NO_DUPLICATE_HOLD_SECONDS)
            final = command_with_prompt(console, "STATUS")
            stage_i.assert_single_shot_status(final, require_dispatched=True)
            print("NO_SECOND_INTERNAL_DISPATCH_AFTER_HOLD=PASS")
            print("AUTOMATIC_TX_RETRY=NO")

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
            cleanup_error = RuntimeError("temporary product-converse PTY leaked after teardown")
        if cleanup_error is not None:
            raise cleanup_error

    if not tx_dispatched:
        raise SystemExit("[FAIL] qualification ended without exactly one TX dispatch")
    if stage_i._systemctl_state("is-enabled") != "enabled" or stage_i._systemctl_state("is-active") != "active":
        raise SystemExit("[FAIL] normal no-TX service was not restored")
    restored = stage_i.PERSISTENT_CONFIG.read_bytes()
    if hashlib.sha256(restored).hexdigest() != original_hash:
        raise SystemExit("[FAIL] persistent config changed during product converse qualification")
    restored_source = stage_i.validate_persistent_config(tomllib.loads(restored.decode("utf-8")))
    if restored_source != source:
        raise SystemExit("[FAIL] persistent station identity changed")
    if stage_i.INSTALLED_COMMIT.read_text(encoding="utf-8").strip() != installed_baseline:
        raise SystemExit("[FAIL] installed source marker changed during qualification")

    print("===== PRODUCT CONVERSE PHYSICAL QUALIFICATION COMPLETE =====")
    print("YWD1278_0F_PRODUCT_CONVERSE_PHYSICAL=PASS")
    print("PRODUCT_CONVERSE_TX_LINES=1")
    print("INDEPENDENT_EXTERNAL_DECODE_COUNT=1")
    print("PRODUCT_CONVERSE_LIVE_RX=PASS")
    print("PRINTABLE_CMD_ESCAPE=PASS")
    print("COMMAND_PROMPT_RESTORED=PASS")
    print("AUTOMATIC_TX_RETRY=NO")
    print("PERSISTENT_TX_ENABLED=NO")
    print("PERSISTENT_CONFIG_MUTATED=NO")
    print("INSTALLED_SOURCE_MUTATED=NO")
    print("NORMAL_SERVICE_RESTORED=YES")
    print("FLASH_WRITTEN=NO")
    print("OPTION_BYTES_WRITTEN=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
