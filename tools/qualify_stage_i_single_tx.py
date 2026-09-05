#!/usr/bin/env python3
"""Stage-I guarded one-shot product TX acceptance.

Default invocation is a zero-I/O dry run.  Physical mode is intentionally
operator-gated and narrow: verify the already-qualified no-TX appliance, stop
the normal service, launch the *installed* product daemon against a root-only
temporary /run config with only the qualified TX profile enabled, inject exactly
one localhost KISS DATA frame, prove exactly one product runtime dispatch, require
operator confirmation of one matching external decode, prove a later received
packet after RX restart, then tear the TX-capable daemon down and restore the
original persistent no-TX service.

The persistent /etc/ywd-1278/config.toml is never modified.  This harness has no
firmware flash, GPIO/reset, option-byte, beacon, connected-mode, or retry path.
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
import tempfile
import time
import tomllib

from ywd1278.ax25 import Address, build_ui_frame, parse_frame
from ywd1278.kiss.framing import DATA, KISSStreamDecoder, encode
from ywd1278.service.appliance import load_product_packet_engine_config

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
VENV_DAEMON = Path("/opt/ywd-1278/venv/bin/ywd1278d")
SOURCE_ROOT = Path("/opt/ywd-1278/source")
ELIGIBILITY = Path("/var/lib/ywd-1278/firmware-ready.json")
DEVICE = "/dev/ttyAMA0"
TEMP_ROOT = Path("/run/ywd-1278-stage-i")
TEMP_CONFIG = TEMP_ROOT / "config.toml"
TEMP_LOG = TEMP_ROOT / "daemon.log"
TEMP_KISS_PORT = 18001
TEMP_CONSOLE_PORT = 18010
TEMP_PTY = "/run/ywd-1278/stage-i-tnc"
AUTHORIZATION_TOKEN = "STAGE-I-TX-145050-ONE"
ARM_PHRASE = "TRANSMIT-STAGE-I-ONE"
EXTERNAL_PHRASE = "EXTERNAL-DECODE-MATCH-ONE"
DESTINATION = "YWD127"
INFORMATION = "YWD-1278 STAGE-I TX 1/1"
DISPATCH_TIMEOUT_SECONDS = 45.0
NO_DUPLICATE_HOLD_SECONDS = 2.0
POST_TX_RX_TIMEOUT_SECONDS = 120.0


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
    return callsign.strip().upper() if ssid == 0 else f"{callsign.strip().upper()}-{ssid}"


def build_vector(source: str = "KJ6YWD-10") -> bytes:
    body = build_ui_frame(
        source=Address.parse(source),
        destination=Address.parse(DESTINATION),
        path=[],
        info=INFORMATION.encode("ascii"),
        include_fcs=False,
    )
    if not body or len(body) > 330:
        raise ValueError("unexpected Stage-I AX.25 body size")
    return body


def expected_external_decode(source: str = "KJ6YWD-10") -> str:
    return f"{source}>{DESTINATION}:{INFORMATION}"


def replace_toml_key(text: str, section: str, key: str, rendered_value: str) -> str:
    lines = text.splitlines(keepends=True)
    current = ""
    changed = 0
    out: list[str] = []
    section_re = re.compile(r"^\s*\[([^]]+)\]\s*(?:#.*)?(?:\r?\n)?$")
    key_re = re.compile(rf"^(\s*){re.escape(key)}\s*=.*?(\r?\n)?$")
    for line in lines:
        match = section_re.match(line)
        if match:
            current = match.group(1).strip()
            out.append(line)
            continue
        match = key_re.match(line)
        if current == section and match:
            newline = match.group(2) or "\n"
            out.append(f"{match.group(1)}{key} = {rendered_value}{newline}")
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


def parse_status_mapping(text: str, label: str) -> dict[str, str]:
    prefix = label.upper() + " "
    for raw in text.replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line.startswith(prefix):
            continue
        result: dict[str, str] = {}
        for token in line[len(prefix):].split():
            if "=" in token:
                key, value = token.split("=", 1)
                result[key] = value
        return result
    raise ValueError(f"STATUS did not contain {label}")


def _bool(root: dict, table: str, key: str) -> bool:
    value = root.get(table, {}).get(key) if isinstance(root.get(table), dict) else None
    if not isinstance(value, bool):
        raise ValueError(f"invalid [{table}] {key}")
    return value


def validate_persistent_config(root: dict) -> str:
    hardware = root.get("hardware")
    radio = root.get("radio")
    firmware = root.get("firmware")
    beacon = root.get("beacon")
    if not all(isinstance(item, dict) for item in (hardware, radio, firmware, beacon)):
        raise ValueError("required product config tables are missing")
    if hardware.get("target") != EXPECTED_TARGET:
        raise ValueError("unexpected hardware target")
    if radio.get("device") != DEVICE:
        raise ValueError("unexpected modem UART")
    if float(radio.get("frequency_mhz", 0.0)) != 145.05:
        raise ValueError("frequency is not 145.050 MHz")
    if _bool(root, "radio", "tx_enabled"):
        raise ValueError("persistent TX must be disabled before Stage I")
    if _bool(root, "firmware", "allow_automatic_flash"):
        raise ValueError("automatic flash must remain disabled")
    if _bool(root, "beacon", "enabled"):
        raise ValueError("beacon must remain disabled")
    source = _station_source(root)
    if source != "KJ6YWD-10":
        raise ValueError(f"Stage-I fixed-vector source requires KJ6YWD-10, got {source}")
    return source


def _run(args: list[str], *, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        check=check,
    )


def _systemctl_state(kind: str) -> str:
    return _run(["systemctl", kind, SERVICE], check=False).stdout.strip()


def _wait_port(port: int, timeout: float = 5.0) -> None:
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


def _recv_until(sock: socket.socket, needle: bytes, timeout: float = 3.0) -> bytes:
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
    return bytes(data)


def telnet_command(command: str) -> str:
    with socket.create_connection(("127.0.0.1", TEMP_CONSOLE_PORT), timeout=2.0) as sock:
        _recv_until(sock, b"cmd:", 2.0)
        sock.sendall(command.encode("ascii") + b"\r\n")
        return _recv_until(sock, b"cmd:", 3.0).decode("utf-8", "replace")


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

    if require_dispatched:
        if (dispatches, accepted, dispatched, depth, received, admitted) != (1, 1, 1, 0, 1, 1):
            raise RuntimeError(
                "single-shot accounting mismatch: "
                f"dispatches={dispatches} accepted={accepted} dispatched={dispatched} "
                f"depth={depth} received={received} admitted={admitted}"
            )
    else:
        if (dispatches, accepted, dispatched, received, admitted) != (0, 0, 0, 0, 0):
            raise RuntimeError("Stage-I temporary runtime was not clean before injection")

    for key in (
        "tx_invalid_rejections",
        "tx_queue_full_drops",
        "tx_access_timeouts",
        "tx_downstream_failures",
    ):
        if _status_int(queue, key) != 0:
            raise RuntimeError(f"unexpected queue failure counter {key}")
    for key in (
        "data_invalid_rejections",
        "data_queue_full_drops",
        "data_time_rejections",
        "data_other_rejections",
    ):
        if _status_int(ingress, key) != 0:
            raise RuntimeError(f"unexpected ingress failure counter {key}")
    if _status_int(backend, "subscriber_drops") != 0:
        raise RuntimeError("subscriber drops are non-zero")
    if runtime.get("failure", "") not in ("", "-"):
        raise RuntimeError(f"runtime failure is non-empty: {runtime.get('failure')}")


def wait_for_one_dispatch(timeout: float = DISPATCH_TIMEOUT_SECONDS) -> str:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        last = telnet_command("STATUS")
        runtime = parse_status_mapping(last, "RUNTIME")
        tx = _status_int(runtime, "tx_dispatches")
        if tx > 1:
            raise RuntimeError("more than one TX dispatch occurred")
        if tx == 1:
            assert_single_shot_status(last, require_dispatched=True)
            return last
        time.sleep(0.1)
    raise RuntimeError(f"timed out waiting for one product TX dispatch; last STATUS={last!r}")


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
            raise RuntimeError("KISS connection closed while waiting for post-TX RX")
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


def _verify_hardware_identity() -> None:
    proc = _run(
        [
            "bash",
            str(SOURCE_ROOT / "installer/hardware-detect.sh"),
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
        raise RuntimeError("exact Stage-H HAT target/identity recheck failed")


def _verify_eligibility(firmware: Path) -> None:
    proc = _run(
        [
            str(VENV_PYTHON),
            "-m",
            "ywd1278.install.firmware_trust",
            "--profile",
            str(SOURCE_ROOT / "firmware/product-ax25r4.json"),
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
        raise RuntimeError("Stage-F service eligibility did not revalidate")


def _check_firmware(firmware: Path) -> None:
    if not firmware.is_file():
        raise RuntimeError(f"firmware artifact missing: {firmware}")
    data = firmware.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if len(data) != EXPECTED_FIRMWARE_SIZE or digest != EXPECTED_FIRMWARE_SHA256:
        raise RuntimeError("firmware artifact size/hash mismatch")


def _restore_service(original_hash: str) -> None:
    if TEMP_PTY and Path(TEMP_PTY).exists():
        # The temporary daemon should remove this itself; do not unlink a live PTY.
        pass
    if hashlib.sha256(PERSISTENT_CONFIG.read_bytes()).hexdigest() != original_hash:
        raise RuntimeError("persistent config changed during Stage I")
    _run(["systemctl", "start", SERVICE], capture=True)
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        if _systemctl_state("is-active") == "active":
            try:
                _wait_port(8001, 0.5)
                _wait_port(8010, 0.5)
                return
            except RuntimeError:
                pass
        time.sleep(0.1)
    raise RuntimeError("normal no-TX service did not recover after Stage I")


def print_plan(source: str = "KJ6YWD-10") -> None:
    body = build_vector(source)
    print("===== YWD-1278 STAGE I SINGLE-SHOT PRODUCT TX =====")
    print(f"SOURCE={source}")
    print(f"DESTINATION={DESTINATION}")
    print("PATH=DIRECT")
    print(f"INFORMATION={INFORMATION}")
    print(f"KISS_BODY_BYTES={len(body)}")
    print(f"KISS_BODY_SHA256={hashlib.sha256(body).hexdigest()}")
    print(f"EXPECTED_EXTERNAL_DECODE={expected_external_decode(source)}")
    print("TX_FREQUENCY_HZ=145050000")
    print("TX_POWER=200")
    print("KISS_DATA_MESSAGES=1")
    print("AUTOMATIC_TX_RETRY=NO")
    print("PERSISTENT_CONFIG_MUTATED=NO")
    print("BEACON_ENABLED=NO")
    print("FLASH_PERMITTED=NO")
    print("OPTION_BYTES_PERMITTED=NO")


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage-I guarded single-shot product TX acceptance")
    ap.add_argument("--transmit", action="store_true")
    ap.add_argument("--authorize", default="")
    ap.add_argument("--firmware", type=Path)
    ap.add_argument("--post-rx-timeout", type=float, default=POST_TX_RX_TIMEOUT_SECONDS)
    args = ap.parse_args()

    print_plan()
    if not args.transmit:
        print("YWD1278_STAGE_I_DRY_RUN=PASS")
        print("SERVICE_MUTATED=NO")
        print("MODEM_UART_OPENED=NO")
        print("KISS_DATA_SENT=NO")
        print("RF_TRANSMITTED=NO")
        return 0

    if os.geteuid() != 0:
        raise SystemExit("[FAIL] physical Stage I requires root")
    if args.authorize != AUTHORIZATION_TOKEN:
        raise SystemExit(f"[FAIL] exact authorization required: --authorize {AUTHORIZATION_TOKEN}")
    if args.firmware is None:
        raise SystemExit("[FAIL] --firmware is required in physical mode")
    if args.post_rx_timeout <= 0:
        raise SystemExit("[FAIL] --post-rx-timeout must be positive")

    for path in (PERSISTENT_CONFIG, INSTALLED_COMMIT, VENV_PYTHON, VENV_DAEMON, ELIGIBILITY):
        if not path.exists():
            raise SystemExit(f"[FAIL] required installed-appliance path missing: {path}")
    installed = INSTALLED_COMMIT.read_text(encoding="utf-8").strip()
    if installed != EXPECTED_INSTALLED_COMMIT:
        raise SystemExit(f"[FAIL] installed product commit mismatch: {installed}")
    if _systemctl_state("is-enabled") != "enabled" or _systemctl_state("is-active") != "active":
        raise SystemExit("[FAIL] qualified normal service must be enabled and active before Stage I")

    original_bytes = PERSISTENT_CONFIG.read_bytes()
    original_hash = hashlib.sha256(original_bytes).hexdigest()
    original_text = original_bytes.decode("utf-8")
    root = tomllib.loads(original_text)
    source = validate_persistent_config(root)
    body = build_vector(source)
    _check_firmware(args.firmware)
    _verify_eligibility(args.firmware)

    print("===== STAGE I OPERATOR ARM =====")
    print(f"EXPECTED_EXTERNAL_DECODE={expected_external_decode(source)}")
    typed = input(f"Type exactly {ARM_PHRASE} to authorize ONE RF frame: ").strip()
    if typed != ARM_PHRASE:
        raise SystemExit("[FAIL] Stage-I interactive TX arm phrase did not match")

    daemon: subprocess.Popen[str] | None = None
    log_handle = None
    service_stopped = False
    tx_dispatched = False
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

        TEMP_ROOT.mkdir(mode=0o700, parents=True, exist_ok=False)
        temp_text = make_temporary_tx_config(original_text)
        TEMP_CONFIG.write_text(temp_text, encoding="utf-8")
        os.chmod(TEMP_CONFIG, 0o600)
        temp_cfg = load_product_packet_engine_config(TEMP_CONFIG)
        if not temp_cfg.tx_enabled or temp_cfg.tx_power != TX_POWER or temp_cfg.frequency_hz != EXPECTED_FREQUENCY_HZ:
            raise RuntimeError("temporary Stage-I TX profile failed product config validation")

        log_handle = TEMP_LOG.open("w", encoding="utf-8")
        daemon = subprocess.Popen(
            [str(VENV_DAEMON), "--config", str(TEMP_CONFIG)],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        _wait_port(TEMP_KISS_PORT, 6.0)
        _wait_port(TEMP_CONSOLE_PORT, 6.0)
        if daemon.poll() is not None:
            raise RuntimeError(f"temporary product daemon exited early rc={daemon.returncode}")
        baseline = telnet_command("STATUS")
        assert_single_shot_status(baseline, require_dispatched=False)
        print("STAGE_I_TEMP_PRODUCT_DAEMON=RUNNING")
        print("PRODUCT_TX=ENABLED_TEMPORARILY")
        print("PERSISTENT_CONFIG_MUTATED=NO")

        with socket.create_connection(("127.0.0.1", TEMP_KISS_PORT), timeout=3.0) as kiss:
            # Exactly one application-originated KISS DATA message.  There is no
            # retry loop around this send, and the body intentionally excludes FCS.
            kiss.sendall(encode(body, command=DATA))
            print("STAGE_I_KISS_DATA_INJECTED=ONE")
            status = wait_for_one_dispatch()
            tx_dispatched = True
            runtime = parse_status_mapping(status, "RUNTIME")
            queue = parse_status_mapping(status, "QUEUE")
            print(f"TX_DISPATCHES={runtime['tx_dispatches']}")
            print(f"TX_QUEUE_ACCEPTED={queue['tx_queue_accepted']}")
            print(f"TX_QUEUE_DISPATCHED={queue['tx_dispatched']}")
            print("AUTOMATIC_TX_RETRY=NO")

            time.sleep(NO_DUPLICATE_HOLD_SECONDS)
            stable = telnet_command("STATUS")
            assert_single_shot_status(stable, require_dispatched=True)
            print("NO_SECOND_INTERNAL_DISPATCH_AFTER_HOLD=PASS")

            print("===== INDEPENDENT OVER-AIR DECODE GATE =====")
            print(f"EXPECTED_EXTERNAL_DECODE={expected_external_decode(source)}")
            external = input(
                f"After an independent receiver decoded that exact frame ONCE, type {EXTERNAL_PHRASE}: "
            ).strip()
            if external != EXTERNAL_PHRASE:
                raise RuntimeError("independent external decode was not confirmed")
            print("INDEPENDENT_EXTERNAL_DECODE_CONFIRMED=YES")
            print("INDEPENDENT_EXTERNAL_DECODE_COUNT=1")

            print("===== POST-TX RX-RESUME GATE =====")
            print("WAITING_FOR_LATER_NON_QUALIFICATION_PACKET_145050=YES")
            print("Generate or wait for one packet whose source/payload is not the Stage-I TX frame.")
            rx_body, rx_source = recv_post_tx_non_qualification(
                kiss, tx_source=source, timeout=float(args.post_rx_timeout)
            )
            print("POST_TX_RX_RESUMED=PASS")
            print(f"POST_TX_RX_FRAME_BYTES={len(rx_body)}")
            print(f"POST_TX_RX_SOURCE={rx_source}")

            final = telnet_command("STATUS")
            assert_single_shot_status(final, require_dispatched=True)
            runtime_final = parse_status_mapping(final, "RUNTIME")
            if _status_int(runtime_final, "decoded_rx_frames") < 1:
                raise RuntimeError("runtime did not account a decoded RX frame after Stage-I TX")
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
        if TEMP_ROOT.exists():
            shutil.rmtree(TEMP_ROOT)
        if Path(TEMP_PTY).exists():
            raise RuntimeError("temporary Stage-I PTY leaked after daemon teardown")
        if service_stopped:
            _restore_service(original_hash)

    if not tx_dispatched:
        raise SystemExit("[FAIL] Stage-I physical path ended without a TX dispatch")
    if _systemctl_state("is-enabled") != "enabled" or _systemctl_state("is-active") != "active":
        raise SystemExit("[FAIL] normal no-TX service was not restored")
    restored = tomllib.loads(PERSISTENT_CONFIG.read_text(encoding="utf-8"))
    validate_persistent_config(restored)
    print("===== STAGE I SINGLE-SHOT PRODUCT TX COMPLETE =====")
    print("YWD1278_STAGE_I_SINGLE_TX=PASS")
    print("PRODUCT_KISS_TO_CSMA_TO_RF=PASS")
    print("INTERNAL_TX_DISPATCH_COUNT=1")
    print("INDEPENDENT_EXTERNAL_DECODE_COUNT=1")
    print("AUTOMATIC_TX_RETRY=NO")
    print("POST_TX_RX_RESUMED=PASS")
    print("PERSISTENT_TX_ENABLED=NO")
    print("PERSISTENT_CONFIG_MUTATED=NO")
    print("NORMAL_SERVICE_RESTORED=YES")
    print("FLASH_WRITTEN=NO")
    print("OPTION_BYTES_WRITTEN=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
