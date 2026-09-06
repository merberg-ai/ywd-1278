#!/usr/bin/env python3
"""Guarded 0H-P10 physical LinBPQ personal-message delivery acceptance."""
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
from ywd1278.link.timed_link import LinkTimerConfig, TimedModulo8DataLink  # noqa: E402
from ywd1278.node.forwarding_integration import PreparedForwardMessage  # noqa: E402
from ywd1278.node.linbpq_dialogue import LinBPQPersonalDelivery, LinBPQState  # noqa: E402
from ywd1278.service.appliance import load_product_packet_engine_config  # noqa: E402

EXPECTED_HOST_COMMIT = "618585fd2588235296a281022cf39feb5f2ba8e9"
AUTHORIZATION_TOKEN = "0H-P10-LINBPQ-145050-KJ6YWD5-ONE"
ARM_PHRASE = "TRANSMIT-0H-P10-LINBPQ-KJ6YWD-5-ONE"
TEMP_ROOT = Path("/run/ywd-1278-0h-p10")
TEMP_CONFIG = TEMP_ROOT / "config.toml"
TEMP_LOG = TEMP_ROOT / "daemon.log"
TEMP_KISS_PORT = 18601
TEMP_CONSOLE_PORT = 18610
TEMP_PTY = str(TEMP_ROOT / "tnc")

LOCAL = Address.parse("KJ6YWD-10")
REMOTE_LISTENER = Address.parse("KJ6YWD-5")
BBS = Address.parse("KJ6YWD-1")
DESTINATION = Address.parse("KJ6YWD-15")
PROMPT_CALLSIGN = "KJ6YWD"
BBS_ENTRY = b"BBS\r"
SUBJECT = "P10 TEST"
BODY = b"YWD-1278 0H-P10 LINBPQ DELIVERY 1/1"
MAX_REMOTE_CAPTURE = 4096
EXPECTED_DIALOGUE_ACTIONS = ("SP", "TITLE", "BODY", "BODY_END", "END")


def make_work() -> PreparedForwardMessage:
    return PreparedForwardMessage(
        10,
        LOCAL,
        DESTINATION,
        BBS,
        SUBJECT,
        (BODY,),
        (LOCAL,),
    )


def build_dialogue() -> LinBPQPersonalDelivery:
    return LinBPQPersonalDelivery(
        work=make_work(),
        bbs=BBS,
        prompt_callsign=PROMPT_CALLSIGN,
    )


def make_temporary_tx_config(original: str) -> str:
    text = stage_i.replace_toml_key(original, "radio", "tx_power", str(stage_i.TX_POWER))
    text = stage_i.replace_toml_key(text, "radio", "tx_enabled", "true")
    text = stage_i.replace_toml_key(text, "kiss", "port", str(TEMP_KISS_PORT))
    text = stage_i.replace_toml_key(text, "console", "port", str(TEMP_CONSOLE_PORT))
    return stage_i.replace_toml_key(text, "console", "pty_link", f'"{TEMP_PTY}"')


def _escape(data: bytes) -> str:
    return "".join(chr(value) if 32 <= value <= 126 else f"\\x{value:02x}" for value in data)


def _send_link_actions(sock: socket.socket, result) -> int:  # type: ignore[no-untyped-def]
    count = 0
    for action in result.actions:
        sock.sendall(encode(action.frame_no_fcs, port=0, command=DATA))
        count += 1
    return count


def _submit_information(
    sock: socket.socket,
    link: TimedModulo8DataLink,
    payload: bytes,
    *,
    now: float,
) -> int:
    if not isinstance(payload, bytes) or not 1 <= len(payload) <= 128:
        raise RuntimeError(f"outbound information must be 1..128 bytes; got {len(payload)}")
    result = link.send_information(payload, now=now)
    if not result.accepted:
        raise RuntimeError(f"connected information rejected: {result.reason}")
    return _send_link_actions(sock, result)


def print_plan() -> None:
    print("===== YWD-1278 0H-P10 LINBPQ DELIVERY ACCEPTANCE =====")
    print(f"HOST_BASE_CHECKPOINT={EXPECTED_HOST_COMMIT}")
    print(f"SOURCE={LOCAL}")
    print(f"REMOTE_LISTENER={REMOTE_LISTENER}")
    print(f"BBS_IDENTITY={BBS}")
    print(f"DESTINATION={DESTINATION}")
    print(f"SUBJECT={SUBJECT}")
    print(f"BODY={BODY.decode('ascii')}")
    print("ENTRY_COMMAND=BBS<CR>")
    print("EXPECTED_DIALOGUE=SP,TITLE,BODY,BODY_END,/EX,PROMPT_RETURN")
    print("TX_FREQUENCY_HZ=145050000")
    print("TX_POWER=200")
    print("ONE_MESSAGE_MAX=YES")
    print("AUTOMATIC_RETRY_OF_MESSAGE=NO")
    print("PERSISTENT_CONFIG_MUTATED=NO")
    print("FLASH_WRITTEN=NO")
    print("OPTION_BYTES_WRITTEN=NO")


