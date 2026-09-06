#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from ywd1278.service.forwarding_config import (
    ProductForwardingConfigurationError,
    load_product_forwarding_config,
)

ROOT = Path(__file__).resolve().parents[1]


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


class P11ForwardingPlumbingContractTests(unittest.TestCase):
    def test_frozen_p8_p9_p10_lineage_is_byte_exact(self) -> None:
        self.assertEqual(
            git_blob(ROOT / "src/ywd1278/node/forwarding_integration.py"),
            "263b5583d473a5673e6dfa60978804055197f676",
        )
        self.assertEqual(
            git_blob(ROOT / "src/ywd1278/node/linbpq_dialogue.py"),
            "6c3776b7ffe92cb6216c682fc7c12081c57d12aa",
        )
        self.assertEqual(
            git_blob(ROOT / "tools/qualify_0h_p10_linbpq_delivery_r3.py"),
            "c4399d6be22d00b4bee5d9731cea34d38ca1b7a0",
        )
        self.assertEqual(
            git_blob(ROOT / "firmware/qualification/0h-p10-linbpq-delivery-target-pi.json"),
            "617d891bce3b106a1744a2418b6788e92e16659c",
        )

    def test_example_config_keeps_forwarding_disabled(self) -> None:
        text = (ROOT / "config/ywd-1278.example.toml").read_text(encoding="utf-8")
        self.assertIn("[forwarding]", text)
        section = text.split("[forwarding]", 1)[1].split("[", 1)[0]
        self.assertIn("enabled = false", section)

    def test_product_gate_refuses_enabled_true(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text(
                "[forwarding]\nenabled=true\ninterval_seconds=900\nmax_batch=8\n",
                encoding="ascii",
            )
            with self.assertRaises(ProductForwardingConfigurationError):
                load_product_forwarding_config(path)

    def test_daemon_knows_config_but_does_not_wire_coordinator(self) -> None:
        text = (ROOT / "src/ywd1278/daemon.py").read_text(encoding="utf-8")
        self.assertIn("load_product_forwarding_config", text)
        self.assertIn("FORWARDING=DISABLED", text)
        self.assertNotIn("HostForwardingCoordinator", text)
        self.assertNotIn("forwarding_coordinator", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
