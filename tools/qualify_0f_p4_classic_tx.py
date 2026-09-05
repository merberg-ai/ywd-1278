#!/usr/bin/env python3
"""0F-P4: one guarded physical TX through the actual classic console.

Dry-run is the default and performs zero device/service I/O. Physical mode reuses
Stage-I's already-qualified appliance/firmware/service guards, but replaces the
KISS DATA injection with one persistent classic Telnet session:

    UNPROTO YWD127
    CONVERSE
    YWD-1278 0F-P4 CLASSIC TX 1/1
    COMMAND

Exactly one converse text line may enter the existing product DATA admission
boundary. The harness itself never sends KISS DATA. After one dispatch it holds
for duplicates, requires an independent exact over-air decode, observes a later
RX packet, tears down the temporary TX-capable runtime, and restores the exact
unchanged persistent no-TX service.
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

HOST_QUALIFIED_CHECKPOINT = "3b9bc5c7e212872606ba36d7fa30338b00cd9ce3"
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
NO_DUPLICATE_HOLD_SECONDS = 2.0
POST_TX_RX_TIMEOUT_SECONDS = 120.0

FROZEN_BLOBS = {
    "src/ywd1278/console/classic.py": "4d6dfd5d439fb5dfd6ff586c2a47c37724381b2e",
    "src/ywd1278/console/classic_tx.py": "e920bf5d26a0b7b2005a374384b3dda68996fc4c",
    "src/ywd1278/service/classic_tx_console.py": "579cab015b20556dd9354e91edfd307e3120db8c",
    "src/ywd1278/service/appliance.py": "fa1b086d6d8fa40b537c002dbeec34fdc6532396",
    "src/ywd1278/ax25/codec.py": "866a500d9f3a5d3fc80f6918d07ff83a6672ad64",
    "src/ywd1278/kiss/tx_path.py": "44f4b6c0bddd6ac0977646ac417e448c9a1398ea",
}


def _blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def validate_frozen_capability_blobs() -> None:
    """Root-side check that every RF-capable 0F owner is still the frozen host build.

    Exact staging-commit verification is intentionally performed outside sudo by
    the operator preflight.  This avoids root Git safe-directory ambiguity while
    retaining byte-exact capability checks inside the physical harness.
    """
    for relative, expected in FROZEN_BLOBS.items():
        actual = _blob(ROOT / relative)
        if actual != expected:
            raise RuntimeError(f"frozen capability blob mismatch: {relative} actual={actual}")


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
    raise RuntimeError(f"console closed/timed out waiting for {needle!r}: {bytes(data)!r}")


def console_command(sock: socket.socket, command: str) -> str:
    sock.sendall(command.encode("ascii") + b"\r\n")
    return _recv_until(sock, b"cmd:").decode("utf-8", "replace")


def wait_for_one_dispatch(console: socket.socket) -> str:
    deadline = time.monotonic() + stage_i.DISPATCH_TIMEOUT_SECONDS
    last = ""
    while time.monotonic() < deadline:
        last = console_command(console, "STATUS")
        runtime = stage_i.parse_status_mapping(last, "RUNTIME")
        count = stage_i._status_int(runtime, "tx_dispatches")
        if count > 1:
            raise RuntimeError("more than one 0F-P4 TX dispatch occurred")
        if count == 1:
            stage_i.assert_single_shot_status(last, require_dispatched=True)
            return last
        time.sleep(0.1)
    raise RuntimeError(f"timed out waiting for the one 0F-P4 dispatch: {last!r}")


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
    print("CLASSIC_CONVERSE_TX_LINES_MAX=1")
    print("KISS_TX_MESSAGES=0")
    print("INTERNAL_TX_DISPATCHES_MAX=1")
    print("AUTOMATIC_TX_RETRY=NO")
    print("PERSISTENT_CONFIG_MUTATED=NO")
    print("BEACON_TX=NO")
    print("CONNECTED_MODE_TX=NO")
    print("FLASH_WRITTEN=NO")
    print("OPTION_BYTES_WRITTEN=NO")


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

    validate_frozen_capability_blobs()
    for path in (stage_i.PERSISTENT_CONFIG, stage_i.INSTALLED_COMMIT, stage_i.VENV_PYTHON, stage_i.ELIGIBILITY):
        if not path.exists():
            raise SystemExit(f"[FAIL] required qualified-appliance path missing: {path}")
    installed = stage_i.INSTALLED_COMMIT.read_text(encoding="utf-8").strip()
    if installed != stage_i.EXPECTED_INSTALLED_COMMIT:
        raise SystemExit(f"[FAIL] installed product commit mismatch: {installed}")
    if stage_i._systemctl_state("is-enabled") != "enabled" or stage_i._systemctl_state("is-active") != "active":
        raise SystemExit("[FAIL] qualified normal service must be enabled and active before 0F-P4")

    original_bytes = stage_i.PERSISTENT_CONFIG.read_bytes()
    original_hash = hashlib.sha256(original_bytes).hexdigest()
    original_text = original_bytes.decode("utf-8")
    source = stage_i.validate_persistent_config(tomllib.loads(original_text))
    stage_i._check_firmware(args.firmware)
    stage_i._verify_eligibility(args.firmware)

    print("===== 0F-P4 PRE-ARM QUALIFIED STATE =====")
    print(f"FROZEN_0F_CAPABILITY_BASE={HOST_QUALIFIED_CHECKPOINT}")
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
            raise RuntimeError(f"stale 0F-P4 runtime directory exists: {TEMP_ROOT}")
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
            raise RuntimeError("temporary 0F-P4 TX profile failed product validation")
        if not classic_cfg.configured or str(classic_cfg.source) != source:
            raise RuntimeError("temporary 0F-P4 classic station identity failed validation")

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
        stage_i._wait_port(TEMP_KISS_PORT, 6.0)
        stage_i._wait_port(TEMP_CONSOLE_PORT, 6.0)
        if daemon.poll() is not None:
            raise RuntimeError(f"temporary 0F daemon exited early rc={daemon.returncode}")

        with socket.create_connection(("127.0.0.1", TEMP_KISS_PORT), timeout=3.0) as kiss, socket.create_connection(("127.0.0.1", TEMP_CONSOLE_PORT), timeout=3.0) as console:
            banner = _recv_until(console, b"cmd:").decode("utf-8", "replace")
            if "TELNET TNC CONSOLE" not in banner:
                raise RuntimeError("did not reach actual product classic Telnet console")
            baseline = console_command(console, "STATUS")
            stage_i.assert_single_shot_status(baseline, require_dispatched=False)
            print("0F_P4_TEMP_PRODUCT_DAEMON=RUNNING")
            print("PRODUCT_TX=ENABLED_TEMPORARILY")
            print("KISS_TX_MESSAGES=0")

            reply = console_command(console, f"UNPROTO {DESTINATION}")
            if f"UNPROTO DEST={DESTINATION} VIA=DIRECT" not in reply:
                raise RuntimeError(f"UNPROTO direct setup failed: {reply!r}")
            reply = console_command(console, "CONVERSE")
            if f"CONVERSE MODE DEST={DESTINATION} VIA=DIRECT" not in reply:
                raise RuntimeError(f"CONVERSE entry failed: {reply!r}")
            print("CLASSIC_UNPROTO_DIRECT=PASS")
            print("CLASSIC_CONVERSE_ENTERED=PASS")

            # Exactly one frame-producing console line. There is deliberately
            # no retry and no KISS DATA transmission anywhere in this harness.
            reply = console_command(console, INFORMATION)
            if "TX QUEUED REQUEST=" not in reply or f"DEST={DESTINATION}" not in reply or "VIA=DIRECT" not in reply:
                raise RuntimeError(f"classic converse line was not admitted: {reply!r}")
            print("CLASSIC_CONVERSE_TX_LINE_SENT=ONE")

            reply = console_command(console, "COMMAND")
            if "COMMAND MODE" not in reply:
                raise RuntimeError("classic session did not return to COMMAND mode")
            print("CLASSIC_COMMAND_MODE_RESTORED=PASS")

            status = wait_for_one_dispatch(console)
            tx_dispatched = True
            print("0F_P4_AUTHORIZATION_CONSUMED=YES")
            print("TX_DISPATCHES=1")
            print("TX_QUEUE_ACCEPTED=1")
            print("TX_QUEUE_DISPATCHED=1")
            print("BACKEND_DATA_ADMITTED=1")
            print("KISS_TX_MESSAGES=0")
            print("AUTOMATIC_TX_RETRY=NO")

            time.sleep(NO_DUPLICATE_HOLD_SECONDS)
            stage_i.assert_single_shot_status(console_command(console, "STATUS"), require_dispatched=True)
            print("NO_SECOND_INTERNAL_DISPATCH_AFTER_HOLD=PASS")

            print("===== INDEPENDENT OVER-AIR DECODE GATE =====")
            print(f"EXPECTED_EXTERNAL_DECODE={expected_external_decode(source)}")
            external = input(
                f"After an independent receiver decoded that exact frame ONCE, type {EXTERNAL_PHRASE}: "
            ).strip()
            if external != EXTERNAL_PHRASE:
                raise RuntimeError("independent exact decode not confirmed; 0F-P4 never retries")
            print("INDEPENDENT_EXTERNAL_DECODE_CONFIRMED=YES")
            print("INDEPENDENT_EXTERNAL_DECODE_COUNT=1")

            print("===== POST-TX RX-RESUME GATE =====")
            print("WAITING_FOR_LATER_NON_QUALIFICATION_PACKET_145050=YES")
            print("Generate or wait for one normal 145.050 packet that is not the 0F-P4 TX frame.")
            rx_body, rx_source = recv_post_tx_packet(kiss, tx_source=source, timeout=float(args.post_rx_timeout))
            print("POST_TX_RX_RESUMED=PASS")
            print(f"POST_TX_RX_FRAME_BYTES={len(rx_body)}")
            print(f"POST_TX_RX_SOURCE={rx_source}")

            final = console_command(console, "STATUS")
            stage_i.assert_single_shot_status(final, require_dispatched=True)
            runtime = stage_i.parse_status_mapping(final, "RUNTIME")
            if stage_i._status_int(runtime, "decoded_rx_frames") < 1:
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
                stage_i._restore_service(original_hash)
            except BaseException as exc:
                cleanup_error = exc
        if pty_leaked and cleanup_error is None:
            cleanup_error = RuntimeError("temporary 0F-P4 PTY leaked after daemon teardown")
        if cleanup_error is not None:
            raise cleanup_error

    if not tx_dispatched:
        raise SystemExit("[FAIL] 0F-P4 ended without the one TX dispatch")
    if stage_i._systemctl_state("is-enabled") != "enabled" or stage_i._systemctl_state("is-active") != "active":
        raise SystemExit("[FAIL] normal no-TX service was not restored")
    restored = stage_i.PERSISTENT_CONFIG.read_bytes()
    if hashlib.sha256(restored).hexdigest() != original_hash:
        raise SystemExit("[FAIL] persistent config hash changed during 0F-P4")
    stage_i.validate_persistent_config(tomllib.loads(restored.decode("utf-8")))

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
