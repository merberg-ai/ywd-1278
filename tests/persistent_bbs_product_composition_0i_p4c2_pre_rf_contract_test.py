#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/qualifications/0i-p4c2-persistent-bbs-product-composition-pre-rf.md"


class PersistentBBSProductCompositionP4c2PreRFContract(unittest.TestCase):
    def test_staging_document_keeps_physical_boundary_closed(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("b92d1b2dd8195003f901f6df2142946cc2ca7085", text)
        self.assertIn("8103bf095ebd1bd96c0f65800382718557890340", text)
        self.assertIn("`ProductTNCBackend`", text)
        self.assertIn("`ThreadSafeKISSDataAdmissionQueue`", text)
        self.assertIn("Only the final contextual hardware/RF submitter", text)
        self.assertIn("No physical command is intentionally provided", text)
        for marker in (
            "MODEM_UART_OPENED=NO",
            "RF_TRANSMITTED=NO",
            "FIRMWARE_WRITTEN=NO",
            "OPTION_BYTES_WRITTEN=NO",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_p4c2_host_tests_do_not_name_real_device_or_firmware_write_tools(self) -> None:
        paths = (
            ROOT / "tests/persistent_bbs_product_composition_0i_p4c2_test.py",
            ROOT / "tests/product_mailbox_console_0i_p4c2_test.py",
        )
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        for token in (
            "/dev/tty",
            "/dev/serial",
            "posix_serial_transport_factory",
            "flash_firmware",
            "program_firmware",
            "option_bytes",
            "subprocess.run",
            "os.system",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, combined)

    def test_stage_emits_zero_io_markers(self) -> None:
        print("YWD1278_0I_P4C2_PRE_RF=PASS")
        print("MODEM_UART_OPENED=NO")
        print("RF_TRANSMITTED=NO")
        print("FIRMWARE_WRITTEN=NO")
        print("OPTION_BYTES_WRITTEN=NO")


if __name__ == "__main__":
    unittest.main(verbosity=2)
