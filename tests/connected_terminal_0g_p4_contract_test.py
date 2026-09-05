#!/usr/bin/env python3
"""Architecture and preservation contract for host-only 0G-P4."""

from __future__ import annotations

import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FROZEN = {
    "src/ywd1278/link/timed_link.py": "229b93ccc9ae2745ca1aae48685ced8712f5d433",
    "tests/timed_link_0g_p3_test.py": "dc8a43f1a4d2dbb1667413741fde940867d6b073",
    "tests/timed_link_0g_p3_contract_test.py": "0d4983721c87d5b18b82fcb552cc25689a15afe7",
    "src/ywd1278/link/data_link.py": "40e9fde0df520d43938c12e817c420588d1e5463",
    "src/ywd1278/daemon.py": "f5ff3c6d9feea4c020d84d13795cfcca40ef186f",
    "firmware/qualification/0f-p5e-id-target-pi.json": "9589981794c215eb60a2630b2349bb44702559ad",
}


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class ConnectedTerminalP4ContractTests(unittest.TestCase):
    def test_p3_p2_and_physical_lineage_is_byte_frozen(self) -> None:
        for relative, expected in FROZEN.items():
            with self.subTest(path=relative):
                self.assertEqual(git_blob(ROOT / relative), expected)

    def test_surface_is_single_session_bounded_and_explicit(self) -> None:
        text = (ROOT / "src/ywd1278/link/terminal_session.py").read_text(encoding="utf-8")
        for marker in (
            "MAX_TERMINAL_LINE_BYTES = 256",
            "class ConnectedTerminalSession:",
            '"CONNECT DEST       begin one direct modulo-8 link"',
            '"DISCONNECT         request orderly link release"',
            '"CSTATUS            show this session\'s link status"',
            '"CONVERSE           return to connected text mode"',
            'if normalized.strip().upper() == "COMMAND"',
            'return self._reject(f"connected text exceeds PACLEN {self._paclen}")',
            "def handle_frame(self, frame_no_fcs: bytes, *, now: float)",
            "def poll(self, *, now: float)",
        ):
            self.assertIn(marker, text)

    def test_p4_has_no_transport_dispatch_runtime_or_shared_registry(self) -> None:
        text = (ROOT / "src/ywd1278/link/terminal_session.py").read_text(encoding="utf-8")
        for forbidden in (
            "threading", "time.sleep(", "socket", "listen(", "accept(",
            "KISSMessage(", "ProductBeaconScheduler(", "TXModemOwner(",
            "PosixSerialTransport(", "RPi.GPIO", "subprocess", "open(",
            "sendall(", "write(", "submitter", "sessions =", "session_registry",
        ):
            self.assertNotIn(forbidden, text)

    def test_existing_product_and_console_owners_do_not_import_p4(self) -> None:
        for relative in (
            "src/ywd1278/daemon.py",
            "src/ywd1278/service/appliance.py",
            "src/ywd1278/service/classic_tx_console.py",
            "src/ywd1278/service/product_id_console.py",
            "src/ywd1278/console/classic.py",
            "src/ywd1278/console/classic_tx.py",
            "src/ywd1278/console/telnet.py",
            "src/ywd1278/console/pty_serial.py",
        ):
            self.assertNotIn("terminal_session", (ROOT / relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
