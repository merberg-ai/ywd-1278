#!/usr/bin/env python3
"""Architecture and preservation contract for host-only 0G-P5."""

from __future__ import annotations

import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FROZEN = {
    "src/ywd1278/link/terminal_session.py": "60b33b1d145d3770a37142811d71d7cddcf5ef11",
    "tests/connected_terminal_0g_p4_test.py": "46c2920c907a32352bb442f37b9dacbb4596c72e",
    "tests/connected_terminal_0g_p4_contract_test.py": "846f29bbf510c83009bf6e4074b1166ecd28ce84",
    "src/ywd1278/link/timed_link.py": "229b93ccc9ae2745ca1aae48685ced8712f5d433",
    "src/ywd1278/daemon.py": "f5ff3c6d9feea4c020d84d13795cfcca40ef186f",
    "firmware/qualification/0f-p5e-id-target-pi.json": "9589981794c215eb60a2630b2349bb44702559ad",
}


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class ConnectedSessionsP5ContractTests(unittest.TestCase):
    def test_p4_p3_and_physical_lineage_is_byte_frozen(self) -> None:
        for relative, expected in FROZEN.items():
            with self.subTest(path=relative):
                self.assertEqual(git_blob(ROOT / relative), expected)

    def test_policy_has_one_bounded_exclusive_owner(self) -> None:
        text = (ROOT / "src/ywd1278/link/session_manager.py").read_text(encoding="utf-8")
        for marker in (
            "MAX_CONNECTED_TERMINAL_SESSIONS = 8",
            "class ConnectedSessionManager:",
            "self._owner: str | None = None",
            "self._pending_close: str | None = None",
            "connected link owned by session",
            "session limit reached",
            "owner close awaiting release",
            "def handle_frame(self, frame_no_fcs: bytes, *, now: float)",
            "def poll(self, *, now: float)",
        ):
            self.assertIn(marker, text)

    def test_p5_has_no_transport_thread_dispatch_or_hardware_owner(self) -> None:
        text = (ROOT / "src/ywd1278/link/session_manager.py").read_text(encoding="utf-8")
        for forbidden in (
            "threading", "time.sleep(", "socket", "listen(", "accept(",
            "KISSMessage(", "ProductBeaconScheduler(", "TXModemOwner(",
            "PosixSerialTransport(", "RPi.GPIO", "subprocess", "open(",
            "sendall(", "write(", "submitter",
        ):
            self.assertNotIn(forbidden, text)

    def test_existing_runtime_and_transport_owners_do_not_import_p5(self) -> None:
        for relative in (
            "src/ywd1278/daemon.py", "src/ywd1278/service/appliance.py",
            "src/ywd1278/service/classic_tx_console.py",
            "src/ywd1278/console/telnet.py", "src/ywd1278/console/lan_telnet.py",
            "src/ywd1278/console/pty_serial.py", "src/ywd1278/kiss/sustained.py",
        ):
            self.assertNotIn("session_manager", (ROOT / relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
