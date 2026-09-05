#!/usr/bin/env python3
"""Architecture/preservation contract for 0F classic UI transmission."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]

FROZEN = {
    "src/ywd1278/console/local.py": "9fed5416ca9123811413f4ef284abff0006a48dd",
    "src/ywd1278/console/classic.py": "4d6dfd5d439fb5dfd6ff586c2a47c37724381b2e",
    "src/ywd1278/console/telnet.py": "d15669eb61f2afdf4d0d177191124ef8f13713e0",
    "src/ywd1278/console/pty_serial.py": "c0ba2a3278ac1e790bf383fc12a220ae327255ba",
    "src/ywd1278/ax25/codec.py": "866a500d9f3a5d3fc80f6918d07ff83a6672ad64",
    "src/ywd1278/kiss/tx_path.py": "44f4b6c0bddd6ac0977646ac417e448c9a1398ea",
    "src/ywd1278/service/appliance.py": "fa1b086d6d8fa40b537c002dbeec34fdc6532396",
    "src/ywd1278/service/classic_console.py": "7763a0973f81b69cbdd91de375aaac09d4b0ff77",
}

NEW = (
    "src/ywd1278/console/classic_tx.py",
    "src/ywd1278/service/classic_tx_console.py",
)

FORBIDDEN_IMPORT_PREFIXES = (
    "ywd1278.modem",
    "ywd1278.phy",
    "ywd1278.tx.half_duplex",
    "ywd1278.tx.contextual",
    "ywd1278.install",
)


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


class ClassicTX0FContractTests(unittest.TestCase):
    def test_qualified_lower_boundaries_are_byte_frozen(self) -> None:
        for relative, expected in FROZEN.items():
            with self.subTest(path=relative):
                self.assertEqual(git_blob(ROOT / relative), expected)

    def test_new_0f_layers_do_not_own_modem_phy_or_firmware(self) -> None:
        for relative in NEW:
            with self.subTest(path=relative):
                names = imports(ROOT / relative)
                for name in names:
                    self.assertFalse(
                        any(name == prefix or name.startswith(prefix + ".") for prefix in FORBIDDEN_IMPORT_PREFIXES),
                        f"0F layer imports forbidden capability owner {name}",
                    )
                text = (ROOT / relative).read_text(encoding="utf-8")
                for token in ("stm32flash", "hat_control", "GPIO", "RF_TX_TONES"):
                    self.assertNotIn(token, text)

    def test_console_layer_builds_no_fcs_and_has_no_retry_loop(self) -> None:
        text = (ROOT / "src/ywd1278/console/classic_tx.py").read_text(encoding="utf-8")
        self.assertIn("include_fcs=False", text)
        self.assertIn("COMMAND_MODE_ESCAPE = \"COMMAND\"", text)
        self.assertNotIn("while True", text)
        self.assertNotIn("sleep(", text)
        self.assertNotIn("Timer(", text)

    def test_product_adapter_reuses_kiss_data_admission(self) -> None:
        text = (ROOT / "src/ywd1278/service/classic_tx_console.py").read_text(encoding="utf-8")
        self.assertIn("KISSMessage(port=0, command=DATA", text)
        self.assertIn("reject_client_message", text)
        self.assertNotIn("KISSDataAdmissionQueue(", text)
        self.assertNotIn("ThreadSafeKISSDataAdmissionQueue(", text)
        self.assertNotIn("TXModemOwner(", text)
        self.assertNotIn("ShadowChannelAccessAttempt(", text)

    def test_beacon_and_connected_mode_remain_outside_p1_p3(self) -> None:
        text = (ROOT / "src/ywd1278/console/classic_tx.py").read_text(encoding="utf-8")
        self.assertIn('command in ("BEACON", "BTEXT", "ID")', text)
        self.assertIn("OWNER=0F-P5", text)
        # CONNECT is deliberately not implemented by the 0F layer and therefore
        # continues falling through to frozen P5/0G ownership.
        self.assertNotIn('command == "CONNECT"', text)

    def test_final_appliance_evidence_remains_present(self) -> None:
        seal = ROOT / "firmware/qualification/product-fresh-install-appliance-qualified.json"
        self.assertTrue(seal.is_file())
        contract = ROOT / "tests/product_fresh_install_appliance_qualified_contract_test.py"
        self.assertTrue(contract.is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
