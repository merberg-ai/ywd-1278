#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
FROZEN = {
    # Existing physically/host-qualified product packet path.
    "src/ywd1278/service/appliance.py": "fa1b086d6d8fa40b537c002dbeec34fdc6532396",
    # Frozen 0I-P4b/P4a/P2/P1 mailbox components.
    "src/ywd1278/service/persistent_bbs_service.py": "b816e786de1ca3acaeb1201857bf36db2d008dcf",
    "src/ywd1278/node/persistent_bbs_runtime.py": "0c40aaf283142b71d16c9f30a1687865a98b197f",
    "src/ywd1278/node/classic_bbs.py": "e9ebd80b07f9e91cb6f57ca61c2a010b5e17f3fd",
    "src/ywd1278/node/persistent_mailbox.py": "f9e948ebc0da19ede88dfad97eddbf7eb15dc4fc",
    "src/ywd1278/service/node_mailbox_config.py": "a56d8981888ebffd1aa22d895d53db7326e9d6bc",
    # P4c2 production composition being qualified.
    "src/ywd1278/service/product_mailbox_console.py": "93c9a66be6b5d01d6bacfb70b2eef7b1189a9b6c",
    "src/ywd1278/daemon.py": "85471ccac9e26079c0265753054d54eb1753e191",
}


class PersistentBBSProductCompositionP4c2Contract(unittest.TestCase):
    def test_frozen_source_graph(self) -> None:
        for path, expected in FROZEN.items():
            with self.subTest(path=path):
                actual = subprocess.check_output(
                    ["git", "hash-object", path], cwd=ROOT, text=True
                ).strip()
                self.assertEqual(actual, expected)

    def test_daemon_uses_one_existing_product_backend_for_bbs_and_classic_tx(self) -> None:
        daemon = (ROOT / "src/ywd1278/daemon.py").read_text(encoding="utf-8")
        self.assertEqual(daemon.count("engine = ProductPacketEngine("), 1)
        self.assertIn("backend_getter=lambda: engine.backend", daemon)
        self.assertIn("submitter = make_product_backend_submitter(lambda: engine.backend)", daemon)
        self.assertIn("ProductPersistentBBSService(", daemon)
        self.assertIn("bbs_service.start()", daemon)
        self.assertIn("bbs_service.check_health()", daemon)
        self.assertIn("bbs_service.stop()", daemon)
        self.assertIn("mailbox_store_getter=(", daemon)
        self.assertIn("lambda: None if bbs_service is None else bbs_service.store", daemon)

    def test_bbs_service_only_subscribes_and_reenters_existing_kiss_data_admission(self) -> None:
        source = (ROOT / "src/ywd1278/service/persistent_bbs_service.py").read_text(encoding="utf-8")
        self.assertIn("backend.open_stream()", source)
        self.assertIn("self._backend.close_stream(self._live_queue)", source)
        self.assertIn("self._backend.reject_client_message(", source)
        self.assertIn("KISSMessage(port=0, command=DATA", source)
        self.assertIn("event.frame_no_fcs", source)
        self.assertIn("self._history_discarded = len(history)", source)

        forbidden = (
            "from ywd1278.modem",
            "from ywd1278.phy",
            "from ywd1278.tx",
            "TXModemOwner",
            "SustainedTNCRuntime",
            "ThreadSafeKISSDataAdmissionQueue",
            "ShadowChannelAccessAttempt",
            "ProductBeaconScheduler",
            "posix_serial",
            "/dev/tty",
            "flash",
            "option_byte",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_local_mbox_has_no_packet_submission_or_hardware_edge(self) -> None:
        source = (ROOT / "src/ywd1278/service/product_mailbox_console.py").read_text(encoding="utf-8")
        self.assertIn("ClassicBBSSession(", source)
        self.assertIn("PersistentMailboxStore", source)
        self.assertIn("/CMD", source)
        self.assertIn("COMMAND", source)
        self.assertIn("Ctrl-C", source)
        self.assertIn("BYE", source)
        for token in (
            "KISSMessage",
            "reject_client_message",
            "open_stream(",
            "TXModemOwner",
            "SustainedTNCRuntime",
            "ThreadSafeKISSDataAdmissionQueue",
            "submit_frame(",
            "from ywd1278.modem",
            "from ywd1278.tx",
            "/dev/tty",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_p4c2_does_not_add_a_bbs_retry_or_scheduler(self) -> None:
        bbs = (ROOT / "src/ywd1278/service/persistent_bbs_service.py").read_text(encoding="utf-8")
        mailbox_console = (ROOT / "src/ywd1278/service/product_mailbox_console.py").read_text(encoding="utf-8")
        combined = bbs + "\n" + mailbox_console
        for token in (
            "retry_queue",
            "retry_count",
            "schedule_at",
            "sched.scheduler",
            "ProductBeaconScheduler",
            "Timer(",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, combined)


if __name__ == "__main__":
    unittest.main(verbosity=2)
