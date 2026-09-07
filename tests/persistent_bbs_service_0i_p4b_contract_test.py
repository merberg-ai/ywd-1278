#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
P4B_CHECKPOINT = "8103bf095ebd1bd96c0f65800382718557890340"
FROZEN = {
    "src/ywd1278/node/persistent_bbs_runtime.py": "0c40aaf283142b71d16c9f30a1687865a98b197f",
    "src/ywd1278/node/classic_bbs.py": "e9ebd80b07f9e91cb6f57ca61c2a010b5e17f3fd",
    "src/ywd1278/node/persistent_mailbox.py": "f9e948ebc0da19ede88dfad97eddbf7eb15dc4fc",
    "src/ywd1278/service/node_mailbox_config.py": "a56d8981888ebffd1aa22d895d53db7326e9d6bc",
}


def historical_text(commit: str, path: str) -> str:
    return subprocess.check_output(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT,
        text=True,
    )


class PersistentBBSServiceP4bContractTests(unittest.TestCase):
    def test_frozen_dependencies(self) -> None:
        for path, expected in FROZEN.items():
            with self.subTest(path=path):
                actual = subprocess.check_output(
                    ["git", "hash-object", path], cwd=ROOT, text=True
                ).strip()
                self.assertEqual(actual, expected)

    def test_exact_product_backend_seam_is_used(self) -> None:
        source = (ROOT / "src/ywd1278/service/persistent_bbs_service.py").read_text(encoding="utf-8")
        self.assertIn("backend.open_stream()", source)
        self.assertIn("self._backend.close_stream(self._live_queue)", source)
        self.assertIn("self._backend.reject_client_message(", source)
        self.assertIn("KISSMessage(port=0, command=DATA", source)
        self.assertIn("self._history_discarded = len(history)", source)

    def test_no_second_modem_csma_or_rf_implementation(self) -> None:
        source = (ROOT / "src/ywd1278/service/persistent_bbs_service.py").read_text(encoding="utf-8")
        for token in (
            "from ywd1278.modem",
            "from ywd1278.phy",
            "from ywd1278.tx",
            "TXModemOwner",
            "ShadowChannelAccessAttempt",
            "/dev/tty",
            "TX_TONES",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_p4b_checkpoint_was_still_not_daemon_wired(self) -> None:
        daemon = historical_text(P4B_CHECKPOINT, "src/ywd1278/daemon.py")
        self.assertNotIn("ProductPersistentBBSService", daemon)
        self.assertNotIn("persistent_bbs_service", daemon)


if __name__ == "__main__":
    unittest.main(verbosity=2)
