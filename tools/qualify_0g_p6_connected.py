#!/usr/bin/env python3
"""Guarded 0G-P6 physical connected-mode round-trip acceptance."""

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
from ywd1278.ax25 import Address  # noqa: E402
from ywd1278.kiss.framing import DATA, KISSStreamDecoder, encode  # noqa: E402
from ywd1278.link.modulo8 import LinkState  # noqa: E402
from ywd1278.link.session_manager import ConnectedSessionManager  # noqa: E402
from ywd1278.link.timed_link import LinkTimerConfig  # noqa: E402
from ywd1278.service.appliance import load_product_packet_engine_config  # noqa: E402


EXPECTED_HOST_COMMIT = "0ee7fe6c1f0159ee2534ba8c7ad0e72da28d5247"
AUTHORIZATION_TOKEN = "0G-P6-CONNECTED-145050-KJ6YWD5-ONE"
ARM_PHRASE = "TRANSMIT-0G-P6-CONNECTED-KJ6YWD-5-ONE"
TEMP_ROOT = Path("/run/ywd-1278-0g-p6")
TEMP_CONFIG = TEMP_ROOT / "config.toml"
TEMP_LOG = TEMP_ROOT / "daemon.log"
TEMP_KISS_PORT = 18301
TEMP_CONSOLE_PORT = 18310
TEMP_PTY = "/run/ywd-1278-0g-p6/tnc"
LOCAL = Address.parse("KJ6YWD-10")
REMOTE = Address.parse("KJ6YWD-5")
TEST_INFORMATION = "YWD-1278 0G-P6 CONNECTED TEST 1/1"
SESSION_ID = "physical-p6"


def make_temporary_tx_config(original: str) -> str:
    text = stage_i.replace_toml_key(original, "radio", "tx_power", str(stage_i.TX_POWER))
    text = stage_i.replace_toml_key(text, "radio", "tx_enabled", "true")
    text = stage_i.replace_toml_key(text, "kiss", "port", str(TEMP_KISS_PORT))
    text = stage_i.replace_toml_key(text, "console", "port", str(TEMP_CONSOLE_PORT))
    return stage_i.replace_toml_key(text, "console", "pty_link", f'"{TEMP_PTY}"')


def print_plan() -> None:
    print("===== YWD-1278 0G-P6 CONNECTED-MODE ACCEPTANCE =====")
    print(f"HOST_BASE_CHECKPOINT={EXPECTED_HOST_COMMIT}")
    print(f"SOURCE={LOCAL}")
    print(f"REMOTE_NODE={REMOTE}")
    print("REMOTE_ALIAS=YWDNOD")
    print(f"INFORMATION={TEST_INFORMATION}")
    print("TX_FREQUENCY_HZ=145050000")
    print("TX_POWER=200")
    print("SABM_ATTEMPTS_MAX=3")
    print("INFORMATION_FRAMES_NEW_MAX=1")
    print("ORDERLY_DISC_REQUIRED=YES")
    print("PERSISTENT_CONFIG_MUTATED=NO")
    print("FLASH_WRITTEN=NO")
    print("OPTION_BYTES_WRITTEN=NO")


def _send_actions(sock: socket.socket, managed) -> int:  # type: ignore[no-untyped-def]
    terminal = managed.terminal
    if terminal is None or terminal.link is None:
        return 0
    count = 0
    for action in terminal.link.actions:
        sock.sendall(encode(action.frame_no_fcs, port=0, command=DATA))
        count += 1
    return count


def _drive_until(
    sock: socket.socket,
    manager: ConnectedSessionManager,
    predicate,  # type: ignore[no-untyped-def]
    *,
    timeout: float,
) -> tuple[int, list[str]]:
    decoder = KISSStreamDecoder(max_body_bytes=4096)
    deadline = time.monotonic() + timeout
    next_poll = time.monotonic()
    dispatched = 0
    lines: list[str] = []
    sock.settimeout(0.2)
    while time.monotonic() < deadline:
        now = time.monotonic()
        if now >= next_poll:
            polled = manager.poll(now=now)
            dispatched += _send_actions(sock, polled)
            if polled.terminal is not None:
                lines.extend(polled.terminal.lines)
            next_poll = now + 0.05
        if predicate():
            return dispatched, lines
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            raise RuntimeError("KISS stream closed during connected acceptance")
        for message in decoder.feed(chunk):
            if message.port != 0 or message.command != DATA or not message.frame:
                continue
            handled = manager.handle_frame(message.frame, now=time.monotonic())
            dispatched += _send_actions(sock, handled)
            if handled.terminal is not None:
                lines.extend(handled.terminal.lines)
    raise RuntimeError("timed out waiting for connected-mode state transition")


