#!/usr/bin/env python3
"""Safe MMDVM_HS application identity probe for YWD-1278.

The probe always tries MMDVM GET_VERSION (0x00) first without touching HAT
control GPIOs. If the UART is silent and the installed configuration explicitly
names an allowlisted hardware target, it may invoke that target's qualified
application-release operation (BOOT0 normal, RESET released, no reset pulse)
and retry GET_VERSION.

It never configures RF, changes frequency, enters the STM32 bootloader, writes
flash, or writes option bytes.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import termios
import time

START = 0xE0
GET_VERSION = 0x00
REQUEST = bytes([START, 3, GET_VERSION])


def configure(fd: int) -> None:
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
    attrs[3] = 0
    attrs[4] = termios.B115200
    attrs[5] = termios.B115200
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)


def read_frame(fd: int, timeout: float) -> bytes:
    """Read one MMDVM frame, tolerating junk/partial data before START."""
    data = bytearray()
    target: int | None = None
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        ready, _, _ = select.select([fd], [], [], min(0.1, remaining))
        if fd not in ready:
            continue

        chunk = os.read(fd, 512)
        for byte in chunk:
            if not data:
                if byte == START:
                    data.append(byte)
                continue

            if len(data) == 1:
                if byte < 3:
                    data.clear()
                    target = None
                    if byte == START:
                        data.append(byte)
                    continue
                data.append(byte)
                target = byte
                continue

            data.append(byte)
            if target is not None and len(data) >= target:
                return bytes(data[:target])

    return bytes(data)


def parse_identity(reply: bytes) -> str | None:
    if len(reply) < 5 or reply[0] != START or reply[2] != GET_VERSION:
        return None
    return reply[4:].split(b"\0", 1)[0].decode("ascii", "replace").strip()


def get_identity(
    device: str,
    timeout: float,
    attempts: int = 3,
    settle_seconds: float = 0.10,
) -> str:
    if attempts < 1:
        raise ValueError("attempts must be >= 1")

    fd = os.open(device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    observed: list[bytes] = []
    try:
        configure(fd)
        time.sleep(max(0.0, settle_seconds))

        for attempt in range(1, attempts + 1):
            termios.tcflush(fd, termios.TCIOFLUSH)
            written = os.write(fd, REQUEST)
            if written != len(REQUEST):
                raise RuntimeError(
                    f"short GET_VERSION write on attempt {attempt}: {written}/{len(REQUEST)}"
                )
            termios.tcdrain(fd)

            reply = read_frame(fd, timeout)
            observed.append(reply)
            identity = parse_identity(reply)
            if identity:
                return identity

            if attempt < attempts:
                time.sleep(0.10)
    finally:
        os.close(fd)

    details = ", ".join(
        f"attempt{i + 1}={frame.hex(' ') if frame else '<none>'}"
        for i, frame in enumerate(observed)
    )
    raise RuntimeError(f"invalid/no GET_VERSION response after {attempts} attempts: {details}")


def load_targets(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != 1 or not isinstance(payload.get("targets"), list):
        raise RuntimeError("unsupported targets manifest schema")
    return payload["targets"]


def match_targets(identity: str, targets: list[dict]) -> list[dict]:
    matches: list[dict] = []
    for target in targets:
        exact = target.get("accepted_running_identities") or []
        prefix = target.get("ywd1278_identity_prefix")
        if identity in exact or (isinstance(prefix, str) and prefix and identity.startswith(prefix)):
            matches.append(target)
    return matches


def release_configured_application(config: Path, targets: Path) -> str:
    helper = Path(__file__).with_name("hat_control.py")
    proc = subprocess.run(
        [
            sys.executable,
            str(helper),
            "application-release",
            "--targets",
            str(targets),
            "--config",
            str(config),
        ],
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "target-aware application release failed").strip()
        raise RuntimeError(detail)
    return proc.stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="Safe YWD-1278 MMDVM HAT identity probe")
    ap.add_argument("--device", default="/dev/ttyAMA0")
    ap.add_argument("--targets", default=str(Path(__file__).with_name("targets.json")))
    ap.add_argument("--config", default="/etc/ywd-1278/config.toml")
    ap.add_argument("--timeout", type=float, default=1.25, help="per-attempt response timeout")
    ap.add_argument("--attempts", type=int, default=3)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    target_path = Path(args.targets)
    control_output = ""
    application_release_used = False

    try:
        identity = get_identity(args.device, args.timeout, args.attempts)
    except RuntimeError as first_error:
        config_path = Path(args.config)
        if not config_path.is_file():
            raise RuntimeError(
                f"{first_error}; no configured hardware target is available for safe application release"
            ) from first_error
        try:
            control_output = release_configured_application(config_path, target_path)
        except RuntimeError as release_error:
            raise RuntimeError(f"{first_error}; {release_error}") from first_error
        application_release_used = True
        time.sleep(0.25)
        identity = get_identity(args.device, args.timeout, args.attempts)

    matches = match_targets(identity, load_targets(target_path))

    result = {
        "device": args.device,
        "identity": identity,
        "matched_target_ids": [item["id"] for item in matches],
        "unique_supported_identity": len(matches) == 1,
        "application_release_used": application_release_used,
        "rf_configured": False,
        "flash_written": False,
        "option_bytes_written": False,
    }

    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        if control_output:
            print(control_output)
        print(f"HAT_APPLICATION_RELEASE_USED={'YES' if application_release_used else 'NO'}")
        print(f"HAT_DEVICE={args.device}")
        print(f"HAT_IDENTITY={identity}")
        if len(matches) == 1:
            print(f"HAT_TARGET_MATCH={matches[0]['id']}")
            print("HAT_TARGET_IDENTITY=PASS")
        elif not matches:
            print("HAT_TARGET_MATCH=NONE")
            print("HAT_TARGET_IDENTITY=UNSUPPORTED")
        else:
            print("HAT_TARGET_MATCH=AMBIGUOUS")
            print("HAT_TARGET_IDENTITY=FAIL")
        print("RF_CONFIGURED=NO")
        print("FLASH_WRITTEN=NO")
        print("OPTION_BYTES_WRITTEN=NO")

    return 0 if len(matches) == 1 else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"HAT_PROBE_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2)
