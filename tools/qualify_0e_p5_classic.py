#!/usr/bin/env python3
"""Deterministic target-host smoke for 0E-P5 classic vocabulary over frozen P4 PTY."""

from __future__ import annotations

import argparse
import os
import select
import stat
import tempfile
import termios
import threading
import time
from pathlib import Path

from ywd1278.console.classic import make_classic_shell
from ywd1278.console.pty_serial import PTY_MODE, VirtualPTYTNC


def _read_until(fd: int, needle: bytes, *, timeout: float) -> bytes:
    deadline = time.monotonic() + timeout
    data = bytearray()
    while needle not in data:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(f"timeout waiting for {needle!r}: {bytes(data)!r}")
        readable, _, _ = select.select([fd], [], [], remaining)
        if not readable:
            continue
        chunk = os.read(fd, 4096)
        if chunk:
            data.extend(chunk)
    return bytes(data)


def _command(fd: int, command: str, *, timeout: float) -> bytes:
    os.write(fd, command.encode("ascii") + b"\r")
    return _read_until(fd, b"cmd:", timeout=timeout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Exercise 0E-P5 classic vocabulary through a real frozen P4 PTY"
    )
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args(argv)
    if not 0.1 <= args.timeout <= 10.0:
        raise SystemExit("--timeout must be between 0.1 and 10 seconds")

    with tempfile.TemporaryDirectory(prefix="ywd1278-p5-") as tmp:
        link = str(Path(tmp) / "tnc")
        server = VirtualPTYTNC(
            shell_factory=make_classic_shell,
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
                name="p5-target-qualification",
                daemon=True,
            )
            thread.start()

            first = os.open(link, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            assert os.isatty(first)
            termios.tcgetattr(first)
            banner = _read_until(first, b"cmd:", timeout=args.timeout)
            assert b"VIRTUAL PTY TNC CONSOLE" in banner

            reply = _command(first, "VER", timeout=args.timeout)
            assert b"YWD-1278 0.1.0-alpha0" in reply
            reply = _command(first, "MH", timeout=args.timeout)
            assert b"MHEARD UNAVAILABLE" in reply
            reply = _command(first, "DISP", timeout=args.timeout)
            assert b"DISPLAY MONITOR" in reply
            assert b"MCOM OFF" in reply
            assert b"MCON OFF" in reply
            assert b"MRPT ON" in reply

            reply = _command(first, "MCOM ON", timeout=args.timeout)
            assert b"MCOM ON" in reply
            reply = _command(first, "DISPLAY MONITOR", timeout=args.timeout)
            assert b"MCOM ON" in reply

            blocked = {
                "CONNECT KJ6YWD": b"OWNER=0G",
                "CONVERSE": b"OWNER=0F",
                "UNPROTO CQ": b"OWNER=0F",
                "BEACON EVERY 10": b"OWNER=0F",
                "TX hello": b"OWNER=LATER-TX-COMMAND",
                "XMITOK ON": b"OWNER=LATER-TX-ENABLE-CONTROL",
                "KISS ON": b"OWNER=LATER-KISS-MODE-CONTROL",
            }
            for command, marker in blocked.items():
                reply = _command(first, command, timeout=args.timeout)
                assert b"NOT AVAILABLE IN 0E-P5" in reply
                assert marker in reply

            reply = _command(first, "MHCLEAR", timeout=args.timeout)
            assert b"MHCLEAR DISABLED" in reply
            assert b"read-only MHEARD boundary" in reply

            for ambiguous in ("D", "C", "CON", "MCO", "UNP", "XMIT"):
                reply = _command(first, ambiguous, timeout=args.timeout)
                assert f"ERROR UNKNOWN COMMAND {ambiguous}".encode("ascii") in reply

            os.close(first)
            first = None
            time.sleep(0.15)

            second = os.open(link, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            banner = _read_until(second, b"cmd:", timeout=args.timeout)
            assert b"VIRTUAL PTY TNC CONSOLE" in banner
            reply = _command(second, "DISP", timeout=args.timeout)
            assert b"MCOM OFF" in reply

            print("YWD1278_0E_P5_TARGET_CLASSIC=PASS")
            print(f"PTY_SLAVE={slave}")
            print("PTY_SLAVE_MODE=0600")
            print("PTY_TERMIOS_API=PASS")
            print("SAFE_ALIASES=DISP_MH_VER_STAT_HEAL")
            print("DISPLAY_MONITOR=PASS")
            print("DETACH_REOPEN_STATE_RESET=PASS")
            print("AMBIGUOUS_ABBREVIATIONS=FAIL_CLOSED")
            print("CONNECT_CONVERSE_UNPROTO_BEACON=DEFERRED")
            print("TX_XMITOK_KISS=DEFERRED")
            print("MHCLEAR=DISABLED_READ_ONLY")
            print("FROZEN_P4_PTY_COMPOSITION=PASS")
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

        assert not os.path.lexists(link), "stable PTY link was not removed"
        print("STABLE_LINK_CLEANUP=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
