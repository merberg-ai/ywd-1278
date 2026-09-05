#!/usr/bin/env python3
from __future__ import annotations
import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
FROZEN = {
    "src/ywd1278/link/session_manager.py": "5ee738b10de3ec2b32d44bc7c810598dee33b3be",
    "firmware/qualification/0g-p6-connected-target-pi.json": "5050477cf15fbc8638adb3d793ebc9fc9ad63cbe",
}

def blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()

class NodeCommandsP1ContractTests(unittest.TestCase):
    def test_connected_and_physical_lineage_is_frozen(self) -> None:
        for path, expected in FROZEN.items():
            self.assertEqual(blob(ROOT / path), expected)

    def test_node_layer_is_bounded_and_inert(self) -> None:
        text = (ROOT / "src/ywd1278/node/commands.py").read_text(encoding="utf-8")
        for marker in ("MAX_NODE_COMMAND_BYTES = 128", "MAX_NODE_BUFFER_BYTES = 256", "class NodeCommandSession", '"HELP"', '"INFO"', '"VERSION"', '"BYE"'):
            self.assertIn(marker, text)
        for forbidden in ("sqlite", "socket", "threading", "subprocess", "open(", "TXModemOwner", "session_manager"):
            self.assertNotIn(forbidden, text)

    def test_product_owners_do_not_import_node(self) -> None:
        for path in ("src/ywd1278/daemon.py", "src/ywd1278/service/appliance.py", "src/ywd1278/link/session_manager.py"):
            self.assertNotIn("ywd1278.node", (ROOT / path).read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main(verbosity=2)
