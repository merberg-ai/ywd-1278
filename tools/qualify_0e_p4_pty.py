#!/usr/bin/env python3
"""Deterministic target-host smoke for the 0E-P4 virtual PTY TNC personality."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import select
import stat
import tempfile
import termios
import threading
import time

from ywd1278.console.local import LocalTNCCommandShell
from ywd1278.console.pty_serial import PTY_MODE, VirtualPTYTNC
from ywd1278.monitor.policy import MonitorPolicyState


def _shell() -> LocalTNCCommandShell:
    return LocalTNCCommandShell(monitor_policy=MonitorPolicyState())


def _read_until(fd: int, needle: bytes, *, timeout: float) -> bytes:
    deadline = time.monotonic() + timeout
    data = bytearray()
    while needle not in data:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(
                f"timed out waiting for {needle!r}; received {bytes(data)!r}"
            )
        readable, _, _ = select.select([fd], [], [], remaining)
        if not readable:
            continue
        try:
            chunk = os.read(fd, 4096)
        except BlockingIOError:
            continue
        if chunk:
            data.extend(chunk)
    return bytes(data)


def _command(fd: int, command: str, *, timeout: float) -> bytes:
    os.write(fd, command.encode("ascii") + b"\r")
    return _read_until(fd, b"cmd:", timeout=timeout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Exercise 0E-P4 entirely through a real local kernel PTY"
    )
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args(argv)
    if not 0.1 <= args.timeout <= 10.0:
        raise SystemExit("--timeout must be between 0.1 and 10 seconds")

    with tempfile.TemporaryDirectory(prefix="ywd1278-p4-") as tmp:
        link = str(Path(tmp) / "tnc")
        server = VirtualPTYTNC(
            shell_factory=_shell,
            link_path=link,
            poll_seconds=0.01,
        )
        stop = threading.Event()
        thread: threading.Thread | None = None
        first: int | None = None
        second: int | None = None
        slave = ""
        try:
            slave = server.open()
            assert slave.startswith("/dev/pts/"), slave
            assert os.path.islink(link)
            assert os.readlink(link) == slave
            assert stat.S_IMODE(os.stat(slave).st_mode) == PTY_MODE

            thread = threading.Thread(
                target=server.serve,
                args=(stop,),
                name="p4-target-qualification",
                daemon=True,
            )
            thread.start()

            first = os.open(link, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            assert os.isatty(first)
            termios.tcgetattr(first)
            banner = _read_until(first, b"cmd:", timeout=args.timeout)
            assert b"VIRTUAL PTY TNC CONSOLE" in banner

            reply = _command(first, "VERSION", timeout=args.timeout)
            assert b"YWD-1278 0.1.0-alpha0" in reply
            reply = _command(first, "MCOM", timeout=args.timeout)
            assert b"MCOM OFF" in reply
            reply = _command(first, "MCOM ON", timeout=args.timeout)
            assert b"MCOM ON" in reply
            assert b"MONITOR_GENERATION 1" in reply
            reply = _command(first, "CONNECT KJ6YWD", timeout=args.timeout)
            assert b"ERROR UNKNOWN COMMAND CONNECT" in reply
            reply = _command(first, "TX hello", timeout=args.timeout)
            assert b"ERROR UNKNOWN COMMAND TX" in reply

            os.close(first)
            first = None
            time.sleep(0.15)

            second = os.open(link, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            assert os.isatty(second)
            banner = _read_until(second, b"cmd:", timeout=args.timeout)
            assert b"VIRTUAL PTY TNC CONSOLE" in banner
            reply = _command(second, "MCOM", timeout=args.timeout)
            assert b"MCOM OFF" in reply
            reply = _command(second, "QUIT", timeout=args.timeout)
            assert b"BYE" in reply
            assert b"VIRTUAL PTY TNC CONSOLE" in reply
            reply = _command(second, "MCOM", timeout=args.timeout)
            assert b"MCOM OFF" in reply

            print("YWD1278_0E_P4_TARGET_PTY=PASS")
            print(f"PTY_SLAVE={slave}")
            print("PTY_SLAVE_PREFIX=/dev/pts/")
            print("PTY_SLAVE_MODE=0600")
            print("PTY_TERMios_API=PASS")
            print("STABLE_LINK_CREATE_RESOLVE=PASS")
            print("FROZEN_P1_COMMANDS=PASS")
            print("DETACH_REOPEN_STATE_RESET=PASS")
            print("QUIT_LOGICAL_SESSION_RESET=PASS")
            print("FUTURE_CONNECT_TX_COMMANDS_REJECTED=PASS")
            print("NETWORK_LISTENER_REQUIRED=NO")
            print("HARDWARE_SERIAL_OPENED=NO")
            print("MODEM_KISS_TX_PATH=ABSENT")
            print("TX_RF_HARDWARE_TEST_REQUIRED=NO")
        finally:
            if first is not None:
                os.close(first)
            if second is not None:
                os.close(second)
            stop.set()
            if thread is not None:
                thread.join(timeout=2.0)
            server.close()

        assert not os.path.lexists(link), "stable link was not removed on close"
        print("STABLE_LINK_CLEANUP=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
