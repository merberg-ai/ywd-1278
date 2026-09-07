#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs/qualifications/0i-p4c2-persistent-bbs-product-composition-host-qualified-2026-09-07.md"
RECORD_BLOB = "a216099ebaea512363b492cb024f36088dd721b6"
CANDIDATE = "c90c81426ab09ce60587a236a093fb5c5bddfa41"
CANDIDATE_TREE = "67e579f982135b56f1baa94d8b9ca0ae16621912"
CI_RUN = "34121711854"

FROZEN = {
    "src/ywd1278/daemon.py": "85471ccac9e26079c0265753054d54eb1753e191",
    "src/ywd1278/service/product_mailbox_console.py": "93c9a66be6b5d01d6bacfb70b2eef7b1189a9b6c",
    "src/ywd1278/service/appliance.py": "fa1b086d6d8fa40b537c002dbeec34fdc6532396",
    "src/ywd1278/service/persistent_bbs_service.py": "b816e786de1ca3acaeb1201857bf36db2d008dcf",
    "src/ywd1278/node/persistent_bbs_runtime.py": "0c40aaf283142b71d16c9f30a1687865a98b197f",
    "src/ywd1278/node/classic_bbs.py": "e9ebd80b07f9e91cb6f57ca61c2a010b5e17f3fd",
    "src/ywd1278/node/persistent_mailbox.py": "f9e948ebc0da19ede88dfad97eddbf7eb15dc4fc",
    "src/ywd1278/service/node_mailbox_config.py": "a56d8981888ebffd1aa22d895d53db7326e9d6bc",
    "tests/persistent_bbs_product_composition_0i_p4c2_test.py": "10b8bf588a23ee797bcff53eaee3909c06853cb4",
    "tests/persistent_bbs_product_composition_0i_p4c2_contract_test.py": "2816e42a930a064d223924b2f165a1b6fb510e33",
    "docs/qualifications/0i-p4c2-persistent-bbs-product-composition-pre-rf.md": "7b8edc5483f32735ebe0dd1be2b81832b3a6d6f1",
    "tests/persistent_bbs_product_composition_0i_p4c2_pre_rf_contract_test.py": "04ed7b7ed7fb226f02ff923baa6010272ab0d668",
}


class PersistentBBSProductCompositionP4c2QualificationContract(unittest.TestCase):
    def hash_object(self, path: str) -> str:
        return subprocess.check_output(
            ["git", "hash-object", path], cwd=ROOT, text=True
        ).strip()

    def test_host_qualification_record_is_frozen(self) -> None:
        self.assertEqual(self.hash_object(str(RECORD.relative_to(ROOT))), RECORD_BLOB)

    def test_qualified_runtime_and_evidence_blobs_remain_exact(self) -> None:
        for path, expected in FROZEN.items():
            with self.subTest(path=path):
                self.assertEqual(self.hash_object(path), expected)

    def test_record_pins_candidate_tree_and_green_exact_tip_ci(self) -> None:
        text = RECORD.read_text(encoding="utf-8")
        for token in (
            "b92d1b2dd8195003f901f6df2142946cc2ca7085",
            "8103bf095ebd1bd96c0f65800382718557890340",
            CANDIDATE,
            CANDIDATE_TREE,
            CI_RUN,
            "0i-p4c2-persistent-bbs-product-composition-ci",
            "result: PASS",
        ):
            with self.subTest(token=token):
                self.assertIn(token, text)

    def test_record_preserves_local_mbox_and_real_backend_boundary(self) -> None:
        text = RECORD.read_text(encoding="utf-8")
        for token in (
            "`MBOX`",
            "`/CMD`",
            "`COMMAND`",
            "raw Ctrl-C",
            "`BYE`",
            "actual `ProductTNCBackend`",
            "`ThreadSafeKISSDataAdmissionQueue`",
            "same `PersistentMailboxStore` object",
            "application-level TX retry",
        ):
            with self.subTest(token=token):
                self.assertIn(token, text)

    def test_record_explicitly_closes_physical_boundary(self) -> None:
        text = RECORD.read_text(encoding="utf-8")
        self.assertIn("This qualification was host-only", text)
        self.assertIn("No physical test command is authorized or supplied", text)
        for marker in (
            "MODEM_UART_OPENED=NO",
            "RF_TRANSMITTED=NO",
            "FIRMWARE_WRITTEN=NO",
            "OPTION_BYTES_WRITTEN=NO",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

        print("YWD1278_0I_P4C2_HOST_QUALIFICATION_EVIDENCE=PASS")
        print("TARGET_PI_TOUCHED=NO")
        print("MODEM_UART_OPENED=NO")
        print("RF_TRANSMITTED=NO")
        print("FIRMWARE_WRITTEN=NO")
        print("OPTION_BYTES_WRITTEN=NO")


if __name__ == "__main__":
    unittest.main(verbosity=2)
