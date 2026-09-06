#!/usr/bin/env python3
"""Host qualification for 0F-P9 persistent product TX configuration control."""

from __future__ import annotations

from pathlib import Path
import tempfile
import tomllib
import unittest

from ywd1278.install.tx_control import (
    ProductTXControlError,
    render_tx_state,
    validate_candidate,
)
from ywd1278.service.appliance import PRODUCT_TARGET


def config_text(*, frequency: float = 145.050, auto_flash: bool = False, forwarding: bool = False) -> str:
    return f'''[station]
callsign = "KJ6YWD"
ssid = 10

[hardware]
target = "{PRODUCT_TARGET}"

[radio]
device = "/dev/ttyAMA0"
frequency_mhz = {frequency}
tx_power = 64
tx_enabled = false

[packet]
baud = 1200
txdelay_ms = 300
persist = 63
slottime_ms = 100
paclen = 128
maxframe = 4
retry = 10

[kiss]
enabled = true
listen = "127.0.0.1"
port = 8001

[monitor]
enabled = false
log_frames = false

[beacon]
enabled = false
interval_seconds = 600
destination = "BEACON"
path = []
text = "YWD-1278"

[forwarding]
enabled = {'true' if forwarding else 'false'}
interval_seconds = 900
max_batch = 8

[firmware]
required_product = "YWD-1278"
allow_automatic_flash = {'true' if auto_flash else 'false'}
'''


class PersistentProductConverseP9Tests(unittest.TestCase):
    def test_enable_changes_only_qualified_power_and_tx_authority(self) -> None:
        before = config_text()
        after = render_tx_state(before, enabled=True)
        old = tomllib.loads(before)
        new = tomllib.loads(after)

        self.assertEqual(new["station"], old["station"])
        self.assertEqual(new["hardware"], old["hardware"])
        self.assertEqual(new["radio"]["device"], old["radio"]["device"])
        self.assertEqual(new["radio"]["frequency_mhz"], old["radio"]["frequency_mhz"])
        self.assertEqual(new["radio"]["tx_power"], 200)
        self.assertIs(new["radio"]["tx_enabled"], True)
        self.assertEqual(new["packet"], old["packet"])
        self.assertEqual(new["kiss"], old["kiss"])
        self.assertEqual(new["beacon"], old["beacon"])
        self.assertEqual(new["forwarding"], old["forwarding"])
        self.assertEqual(new["firmware"], old["firmware"])

    def test_disable_only_revokes_tx_authority(self) -> None:
        enabled = render_tx_state(config_text(), enabled=True)
        disabled = render_tx_state(enabled, enabled=False)
        old = tomllib.loads(enabled)
        new = tomllib.loads(disabled)
        self.assertEqual(new["radio"]["tx_power"], 200)
        self.assertIs(new["radio"]["tx_enabled"], False)
        old["radio"]["tx_enabled"] = False
        self.assertEqual(new, old)

    def test_enable_rejects_nonqualified_frequency(self) -> None:
        with self.assertRaisesRegex(ProductTXControlError, "145.050"):
            render_tx_state(config_text(frequency=144.390), enabled=True)

    def test_enable_rejects_automatic_flash_or_forwarding(self) -> None:
        with self.assertRaisesRegex(ProductTXControlError, "automatic firmware flash"):
            render_tx_state(config_text(auto_flash=True), enabled=True)
        with self.assertRaisesRegex(ProductTXControlError, "forwarding"):
            render_tx_state(config_text(forwarding=True), enabled=True)

    def test_candidate_runs_through_real_product_loaders(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.toml"
            path.write_text(render_tx_state(config_text(), enabled=True), encoding="utf-8")
            source, frequency_hz, power = validate_candidate(path, expect_enabled=True)
        self.assertEqual(source, "KJ6YWD-10")
        self.assertEqual(frequency_hz, 145_050_000)
        self.assertEqual(power, 200)

    def test_disable_remains_available_if_enable_only_constraints_are_wrong(self) -> None:
        text = config_text(frequency=144.390, auto_flash=True, forwarding=True)
        disabled = tomllib.loads(render_tx_state(text, enabled=False))
        self.assertIs(disabled["radio"]["tx_enabled"], False)
        self.assertEqual(disabled["radio"]["frequency_mhz"], 144.390)
        self.assertEqual(disabled["radio"]["tx_power"], 64)


if __name__ == "__main__":
    unittest.main(verbosity=2)
