#!/usr/bin/env python3
"""RX-only Stage-G qualifier for the installed YWD-1278 appliance.

Uses the real installed KISS socket, loopback Telnet console, and stable PTY.
It never sends KISS DATA and never opens the modem UART.
"""

from __future__ import annotations

import argparse
import os
import select
import socket
import time
from pathlib import Path

FEND = 0xC0
FESC = 0xDB
TFEND = 0xDC
TFESC = 0xDD


def kiss_unescape(payload: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(payload):
        b = payload[i]
        if b == FESC:
            i += 1
            if i >= len(payload):
                raise ValueError("truncated KISS escape")
            esc = payload[i]
            if esc == TFEND:
                out.append(FEND)
            elif esc == TFESC:
                out.append(FESC)
            else:
                raise ValueError("invalid KISS escape")
        else:
            out.append(b)
        i += 1
    return bytes(out)


def recv_kiss_data(sock: socket.socket, timeout: float) -> bytes:
    deadline = time.monotonic() + timeout
    buf = bytearray()
    in_frame = False
    while time.monotonic() < deadline:
        remaining = max(0.05, deadline - time.monotonic())
        sock.settimeout(min(1.0, remaining))
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            raise RuntimeError("KISS connection closed before a DATA frame arrived")
        for b in chunk:
            if b == FEND:
                if in_frame and buf:
                    decoded = kiss_unescape(bytes(buf))
                    buf.clear()
                    if decoded and (decoded[0] & 0x0F) == 0x00:
                        return decoded[1:]
                else:
                    buf.clear()
                in_frame = True
            elif in_frame:
                buf.append(b)
    raise TimeoutError(f"no KISS DATA frame within {timeout:.0f}s")


def decode_ax25_address(raw: bytes) -> str:
    if len(raw) != 7:
        raise ValueError("AX.25 address must be 7 bytes")
    call = "".join(chr((b >> 1) & 0x7F) for b in raw[:6]).rstrip()
    ssid = (raw[6] >> 1) & 0x0F
    return f"{call}-{ssid}" if ssid else call


def ax25_source(frame: bytes) -> str:
    if len(frame) < 14:
        raise ValueError("AX.25 frame too short")
    return decode_ax25_address(frame[7:14])


def recv_until(sock: socket.socket, token: bytes, timeout: float = 3.0) -> bytes:
    deadline = time.monotonic() + timeout
    data = bytearray()
    while time.monotonic() < deadline:
        sock.settimeout(max(0.05, min(0.5, deadline - time.monotonic())))
        try:
            part = sock.recv(4096)
        except socket.timeout:
            continue
        if not part:
            break
        data.extend(part)
        if token in data:
            break
    return bytes(data)


def telnet_command(host: str, port: int, command: str, timeout: float = 4.0) -> str:
    with socket.create_connection((host, port), timeout=3.0) as sock:
        recv_until(sock, b"cmd:", timeout=2.0)
        sock.sendall(command.encode("ascii") + b"\r")
        data = recv_until(sock, b"cmd:", timeout=timeout)
    return data.decode("ascii", errors="ignore")


def pty_command(path: str, command: str, timeout: float = 4.0) -> str:
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        deadline = time.monotonic() + 1.5
        initial = bytearray()
        while time.monotonic() < deadline:
            readable, _, _ = select.select([fd], [], [], 0.15)
            if fd in readable:
                try:
                    initial.extend(os.read(fd, 4096))
                except BlockingIOError:
                    pass
                if b"cmd:" in initial:
                    break
        os.write(fd, command.encode("ascii") + b"\r")
        data = bytearray()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            readable, _, _ = select.select([fd], [], [], 0.2)
            if fd not in readable:
                continue
            try:
                part = os.read(fd, 4096)
            except BlockingIOError:
                continue
            if not part:
                continue
            data.extend(part)
            if b"cmd:" in data:
                break
        return data.decode("ascii", errors="ignore")
    finally:
        os.close(fd)


def wait_mheard(source: str, host: str, port: int, pty: str) -> tuple[str, str]:
    deadline = time.monotonic() + 8.0
    last_telnet = ""
    last_pty = ""
    while time.monotonic() < deadline:
        last_telnet = telnet_command(host, port, "MHEARD 20")
        last_pty = pty_command(pty, "MHEARD 20")
        if source in last_telnet and source in last_pty:
            return last_telnet, last_pty
        time.sleep(0.25)
    raise RuntimeError(
        f"decoded source {source} did not appear in both MHEARD surfaces; "
        f"telnet={last_telnet!r} pty={last_pty!r}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kiss-host", default="127.0.0.1")
    ap.add_argument("--kiss-port", type=int, default=8001)
    ap.add_argument("--console-host", default="127.0.0.1")
    ap.add_argument("--console-port", type=int, default=8010)
    ap.add_argument("--pty", default="/run/ywd-1278/tnc")
    ap.add_argument("--timeout", type=float, default=120.0)
    args = ap.parse_args()

    pty = Path(args.pty)
    if not pty.exists():
        raise SystemExit(f"[FAIL] stable PTY link does not exist: {pty}")

    health_telnet = telnet_command(args.console_host, args.console_port, "HEALTH")
    health_pty = pty_command(args.pty, "HEALTH")
    if "HEALTH OK" not in health_telnet:
        raise SystemExit(f"[FAIL] Telnet HEALTH is not OK: {health_telnet!r}")
    if "HEALTH OK" not in health_pty:
        raise SystemExit(f"[FAIL] PTY HEALTH is not OK: {health_pty!r}")

    print("YWD1278_STAGE_G_CONSOLE_HEALTH=PASS", flush=True)
    print("WAITING_FOR_LIVE_PACKET_145050=YES", flush=True)
    print("Generate one known packet on 145.050 MHz now.", flush=True)

    with socket.create_connection((args.kiss_host, args.kiss_port), timeout=3.0) as kiss:
        frame = recv_kiss_data(kiss, args.timeout)

    source = ax25_source(frame)
    wait_mheard(source, args.console_host, args.console_port, args.pty)

    print("YWD1278_STAGE_G_LIVE_RX=PASS")
    print(f"KISS_FRAME_BYTES={len(frame)}")
    print(f"AX25_SOURCE={source}")
    print("KISS_DATA_RECEIVED=YES")
    print("TELNET_MHEARD_SOURCE_MATCH=YES")
    print("PTY_MHEARD_SOURCE_MATCH=YES")
    print("TX_COMMAND_SENT=NO")
    print("KISS_DATA_SENT=NO")
    print("MODEM_UART_OPENED_BY_QUALIFIER=NO")
    print("RF_TRANSMITTED_BY_QUALIFIER=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
