#!/usr/bin/env python3
"""RX-only post-reboot Stage-G qualifier.

Receives one fresh KISS DATA frame, then requires the decoded AX.25 source to
advance persistent MHEARD state on both Telnet and PTY surfaces.  This helper
never opens the modem UART and never sends KISS DATA.
"""
from __future__ import annotations

import argparse
import re
import socket
import time

import qualify_stage_g_live_rx as base

_MHEARD_RE = re.compile(r"^(?P<source>\S+)\s+COUNT=(?P<count>\d+)\s+LAST_NS=(?P<last_ns>\d+)\b")


def parse_mheard_entry(text: str, source: str) -> tuple[int, int] | None:
    wanted = source.upper()
    for raw in text.replace("\r", "\n").split("\n"):
        line = raw.strip()
        m = _MHEARD_RE.match(line)
        if not m or m.group("source").upper() != wanted:
            continue
        return int(m.group("count")), int(m.group("last_ns"))
    return None


def advanced(before: tuple[int, int] | None, after: tuple[int, int] | None) -> bool:
    if after is None:
        return False
    if before is None:
        return True
    return after[0] > before[0] or after[1] > before[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kiss-host", default="127.0.0.1")
    ap.add_argument("--kiss-port", type=int, default=8001)
    ap.add_argument("--console-host", default="127.0.0.1")
    ap.add_argument("--console-port", type=int, default=8010)
    ap.add_argument("--pty", default="/run/ywd-1278/tnc")
    ap.add_argument("--timeout", type=float, default=120.0)
    args = ap.parse_args()

    health_telnet = base.telnet_command(args.console_host, args.console_port, "HEALTH")
    health_pty = base.pty_command(args.pty, "HEALTH")
    if "HEALTH OK" not in health_telnet or "HEALTH OK" not in health_pty:
        raise SystemExit("[FAIL] post-reboot console HEALTH is not OK on both surfaces")

    before_telnet_text = base.telnet_command(args.console_host, args.console_port, "MHEARD 100")
    before_pty_text = base.pty_command(args.pty, "MHEARD 100")

    print("YWD1278_STAGE_G_REBOOT_CONSOLE_HEALTH=PASS", flush=True)
    print("POST_REBOOT_MHEARD_BASELINE_CAPTURED=YES", flush=True)
    print("WAITING_FOR_FRESH_LIVE_PACKET_145050=YES", flush=True)
    print("Generate one known packet on 145.050 MHz now.", flush=True)

    with socket.create_connection((args.kiss_host, args.kiss_port), timeout=3.0) as kiss:
        frame = base.recv_kiss_data(kiss, args.timeout)
    source = base.ax25_source(frame)

    before_telnet = parse_mheard_entry(before_telnet_text, source)
    before_pty = parse_mheard_entry(before_pty_text, source)

    deadline = time.monotonic() + 8.0
    after_telnet = None
    after_pty = None
    while time.monotonic() < deadline:
        telnet_text = base.telnet_command(args.console_host, args.console_port, "MHEARD 100")
        pty_text = base.pty_command(args.pty, "MHEARD 100")
        after_telnet = parse_mheard_entry(telnet_text, source)
        after_pty = parse_mheard_entry(pty_text, source)
        if advanced(before_telnet, after_telnet) and advanced(before_pty, after_pty):
            break
        time.sleep(0.25)

    if not advanced(before_telnet, after_telnet):
        raise SystemExit(f"[FAIL] Telnet MHEARD did not advance for fresh source {source}")
    if not advanced(before_pty, after_pty):
        raise SystemExit(f"[FAIL] PTY MHEARD did not advance for fresh source {source}")

    print("YWD1278_STAGE_G_REBOOT_LIVE_RX=PASS")
    print(f"KISS_FRAME_BYTES={len(frame)}")
    print(f"AX25_SOURCE={source}")
    print("KISS_DATA_RECEIVED=YES")
    print("TELNET_MHEARD_FRESH_ADVANCE=YES")
    print("PTY_MHEARD_FRESH_ADVANCE=YES")
    print("TX_COMMAND_SENT=NO")
    print("KISS_DATA_SENT=NO")
    print("MODEM_UART_OPENED_BY_QUALIFIER=NO")
    print("RF_TRANSMITTED_BY_QUALIFIER=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
