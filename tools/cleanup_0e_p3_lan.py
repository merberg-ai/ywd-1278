#!/usr/bin/env python3
"""Safely remove residual 0E-P3 qualification listeners and temporary files."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import socket
import sys
import time

PORT = 8023
TEMP_PATHS = (
    Path("/tmp/ywd1278-p3.auth"),
    Path("/tmp/ywd1278-0e-p3-lan-state.json"),
    Path("/tmp/ywd1278-p3-wildcard.log"),
    Path("/tmp/ywd1278-p3-public.log"),
    Path("/tmp/ywd1278-p3-lan-ip"),
    Path("/tmp/ywd1278-0e-p3-lan.pid"),
)


def cmdline(pid: int) -> list[str]:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return []
    return [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]


def is_p3_listener(args: list[str], host: str | None) -> bool:
    if not args:
        return False
    try:
        module_index = args.index("-m")
    except ValueError:
        return False
    if module_index + 1 >= len(args) or args[module_index + 1] != "ywd1278.console.lan_telnet":
        return False
    try:
        port_index = args.index("--port")
    except ValueError:
        return False
    if port_index + 1 >= len(args) or args[port_index + 1] != str(PORT):
        return False
    if host is not None:
        try:
            bind_index = args.index("--bind")
        except ValueError:
            return False
        if bind_index + 1 >= len(args) or args[bind_index + 1] != host:
            return False
    return True


def matching_pids(host: str | None) -> list[int]:
    matches: list[int] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == os.getpid():
            continue
        args = cmdline(pid)
        if is_p3_listener(args, host):
            matches.append(pid)
    return sorted(matches)


def wait_dead(pid: int, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return True
        time.sleep(0.05)
    return False


def socket_open(host: str) -> bool:
    try:
        with socket.create_connection((host, PORT), timeout=0.5):
            return True
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host",
        default="192.168.1.11",
        help="expected P3 bind address (default: 192.168.1.11)",
    )
    args = parser.parse_args(argv)

    print("===== 0E-P3 RESIDUAL LISTENER CLEANUP =====")
    print(f"TARGET={args.host}:{PORT}")

    matches = matching_pids(args.host)
    if matches:
        print("MATCHING_PIDS=" + ",".join(str(pid) for pid in matches))
    else:
        print("MATCHING_PIDS=NONE")

    for pid in matches:
        print(f"Stopping PID {pid}: {' '.join(cmdline(pid))}")
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        if not wait_dead(pid):
            print(f"PID {pid} did not exit after SIGTERM; sending SIGKILL")
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if not wait_dead(pid):
                print(f"ERROR: PID {pid} is still present", file=sys.stderr)
                return 1

    leftovers = matching_pids(args.host)
    if leftovers:
        print("ERROR: matching P3 listener processes remain: " + ",".join(map(str, leftovers)), file=sys.stderr)
        return 1

    if socket_open(args.host):
        print(f"ERROR: {args.host}:{PORT} is still accepting TCP connections", file=sys.stderr)
        return 1

    for path in TEMP_PATHS:
        try:
            path.unlink()
            print(f"REMOVED={path}")
        except FileNotFoundError:
            pass

    print("P3_LISTENER_PROCESS=ABSENT")
    print("P3_TCP_8023=NOT_LISTENING")
    print("P3_TEMP_AUTH_STATE=REMOVED")
    print("YWD1278_0E_P3_CLEANUP=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