def main() -> int:
    ap = argparse.ArgumentParser(description="0H-P10 guarded LinBPQ delivery RF acceptance")
    ap.add_argument("--transmit", action="store_true")
    ap.add_argument("--authorize", default="")
    ap.add_argument("--firmware", type=Path)
    ap.add_argument("--timeout", type=float, default=240.0)
    args = ap.parse_args()

    print_plan()
    if not args.transmit:
        print("YWD1278_0H_P10_DRY_RUN=PASS")
        print("SERVICE_MUTATED=NO")
        print("MODEM_UART_OPENED=NO")
        print("RF_TRANSMITTED=NO")
        return 0

    if os.geteuid() != 0:
        raise SystemExit("[FAIL] physical P10 requires root")
    if args.authorize != AUTHORIZATION_TOKEN:
        raise SystemExit(
            f"[FAIL] exact authorization required: --authorize {AUTHORIZATION_TOKEN}"
        )
    if args.firmware is None:
        raise SystemExit("[FAIL] --firmware is required")
    if not 60.0 <= args.timeout <= 360.0:
        raise SystemExit("[FAIL] --timeout must be 60..360 seconds")

    ancestry = stage_i._run(
        ["git", "merge-base", "--is-ancestor", EXPECTED_HOST_COMMIT, "HEAD"],
        check=False,
    )
    if ancestry.returncode != 0:
        raise SystemExit("[FAIL] checkout does not descend from the qualified P9 checkpoint")

    for path in (
        stage_i.PERSISTENT_CONFIG,
        stage_i.INSTALLED_COMMIT,
        stage_i.VENV_PYTHON,
        stage_i.ELIGIBILITY,
    ):
        if not path.exists():
            raise SystemExit(f"[FAIL] required qualified-appliance path missing: {path}")

    if (
        stage_i._systemctl_state("is-enabled") != "enabled"
        or stage_i._systemctl_state("is-active") != "active"
    ):
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

    typed = input(
        f"Type exactly {ARM_PHRASE} to transmit ONE LinBPQ delivery session: "
    ).strip()
    if typed != ARM_PHRASE:
        raise SystemExit("[FAIL] P10 interactive arm phrase did not match")

    daemon: subprocess.Popen[str] | None = None
    log_handle = None
    service_stopped = False
    cleanup_error: BaseException | None = None
    completed = False
    total_actions = 0
    remote_capture = bytearray()
    dialogue_kinds: list[str] = []

    try:
        stage_i._run(["systemctl", "stop", stage_i.SERVICE])
        service_stopped = True
        if stage_i._run(["fuser", stage_i.DEVICE], check=False).returncode == 0:
            raise RuntimeError("UART remained owned after normal service stop")
        stage_i._verify_hardware_identity()

        if TEMP_ROOT.exists():
            raise RuntimeError(f"stale P10 runtime directory exists: {TEMP_ROOT}")
        TEMP_ROOT.mkdir(mode=0o700, parents=True)
        TEMP_CONFIG.write_text(make_temporary_tx_config(original_text), encoding="utf-8")
        os.chmod(TEMP_CONFIG, 0o600)

        cfg = load_product_packet_engine_config(TEMP_CONFIG)
        if not cfg.tx_enabled or cfg.frequency_hz != stage_i.EXPECTED_FREQUENCY_HZ:
            raise RuntimeError("temporary P10 radio profile failed validation")

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

        link = TimedModulo8DataLink(
            local=LOCAL,
            remote=REMOTE_LISTENER,
            maxframe=4,
            paclen=128,
            timers=LinkTimerConfig(
                t1_seconds=8.0,
                t2_seconds=1.0,
                t3_seconds=60.0,
                max_retries=2,
            ),
        )
        dialogue = build_dialogue()
        decoder = KISSStreamDecoder(max_body_bytes=4096)
        deadline = time.monotonic() + args.timeout
        next_poll = time.monotonic()
        bbs_entry_sent = False
        disconnect_started = False

        print("PHYSICAL_SESSION_ARMED=YES")
        print(f"CONNECT_FROM={LOCAL}")
        print(f"CONNECT_TO={REMOTE_LISTENER}")
        print("NO_OPERATOR_INPUT_REQUIRED_AFTER_RF_ARM=YES")

        with socket.create_connection(
            ("127.0.0.1", TEMP_KISS_PORT), timeout=3.0
        ) as kiss:
            kiss.settimeout(0.2)
            started = link.connect(now=time.monotonic())
            if not started.accepted:
                raise RuntimeError(f"SABM start rejected: {started.reason}")
            total_actions += _send_link_actions(kiss, started)

            while time.monotonic() < deadline:
                now = time.monotonic()

                if now >= next_poll:
                    polled = link.poll(now=now)
                    total_actions += _send_link_actions(kiss, polled)
                    next_poll = now + 0.05

                if link.snapshot.retry_exhausted:
                    raise RuntimeError("AX.25 link retry limit exhausted")

                if (
                    link.snapshot.link.state is LinkState.CONNECTED
                    and not bbs_entry_sent
                ):
                    total_actions += _submit_information(
                        kiss, link, BBS_ENTRY, now=time.monotonic()
                    )
                    bbs_entry_sent = True
                    print("SABM_UA_EXCHANGE=PASS")
                    print("BBS_ENTRY_SUBMITTED=YES")

                if (
                    dialogue.snapshot.state is LinBPQState.COMPLETE
                    and link.snapshot.link.outstanding == 0
                    and not disconnect_started
                ):
                    released = link.disconnect(now=time.monotonic())
                    if not released.accepted:
                        raise RuntimeError(f"DISC start rejected: {released.reason}")
                    total_actions += _send_link_actions(kiss, released)
                    disconnect_started = True

                if (
                    disconnect_started
                    and link.snapshot.link.state is LinkState.DISCONNECTED
                ):
                    completed = True
                    break

                try:
                    chunk = kiss.recv(4096)
                except socket.timeout:
                    continue
                if not chunk:
                    raise RuntimeError("KISS stream closed during P10")

                for message in decoder.feed(chunk):
                    if message.port != 0 or message.command != DATA or not message.frame:
                        continue
                    handled = link.handle_frame(message.frame, now=time.monotonic())
                    total_actions += _send_link_actions(kiss, handled)
                    if not handled.accepted:
                        continue

                    for info in handled.delivered:
                        if len(remote_capture) + len(info) > MAX_REMOTE_CAPTURE:
                            raise RuntimeError("remote transcript capture overflow")
                        remote_capture.extend(info)
                        print(f"REMOTE_I={_escape(info)}")

                        if not bbs_entry_sent or dialogue.snapshot.state in (
                            LinBPQState.COMPLETE,
                            LinBPQState.FAILED,
                        ):
                            continue

                        result = dialogue.feed(info)
                        if not result.accepted:
                            raise RuntimeError(f"P9 dialogue failed: {result.reason}")

                        for action in result.actions:
                            dialogue_kinds.append(action.kind)
                            total_actions += _submit_information(
                                kiss,
                                link,
                                action.data,
                                now=time.monotonic(),
                            )
                            print(
                                f"P9_ACTION={action.kind} BYTES={len(action.data)} "
                                f"DATA={_escape(action.data)}"
                            )

        if not completed:
            raise RuntimeError(
                "P10 timed out before accepted message and orderly AX.25 release; "
                f"link={link.snapshot.link.state.value} dialogue={dialogue.snapshot.state.value}"
            )
        if dialogue.snapshot.state is not LinBPQState.COMPLETE:
            raise RuntimeError(f"P9 dialogue did not complete: {dialogue.snapshot}")
        if tuple(dialogue_kinds) != EXPECTED_DIALOGUE_ACTIONS:
            raise RuntimeError(f"unexpected P9 action sequence: {dialogue_kinds}")

        print("BPQ_SID_OBSERVED=PASS")
        print("BBS_PROMPT_OBSERVED=PASS")
        print("LIVE_TITLE_PROMPT=PASS")
        print("LIVE_BODY_PROMPT=PASS")
        print("MESSAGE_SUBMISSION_PROMPT_RETURN=PASS")
        print("P9_DIALOGUE_ACTIONS=" + ",".join(dialogue_kinds))
        print("REMOTE_TRANSCRIPT=" + _escape(bytes(remote_capture)))
        print("DISC_UA_EXCHANGE=PASS")

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
        raise SystemExit("[FAIL] P10 LinBPQ acceptance incomplete")
    if hashlib.sha256(stage_i.PERSISTENT_CONFIG.read_bytes()).hexdigest() != original_hash:
        raise SystemExit("[FAIL] persistent config changed during P10")

    print("YWD1278_0H_P10_LINBPQ_DELIVERY_ACCEPTANCE=PASS")
    print(f"LINK_ACTIONS_SUBMITTED={total_actions}")
    print("ONE_MESSAGE_SUBMITTED=YES")
    print("NORMAL_SERVICE_RESTORED=YES")
    print("PERSISTENT_TX_ENABLED=NO")
    print("PERSISTENT_CONFIG_MUTATED=NO")
    print("FLASH_WRITTEN=NO")
    print("OPTION_BYTES_WRITTEN=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