def main() -> int:
    ap = argparse.ArgumentParser(description="0G-P6 guarded connected-mode RF acceptance")
    ap.add_argument("--transmit", action="store_true")
    ap.add_argument("--authorize", default="")
    ap.add_argument("--firmware", type=Path)
    ap.add_argument("--timeout", type=float, default=45.0)
    args = ap.parse_args()
    print_plan()
    if not args.transmit:
        print("YWD1278_0G_P6_DRY_RUN=PASS")
        print("SERVICE_MUTATED=NO")
        print("MODEM_UART_OPENED=NO")
        print("RF_TRANSMITTED=NO")
        return 0
    if os.geteuid() != 0:
        raise SystemExit("[FAIL] physical P6 requires root")
    if args.authorize != AUTHORIZATION_TOKEN:
        raise SystemExit(f"[FAIL] exact authorization required: --authorize {AUTHORIZATION_TOKEN}")
    if args.firmware is None:
        raise SystemExit("[FAIL] --firmware is required")
    if not 10.0 <= args.timeout <= 180.0:
        raise SystemExit("[FAIL] --timeout must be 10..180 seconds")

    ancestry = stage_i._run(["git", "merge-base", "--is-ancestor", EXPECTED_HOST_COMMIT, "HEAD"], check=False)
    if ancestry.returncode != 0:
        raise SystemExit("[FAIL] checkout does not descend from the P5 checkpoint")
    for path in (stage_i.PERSISTENT_CONFIG, stage_i.INSTALLED_COMMIT, stage_i.VENV_PYTHON, stage_i.ELIGIBILITY):
        if not path.exists():
            raise SystemExit(f"[FAIL] required qualified-appliance path missing: {path}")
    if stage_i._systemctl_state("is-enabled") != "enabled" or stage_i._systemctl_state("is-active") != "active":
        raise SystemExit("[FAIL] normal appliance must be enabled and active")
    original_bytes = stage_i.PERSISTENT_CONFIG.read_bytes()
    original_hash = hashlib.sha256(original_bytes).hexdigest()
    original_text = original_bytes.decode("utf-8")
    source = stage_i.validate_persistent_config(tomllib.loads(original_text))
    if source != str(LOCAL):
        raise SystemExit(f"[FAIL] configured station must be {LOCAL}; actual={source}")
    stage_i._check_firmware(args.firmware)
    stage_i._verify_eligibility(args.firmware)
    print(f"PERSISTENT_CONFIG_SHA256={original_hash}")
    print("PERSISTENT_TX_ENABLED=NO")
    typed = input(f"Type exactly {ARM_PHRASE} to run ONE connected RF exchange: ").strip()
    if typed != ARM_PHRASE:
        raise SystemExit("[FAIL] P6 interactive arm phrase did not match")

    daemon: subprocess.Popen[str] | None = None
    log_handle = None
    service_stopped = False
    completed = False
    total_actions = 0
    cleanup_error: BaseException | None = None
    try:
        stage_i._run(["systemctl", "stop", stage_i.SERVICE])
        service_stopped = True
        if stage_i._run(["fuser", stage_i.DEVICE], check=False).returncode == 0:
            raise RuntimeError("UART remained owned after normal service stop")
        stage_i._verify_hardware_identity()
        if TEMP_ROOT.exists():
            raise RuntimeError(f"stale P6 runtime directory exists: {TEMP_ROOT}")
        TEMP_ROOT.mkdir(mode=0o700, parents=True)
        TEMP_CONFIG.write_text(make_temporary_tx_config(original_text), encoding="utf-8")
        os.chmod(TEMP_CONFIG, 0o600)
        cfg = load_product_packet_engine_config(TEMP_CONFIG)
        if not cfg.tx_enabled or cfg.frequency_hz != stage_i.EXPECTED_FREQUENCY_HZ:
            raise RuntimeError("temporary P6 radio profile failed validation")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        log_handle = TEMP_LOG.open("w", encoding="utf-8")
        daemon = subprocess.Popen(
            [sys.executable, "-m", "ywd1278.daemon", "--config", str(TEMP_CONFIG)],
            cwd=str(ROOT), env=env, stdout=log_handle, stderr=subprocess.STDOUT, text=True,
        )
        stage_i._wait_port(TEMP_KISS_PORT, 6.0)
        manager = ConnectedSessionManager(
            local=LOCAL, max_sessions=1, maxframe=1, paclen=128,
            timers=LinkTimerConfig(t1_seconds=5.0, t2_seconds=1.0, t3_seconds=30.0, max_retries=2),
        )
        manager.open_session(SESSION_ID)
        with socket.create_connection(("127.0.0.1", TEMP_KISS_PORT), timeout=3.0) as kiss:
            started = manager.execute_line(SESSION_ID, f"CONNECT {REMOTE}", now=time.monotonic())
            total_actions += _send_actions(kiss, started)
            sent, received_lines = _drive_until(
                kiss, manager,
                lambda: manager.session_snapshot(SESSION_ID).link_state is LinkState.CONNECTED,
                timeout=args.timeout,
            )
            total_actions += sent
            print("SABM_UA_EXCHANGE=PASS")
            print(f"CONNECTED_TO={REMOTE}")

            payload = manager.execute_line(SESSION_ID, TEST_INFORMATION, now=time.monotonic())
            if not payload.accepted:
                raise RuntimeError(f"test I frame rejected: {payload.reason}")
            total_actions += _send_actions(kiss, payload)
            manager.execute_line(SESSION_ID, "COMMAND", now=time.monotonic())

            def information_acknowledged() -> bool:
                status = manager.execute_line(SESSION_ID, "CSTATUS", now=time.monotonic())
                return bool(
                    status.terminal is not None
                    and status.terminal.lines
                    and "STATE=CONNECTED" in status.terminal.lines[0]
                    and "OUT=0" in status.terminal.lines[0]
                )

            sent, more_lines = _drive_until(
                kiss, manager,
                information_acknowledged,
                timeout=args.timeout,
            )
            total_actions += sent
            received_lines.extend(more_lines)
            print("I_RR_EXCHANGE=PASS")
            print("NEW_INFORMATION_FRAMES=1")
            print(f"REMOTE_TEXT_LINES={len([x for x in received_lines if not x.startswith('CONNECTED')])}")

            release = manager.execute_line(SESSION_ID, "DISCONNECT", now=time.monotonic())
            total_actions += _send_actions(kiss, release)
            sent, _ = _drive_until(
                kiss, manager,
                lambda: manager.snapshot.owner_session_id is None,
                timeout=args.timeout,
            )
            total_actions += sent
            print("DISC_UA_EXCHANGE=PASS")
            completed = True
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
        if service_stopped:
            try:
                stage_i._restore_service(original_hash)
            except BaseException as exc:
                cleanup_error = exc
        if cleanup_error is not None:
            raise cleanup_error

    if not completed:
        raise SystemExit("[FAIL] connected acceptance did not complete")
    if hashlib.sha256(stage_i.PERSISTENT_CONFIG.read_bytes()).hexdigest() != original_hash:
        raise SystemExit("[FAIL] persistent config changed during P6")
    print("YWD1278_0G_P6_CONNECTED_ACCEPTANCE=PASS")
    print(f"LINK_ACTIONS_SUBMITTED={total_actions}")
    print("NORMAL_SERVICE_RESTORED=YES")
    print("PERSISTENT_TX_ENABLED=NO")
    print("PERSISTENT_CONFIG_MUTATED=NO")
    print("FLASH_WRITTEN=NO")
    print("OPTION_BYTES_WRITTEN=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
