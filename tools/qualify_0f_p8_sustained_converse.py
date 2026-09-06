#!/usr/bin/env python3
"""Guarded physical qualification for 0F-P8 sustained product CONVERSE.

Dry-run is the default and performs no service, UART, device, or RF I/O.
Physical mode stages the current checkout against a temporary root-only config,
uses the permanent product Telnet console to set UNPROTO JIM VIA YWDNOD, queues
exactly three converse lines, requires independent over-air decode confirmation,
proves same-session live RX, returns with /CMD, then proves Ctrl-C cancels an
unfinished line without creating a fourth TX or poisoning the next cmd: input.
The normal persistent no-TX appliance is restored byte-identically afterward.
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

import qualify_0f_product_converse as p7  # noqa: E402
import qualify_stage_i_single_tx as stage_i  # noqa: E402
from ywd1278.service.appliance import load_product_packet_engine_config  # noqa: E402
from ywd1278.service.classic_tx_console import load_product_classic_tx_config  # noqa: E402


TEMP_ROOT = Path("/run/ywd-1278-0f-p8-converse")
TEMP_CONFIG = TEMP_ROOT / "config.toml"
TEMP_LOG = TEMP_ROOT / "daemon.log"
TEMP_KISS_PORT = 18301
TEMP_CONSOLE_PORT = 18310
TEMP_PTY = "/run/ywd-1278-0f-p8-converse/tnc"
AUTHORIZATION_TOKEN = "0F-P8-SUSTAINED-CONVERSE-TX-145050-THREE"
ARM_PHRASE = "TRANSMIT-0F-P8-CONVERSE-THREE"
EXTERNAL_PHRASE = "EXTERNAL-DECODE-P8-THREE"
DESTINATION = "JIM"
PATH = ("YWDNOD",)
INFORMATION = (
    "YWD-1278 P8 CONVERSE 1/3",
    "YWD-1278 P8 CONVERSE 2/3",
    "YWD-1278 P8 CONVERSE 3/3",
)
INTERLINE_SECONDS = 1.0
NO_DUPLICATE_HOLD_SECONDS = 2.0
LIVE_RX_TIMEOUT_SECONDS = 120.0
CTRL_C_PARTIAL = b"P8 CTRL-C PARTIAL MUST NOT TX"

# Runtime implementation frozen for the P8 physical attempt.  The historical
# P7 qualifier retains its own older blob pin and intentionally rejects P8.
FROZEN_P8_BLOBS = {
    "src/ywd1278/console/product_session.py": "21528919b0014c75ce98fff328b8c0830e6925b9",
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
    for relative, expected in FROZEN_P8_BLOBS.items():
        actual = _blob(ROOT / relative)
        if actual != expected:
            raise RuntimeError(
                f"P8 product capability blob mismatch: {relative} actual={actual} expected={expected}"
            )


def make_temporary_tx_config(original: str) -> str:
    text = stage_i.replace_toml_key(original, "radio", "tx_power", str(stage_i.TX_POWER))
    text = stage_i.replace_toml_key(text, "radio", "tx_enabled", "true")
    text = stage_i.replace_toml_key(text, "kiss", "port", str(TEMP_KISS_PORT))
    text = stage_i.replace_toml_key(text, "console", "port", str(TEMP_CONSOLE_PORT))
    text = stage_i.replace_toml_key(text, "console", "pty_link", f'"{TEMP_PTY}"')
    return text


def expected_external_decode(information: str, source: str = "KJ6YWD-10") -> str:
    return f"{source}>{DESTINATION},{PATH[0]}:{information}"


def print_plan(source: str = "KJ6YWD-10") -> None:
    print("===== YWD-1278 0F-P8 SUSTAINED PRODUCT CONVERSE QUALIFIER =====")
    print(f"SOURCE={source}")
    print(f"UNPROTO_DESTINATION={DESTINATION}")
    print(f"UNPROTO_PATH={PATH[0]}")
    for index, information in enumerate(INFORMATION, start=1):
        print(f"INFORMATION_{index}={information}")
        print(f"EXPECTED_EXTERNAL_DECODE_{index}={expected_external_decode(information, source)}")
    print("TX_FREQUENCY_HZ=145050000")
    print(f"TX_POWER={stage_i.TX_POWER}")
    print("TX_ORIGIN=PRODUCT_TELNET_CONVERSE")
    print("CLASSIC_CONVERSE_TX_LINES_MAX=3")
    print("LIVE_RX_REQUIRED_IN_SAME_SESSION=YES")
    print("PRINTABLE_ESCAPE=/CMD")
    print("CTRL_C_ESCAPE=REQUIRED_NO_TX")
    print("CTRL_C_PARTIAL_LINE_DISCARD=REQUIRED")
    print("AUTOMATIC_TX_RETRY=NO")
    print("PERSISTENT_TX_ENABLED=NO")
    print("PERSISTENT_CONFIG_MUTATED=NO")
    print("INSTALLED_SOURCE_MUTATED=NO")
    print("FLASH_WRITTEN=NO")
    print("OPTION_BYTES_WRITTEN=NO")


def send_converse_line(sock: socket.socket, information: str, *, index: int) -> str:
    sock.sendall(information.encode("ascii") + b"\r\n")
    data = p7._recv_until(sock, f"TX QUEUED REQUEST={index}".encode("ascii"), timeout=4.0)
    data += p7._recv_quiet(sock)
    text = data.decode("utf-8", "replace")
    if "cmd:" in text:
        raise RuntimeError("product prompt appeared during sustained converse")
    if f"DEST={DESTINATION}" not in text or f"VIA={PATH[0]}" not in text:
        raise RuntimeError(f"P8 converse TX admission reply was incomplete: {text!r}")
    return text


def assert_tx_status(text: str, expected: int) -> None:
    runtime = stage_i.parse_status_mapping(text, "RUNTIME")
    ingress = stage_i.parse_status_mapping(text, "INGRESS")
    queue = stage_i.parse_status_mapping(text, "QUEUE")
    backend = stage_i.parse_status_mapping(text, "BACKEND")

    dispatches = stage_i._status_int(runtime, "tx_dispatches")
    accepted = stage_i._status_int(queue, "tx_queue_accepted")
    dispatched = stage_i._status_int(queue, "tx_dispatched")
    depth = stage_i._status_int(queue, "tx_queue_depth")
    received = stage_i._status_int(ingress, "data_messages_received")
    admitted = stage_i._status_int(ingress, "data_admitted")
    actual = (dispatches, accepted, dispatched, depth, received, admitted)
    required = (expected, expected, expected, 0, expected, expected)
    if actual != required:
        raise RuntimeError(f"P8 TX accounting mismatch actual={actual} required={required}")

    for key in (
        "tx_invalid_rejections",
        "tx_queue_full_drops",
        "tx_access_timeouts",
        "tx_downstream_failures",
    ):
        if stage_i._status_int(queue, key) != 0:
            raise RuntimeError(f"unexpected queue failure counter {key}")
    for key in (
        "data_invalid_rejections",
        "data_queue_full_drops",
        "data_time_rejections",
        "data_other_rejections",
    ):
        if stage_i._status_int(ingress, key) != 0:
            raise RuntimeError(f"unexpected ingress failure counter {key}")
    if stage_i._status_int(backend, "subscriber_drops") != 0:
        raise RuntimeError("subscriber drops are non-zero")
    if runtime.get("failure", "") not in ("", "-"):
        raise RuntimeError(f"runtime failure is non-empty: {runtime.get('failure')}")


def _valid_commit(text: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{40}", text))


def main() -> int:
    ap = argparse.ArgumentParser(description="guarded 0F-P8 sustained product converse physical qualification")
    ap.add_argument("--transmit", action="store_true")
    ap.add_argument("--authorize", default="")
    ap.add_argument("--firmware", type=Path)
    ap.add_argument("--live-rx-timeout", type=float, default=LIVE_RX_TIMEOUT_SECONDS)
    args = ap.parse_args()

    print_plan()
    validate_product_blobs()
    if not args.transmit:
        print("YWD1278_0F_P8_SUSTAINED_CONVERSE_DRY_RUN=PASS")
        print("SERVICE_MUTATED=NO")
        print("MODEM_UART_OPENED=NO")
        print("CONVERSE_TX_LINES_SENT=0")
        print("RF_TRANSMITTED=NO")
        return 0

    if os.geteuid() != 0:
        raise SystemExit("[FAIL] physical 0F-P8 qualification requires root")
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
    for index, information in enumerate(INFORMATION, start=1):
        print(f"EXPECTED_EXTERNAL_DECODE_{index}={expected_external_decode(information, source)}")
    typed = input(f"Type exactly {ARM_PHRASE} to arm THREE product-converse RF frames: ").strip()
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
            raise RuntimeError(f"stale P8 qualification runtime directory exists: {TEMP_ROOT}")
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
            raise RuntimeError("temporary P8 TX profile failed validation")
        if not classic_cfg.configured or str(classic_cfg.source) != source:
            raise RuntimeError("temporary P8 classic identity failed validation")

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
            raise RuntimeError(f"temporary P8 daemon exited early rc={daemon.returncode}")

        with socket.create_connection(("127.0.0.1", TEMP_CONSOLE_PORT), timeout=3.0) as console:
            banner = p7._recv_until(console, b"cmd:").decode("utf-8", "replace")
            if "product command/converse mode" not in banner:
                raise RuntimeError(f"P8 product session banner missing: {banner!r}")
            baseline = p7.command_with_prompt(console, "STATUS")
            assert_tx_status(baseline, 0)
            reply = p7.command_with_prompt(console, f"UNPROTO {DESTINATION} VIA {PATH[0]}")
            if f"UNPROTO DEST={DESTINATION} VIA={PATH[0]}" not in reply:
                raise RuntimeError(f"P8 UNPROTO setup failed: {reply!r}")
            print(f"UNPROTO_CONFIGURED={DESTINATION} VIA {PATH[0]}")

            p7.enter_converse(console)
            print("PRODUCT_CONVERSE_ENTERED=PASS")
            print("COMMAND_PROMPT_SUPPRESSED=PASS")
            print("LIVE_RX_SUBSCRIBER_ATTACHED=PASS")

            for index, information in enumerate(INFORMATION, start=1):
                send_converse_line(console, information, index=index)
                print(f"PRODUCT_CONVERSE_TX_LINE_{index}=QUEUED")
                if index != len(INFORMATION):
                    time.sleep(INTERLINE_SECONDS)

            print("===== INDEPENDENT OVER-AIR DECODE GATE =====")
            for index, information in enumerate(INFORMATION, start=1):
                print(f"EXPECTED_EXTERNAL_DECODE_{index}={expected_external_decode(information, source)}")
            external = input(
                f"After an independent receiver decoded all THREE exact source frames at least once each, type {EXTERNAL_PHRASE}: "
            ).strip()
            if external != EXTERNAL_PHRASE:
                raise RuntimeError("independent P8 decode set not confirmed; harness never retries")
            print("INDEPENDENT_EXTERNAL_DECODE_CONFIRMED=YES")
            print("INDEPENDENT_EXTERNAL_DECODE_COUNT=3")

            print("===== SAME-SESSION LIVE RX GATE =====")
            print("Generate or wait for one normal 145.050 packet now; it must appear as RX in this converse session.")
            live_line = p7.wait_live_rx(console, timeout=float(args.live_rx_timeout))
            print("PRODUCT_CONVERSE_LIVE_RX=PASS")
            print(f"PRODUCT_CONVERSE_LIVE_RX_LINE={live_line}")

            p7.exit_converse(console)
            print("PRINTABLE_CMD_ESCAPE=PASS")
            print("COMMAND_PROMPT_RESTORED=PASS")

            status = p7.command_with_prompt(console, "STATUS")
            assert_tx_status(status, 3)
            tx_dispatched = True
            print("TX_DISPATCHES=3")
            print("TX_QUEUE_ACCEPTED=3")
            print("TX_QUEUE_DISPATCHED=3")
            print("SUBSCRIBER_DROPS=0")

            time.sleep(NO_DUPLICATE_HOLD_SECONDS)
            held = p7.command_with_prompt(console, "STATUS")
            assert_tx_status(held, 3)
            print("NO_SECOND_INTERNAL_DISPATCH_AFTER_HOLD=PASS")
            print("AUTOMATIC_TX_RETRY=NO")

            # A raw Ctrl-C must cancel only this unfinished text.  No newline is
            # sent, therefore this phase is explicitly zero additional TX.
            reply = p7.command_with_prompt(console, f"UNPROTO {DESTINATION} VIA {PATH[0]}")
            if f"UNPROTO DEST={DESTINATION} VIA={PATH[0]}" not in reply:
                raise RuntimeError("P8 UNPROTO state unavailable before Ctrl-C check")
            p7.enter_converse(console)
            console.sendall(CTRL_C_PARTIAL)
            time.sleep(0.15)
            console.sendall(b"\x03")
            ctrl_c = p7._recv_until(console, b"cmd:", timeout=4.0).decode("utf-8", "replace")
            if "COMMAND MODE" not in ctrl_c:
                raise RuntimeError(f"Ctrl-C did not restore command mode: {ctrl_c!r}")
            print("CTRL_C_ESCAPE=PASS")

            clean = p7.command_with_prompt(console, f"UNPROTO {DESTINATION} VIA {PATH[0]}")
            if f"UNPROTO DEST={DESTINATION} VIA={PATH[0]}" not in clean:
                raise RuntimeError(f"partial converse text contaminated command mode: {clean!r}")
            if CTRL_C_PARTIAL.decode("ascii") in clean:
                raise RuntimeError("Ctrl-C partial text leaked into command response")
            print("CTRL_C_PARTIAL_LINE_DISCARD=PASS")
            final = p7.command_with_prompt(console, "STATUS")
            assert_tx_status(final, 3)
            print("CTRL_C_ADDITIONAL_TX=0")

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
            cleanup_error = RuntimeError("temporary P8 product-converse PTY leaked after teardown")
        if cleanup_error is not None:
            raise cleanup_error

    if not tx_dispatched:
        raise SystemExit("[FAIL] P8 qualification ended without exactly three TX dispatches")
    if stage_i._systemctl_state("is-enabled") != "enabled" or stage_i._systemctl_state("is-active") != "active":
        raise SystemExit("[FAIL] normal no-TX service was not restored")
    restored = stage_i.PERSISTENT_CONFIG.read_bytes()
    if hashlib.sha256(restored).hexdigest() != original_hash:
        raise SystemExit("[FAIL] persistent config changed during P8 qualification")
    restored_source = stage_i.validate_persistent_config(tomllib.loads(restored.decode("utf-8")))
    if restored_source != source:
        raise SystemExit("[FAIL] persistent station identity changed")
    if stage_i.INSTALLED_COMMIT.read_text(encoding="utf-8").strip() != installed_baseline:
        raise SystemExit("[FAIL] installed source marker changed during P8 qualification")

    print("===== 0F-P8 SUSTAINED PRODUCT CONVERSE PHYSICAL QUALIFICATION COMPLETE =====")
    print("YWD1278_0F_P8_SUSTAINED_PRODUCT_CONVERSE_PHYSICAL=PASS")
    print("UNPROTO_DESTINATION=JIM")
    print("UNPROTO_PATH=YWDNOD")
    print("PRODUCT_CONVERSE_TX_LINES=3")
    print("INDEPENDENT_EXTERNAL_DECODE_COUNT=3")
    print("PRODUCT_CONVERSE_LIVE_RX=PASS")
    print("PRINTABLE_CMD_ESCAPE=PASS")
    print("CTRL_C_ESCAPE=PASS")
    print("CTRL_C_PARTIAL_LINE_DISCARD=PASS")
    print("CTRL_C_ADDITIONAL_TX=0")
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
