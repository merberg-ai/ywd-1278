#!/usr/bin/env python3
"""Read-only MMDVM_HS application identity probe for YWD-1278.

This probe sends only MMDVM GET_VERSION (0x00). It does not configure the RF
engine, change frequency, enter bootloader mode, write flash, or write option
bytes.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import select
import termios
import time

START = 0xE0
GET_VERSION = 0x00


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
    data = bytearray()
    target: int | None = None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], min(0.1, max(0.0, deadline - time.monotonic())))
        if fd not in ready:
            continue
        chunk = os.read(fd, 512)
        for byte in chunk:
            if not data:
                if byte != START:
                    continue
                data.append(byte)
                continue
            data.append(byte)
            if len(data) == 2:
                target = data[1]
                if target < 3:
                    break
            if target is not None and len(data) >= target:
                return bytes(data[:target])
    return bytes(data)


def get_identity(device: str, timeout: float) -> str:
    fd = os.open(device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        configure(fd)
        termios.tcflush(fd, termios.TCIFLUSH)
        os.write(fd, bytes([START, 3, GET_VERSION]))
        reply = read_frame(fd, timeout)
    finally:
        os.close(fd)

    if len(reply) < 5 or reply[0] != START or reply[2] != GET_VERSION:
        raise RuntimeError(f"invalid/no GET_VERSION response: {reply.hex(' ') if reply else '<none>'}")
    return reply[4:].split(b"\0", 1)[0].decode("ascii", "replace").strip()


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


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only YWD-1278 MMDVM HAT identity probe")
    ap.add_argument("--device", default="/dev/ttyAMA0")
    ap.add_argument("--targets", default=str(Path(__file__).with_name("targets.json")))
    ap.add_argument("--timeout", type=float, default=2.5)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    identity = get_identity(args.device, args.timeout)
    matches = match_targets(identity, load_targets(Path(args.targets)))

    result = {
        "device": args.device,
        "identity": identity,
        "matched_target_ids": [item["id"] for item in matches],
        "unique_supported_identity": len(matches) == 1,
        "rf_configured": False,
        "flash_written": False,
        "option_bytes_written": False,
    }

    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
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
    raise SystemExit(main())
