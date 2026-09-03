#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.ax25 import Address, build_ui_frame  # noqa: E402
from ywd1278.modem import protocol  # noqa: E402
from ywd1278.tx import (  # noqa: E402
    HDLC_FLAG_SECONDS,
    KISS_TXDELAY_DEFAULT,
    TXBrokerFrameRejected,
    TXDelayBroker,
    resolve_txdelay,
)

P5_PACKED_SHA256 = "30718ba5a4368e82bab69e6343f95c7e226cd08426844ed328ad8c52fbfd750e"

VIA_YWDNOD_VECTORS = {
    30: {
        "info": b"YWD-1278 P5 TXDELAY 300MS 1/2",
        "frame_bytes": 54,
        "frame_sha256": "d70b96a24f100e148008a495a808485e5bdc56bf7d408f15b73533e54ad46ee9",
        "selectors": 817,
        "packed_bytes": 103,
        "packed_sha256": "534383e423bdf4f71cdafa3da9d1bbdb0bfc165e1a14d8fbd0fd676df15be145",
        "generated_samples": 13072,
    },
    50: {
        "info": b"YWD-1278 P5 TXDELAY 500MS 2/2",
        "frame_bytes": 54,
        "frame_sha256": "27cda8b62652f5bc855a75b0c41e0fe6b1168ee059be4a01c097f4bcef171253",
        "selectors": 1057,
        "packed_bytes": 133,
        "packed_sha256": "f0c9b7c1e08fb9cf512fa6afa7d57b84e33f42af226e4d4957b00a6ca174cb22",
        "generated_samples": 16912,
    },
}


def p5_reference_frame() -> bytes:
    return build_ui_frame(
        source=Address.parse("KJ6YWD-10"),
        destination=Address.parse("APYWD1"),
        info=b"AX25-5B KISS TX TEST",
        include_fcs=True,
    )


def ywdnod_frame(units: int) -> bytes:
    vector = VIA_YWDNOD_VECTORS[units]
    return build_ui_frame(
        source=Address.parse("KJ6YWD-10"),
        destination=Address.parse("YWD5TD"),
        path=(Address.parse("YWDNOD"),),
        info=vector["info"],
        include_fcs=True,
    )


class FakeOwner:
    def __init__(self) -> None:
        self.status_calls = 0
        self.tx_calls: list[tuple[int, bytes]] = []

    def rf_status(self, *, timeout=None):  # type: ignore[no-untyped-def]
        self.status_calls += 1
        return protocol.RFStatus(flags=0x08, remaining_selectors=0, mode=0)

    def transmit_selector_burst(
        self,
        selector_count: int,
        packed_selectors: bytes,
        *,
        timeout=None,  # type: ignore[no-untyped-def]
    ) -> None:
        self.tx_calls.append((selector_count, bytes(packed_selectors)))


class TXDelayTests(unittest.TestCase):
    def test_kiss_byte_bounds_and_whole_flag_rounding(self) -> None:
        expected = {
            0: (1, 0.0, 1 / 150.0),
            1: (2, 0.010, 2 / 150.0),
            2: (3, 0.020, 0.020),
            30: (45, 0.300, 0.300),
            31: (47, 0.310, 47 / 150.0),
            50: (75, 0.500, 0.500),
            255: (383, 2.550, 383 / 150.0),
        }
        for units, (flags, requested, effective) in expected.items():
            with self.subTest(units=units):
                profile = resolve_txdelay(units)
                self.assertEqual(profile.units, units)
                self.assertEqual(profile.pre_flags, flags)
                self.assertAlmostEqual(profile.requested_seconds, requested)
                self.assertAlmostEqual(profile.effective_seconds, effective)
                self.assertGreaterEqual(profile.effective_seconds, profile.requested_seconds)
                self.assertLessEqual(profile.rounding_overrun_seconds, HDLC_FLAG_SECONDS + 1e-12)

        for invalid in (-1, 256):
            with self.assertRaises(ValueError):
                resolve_txdelay(invalid)
        for invalid in (True, 30.0, "30"):
            with self.assertRaises(TypeError):
                resolve_txdelay(invalid)  # type: ignore[arg-type]

    def test_default_profile_preserves_frozen_p5_serializer_exactly(self) -> None:
        owner = FakeOwner()
        broker = TXDelayBroker(owner, transmit_enabled=True)
        self.assertEqual(KISS_TXDELAY_DEFAULT, 30)
        self.assertEqual(broker.txdelay_profile.pre_flags, 45)
        broker.start()
        try:
            receipt = broker.submit_frame(p5_reference_frame())
        finally:
            broker.stop()
        self.assertEqual(receipt.frame_bytes, 38)
        self.assertEqual(receipt.selector_count, 691)
        self.assertEqual(receipt.packed_selector_bytes, 87)
        self.assertEqual(receipt.packed_selector_sha256, P5_PACKED_SHA256)
        self.assertEqual(owner.status_calls, 1)
        self.assertEqual(len(owner.tx_calls), 1)

    def test_locked_ywdnod_vectors_change_only_txdelay_preamble(self) -> None:
        for units in (30, 50):
            with self.subTest(units=units):
                owner = FakeOwner()
                broker = TXDelayBroker(owner, txdelay_units=units, transmit_enabled=True)
                broker.start()
                try:
                    receipt = broker.submit_frame(ywdnod_frame(units))
                finally:
                    broker.stop()
                vector = VIA_YWDNOD_VECTORS[units]
                self.assertEqual(receipt.frame_bytes, vector["frame_bytes"])
                self.assertEqual(receipt.frame_sha256, vector["frame_sha256"])
                self.assertEqual(receipt.selector_count, vector["selectors"])
                self.assertEqual(receipt.packed_selector_bytes, vector["packed_bytes"])
                self.assertEqual(receipt.packed_selector_sha256, vector["packed_sha256"])
                self.assertEqual(receipt.selector_count * 16, vector["generated_samples"])
                self.assertEqual(len(owner.tx_calls), 1)

    def test_excessive_txdelay_fails_selector_limit_before_modem(self) -> None:
        owner = FakeOwner()
        broker = TXDelayBroker(owner, txdelay_units=255, transmit_enabled=True)
        broker.start()
        try:
            with self.assertRaisesRegex(TXBrokerFrameRejected, "selector limit"):
                broker.submit_frame(p5_reference_frame())
        finally:
            broker.stop()
        self.assertEqual(owner.status_calls, 0)
        self.assertEqual(owner.tx_calls, [])

    def test_profile_is_construction_time_only(self) -> None:
        broker = TXDelayBroker(FakeOwner(), txdelay_units=50)
        self.assertEqual(broker.txdelay_profile.units, 50)
        self.assertFalse(hasattr(broker, "set_txdelay"))
        with self.assertRaises(Exception):
            broker.txdelay_profile.units = 30  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
