#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import socket
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "stage_g_live_rx", ROOT / "tools/qualify_stage_g_live_rx.py"
)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def enc_addr(call: str, ssid: int, last: bool) -> bytes:
    call = call.upper().ljust(6)
    raw = bytearray((ord(ch) << 1) & 0xFE for ch in call)
    raw.append(0x60 | ((ssid & 0x0F) << 1) | (1 if last else 0))
    return bytes(raw)


class ExistingPiStageGTests(unittest.TestCase):
    def test_ax25_source_decode(self) -> None:
        frame = enc_addr("APRS", 0, False) + enc_addr("KJ6YWD", 9, True) + b"\x03\xf0hello"
        self.assertEqual(MOD.ax25_source(frame), "KJ6YWD-9")

    def test_kiss_unescape(self) -> None:
        payload = bytes([1, MOD.FESC, MOD.TFEND, 2, MOD.FESC, MOD.TFESC, 3])
        self.assertEqual(MOD.kiss_unescape(payload), bytes([1, MOD.FEND, 2, MOD.FESC, 3]))

    def test_recv_kiss_data_is_receive_only(self) -> None:
        left, right = socket.socketpair()
        try:
            frame = enc_addr("APRS", 0, False) + enc_addr("KJ6YWD", 0, True) + b"\x03\xf0test"
            wire = bytes([MOD.FEND, 0x00]) + frame + bytes([MOD.FEND])
            sender = threading.Thread(target=lambda: (time.sleep(0.02), right.sendall(wire)))
            sender.start()
            self.assertEqual(MOD.recv_kiss_data(left, 1.0), frame)
            sender.join(timeout=1.0)
            right.setblocking(False)
            with self.assertRaises(BlockingIOError):
                right.recv(1)
        finally:
            left.close(); right.close()

    def test_non_data_kiss_frame_is_ignored(self) -> None:
        left, right = socket.socketpair()
        try:
            frame = enc_addr("APRS", 0, False) + enc_addr("KJ6YWD", 0, True) + b"\x03\xf0test"
            right.sendall(bytes([MOD.FEND, 0x01, 0x7F, MOD.FEND, MOD.FEND, 0x00]) + frame + bytes([MOD.FEND]))
            self.assertEqual(MOD.recv_kiss_data(left, 1.0), frame)
        finally:
            left.close(); right.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
