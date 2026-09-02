#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import pathlib
import sys
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.ax25 import Address, build_ui_frame  # noqa: E402
from ywd1278.modem import protocol  # noqa: E402
from ywd1278.modem.tx_owner import TXModemOwner  # noqa: E402
from ywd1278.tx import (  # noqa: E402
    TXBroker,
    TXBrokerBusy,
    TXBrokerDisabled,
    TXBrokerFrameRejected,
    TXBrokerQueueFull,
)


P5_PACKED_SHA256 = "30718ba5a4368e82bab69e6343f95c7e226cd08426844ed328ad8c52fbfd750e"


def p5_reference_frame() -> bytes:
    return build_ui_frame(
        source=Address.parse("KJ6YWD-10"),
        destination=Address.parse("APYWD1"),
        info=b"AX25-5B KISS TX TEST",
        include_fcs=True,
    )


def idle_rf_status_response() -> bytes:
    return protocol.build_frame(
        protocol.YWD_RF,
        bytes((protocol.RF_GET_STATUS, 1, 0x08, 0, 0, 0)),
    )


class ThreadBoundTXTransport:
    """Fake wire transport that enforces the inherited one-owner-thread rule."""

    def __init__(self) -> None:
        self.owner_thread_id = threading.get_ident()
        self.call_thread_ids: list[int] = []
        self.requests: list[bytes] = []
        self.close_thread_id: int | None = None

    def _assert_owner(self) -> None:
        if threading.get_ident() != self.owner_thread_id:
            raise RuntimeError("TX transport accessed outside modem-owner thread")

    def transact(self, request: bytes, *, timeout: float) -> bytes:
        self._assert_owner()
        self.call_thread_ids.append(threading.get_ident())
        self.requests.append(request)
        frame = protocol.parse_frame(request)
        if frame.command != protocol.YWD_RF:
            raise AssertionError(f"unexpected command: {request.hex()}")
        if frame.payload == bytes((protocol.RF_GET_STATUS,)):
            return idle_rf_status_response()
        if frame.payload and frame.payload[0] == protocol.RF_TX_TONES:
            return protocol.ack_for(protocol.YWD_RF)
        raise AssertionError(f"unexpected YWD_RF request: {request.hex()}")

    def close(self) -> None:
        self._assert_owner()
        self.close_thread_id = threading.get_ident()


class DirectFakeOwner:
    """Broker-facing fake used to force queue and busy edge cases."""

    def __init__(
        self,
        *,
        block_event: threading.Event | None = None,
        busy: bool = False,
    ) -> None:
        self.block_event = block_event
        self.busy = busy
        self.calls: list[tuple[int, bytes]] = []
        self.status_calls = 0
        self._block_once = block_event is not None

    def rf_status(self, *, timeout: float | None = None) -> protocol.RFStatus:
        self.status_calls += 1
        return protocol.RFStatus(
            flags=0x08,
            remaining_selectors=17 if self.busy else 0,
            mode=0,
        )

    def transmit_selector_burst(
        self,
        selector_count: int,
        packed_selectors: bytes,
        *,
        timeout: float | None = None,
    ) -> None:
        self.calls.append((selector_count, bytes(packed_selectors)))
        if self._block_once:
            self._block_once = False
            assert self.block_event is not None
            if not self.block_event.wait(timeout=2.0):
                raise TimeoutError("test TX block was not released")


class TXBrokerTests(unittest.TestCase):
    def test_default_is_hard_disabled(self) -> None:
        owner = DirectFakeOwner()
        broker = TXBroker(owner)
        broker.start()
        try:
            with self.assertRaises(TXBrokerDisabled):
                broker.submit_frame(p5_reference_frame())
            self.assertEqual(owner.status_calls, 0)
            self.assertEqual(owner.calls, [])
            self.assertFalse(broker.snapshot.transmit_enabled)
        finally:
            broker.stop()

    def test_p5_reference_frame_reaches_single_owner_bit_exact(self) -> None:
        created: list[ThreadBoundTXTransport] = []

        def factory() -> ThreadBoundTXTransport:
            transport = ThreadBoundTXTransport()
            created.append(transport)
            return transport

        owner = TXModemOwner(factory, queue_capacity=4)
        owner.start()
        broker = TXBroker(owner, transmit_enabled=True, queue_capacity=2)
        broker.start()
        try:
            receipt = broker.submit_frame(p5_reference_frame())
            self.assertEqual(receipt.frame_bytes, 38)
            self.assertEqual(receipt.selector_count, 691)
            self.assertEqual(receipt.packed_selector_bytes, 87)
            self.assertEqual(receipt.packed_selector_sha256, P5_PACKED_SHA256)
            self.assertAlmostEqual(receipt.nominal_duration_seconds, 691 / 1200.0)

            self.assertEqual(len(created), 1)
            fake = created[0]
            self.assertEqual(len(fake.requests), 2)
            self.assertEqual(fake.requests[0], protocol.rf_status_request())

            tx = protocol.parse_frame(fake.requests[1], expected_command=protocol.YWD_RF)
            self.assertEqual(tx.payload[0], protocol.RF_TX_TONES)
            selector_count = tx.payload[1] | (tx.payload[2] << 8)
            packed = tx.payload[3:]
            self.assertEqual(selector_count, 691)
            self.assertEqual(hashlib.sha256(packed).hexdigest(), P5_PACKED_SHA256)

            self.assertEqual(set(fake.call_thread_ids), {fake.owner_thread_id})
            self.assertNotEqual(fake.owner_thread_id, threading.get_ident())
            self.assertEqual(owner.snapshot.transactions, 2)

            snap = broker.snapshot
            self.assertEqual(snap.submitted, 1)
            self.assertEqual(snap.accepted, 1)
            self.assertEqual(snap.failed, 0)
            self.assertFalse(snap.in_flight)
        finally:
            broker.stop()
            owner.stop()

        self.assertEqual(created[0].close_thread_id, created[0].owner_thread_id)

    def test_invalid_fcs_and_selector_overflow_fail_before_modem(self) -> None:
        owner = DirectFakeOwner()
        broker = TXBroker(owner, transmit_enabled=True)
        broker.start()
        try:
            bad_fcs = p5_reference_frame()[:-1] + bytes((p5_reference_frame()[-1] ^ 0xFF,))
            with self.assertRaisesRegex(TXBrokerFrameRejected, "valid FCS"):
                broker.submit_frame(bad_fcs)

            oversized = build_ui_frame(
                source=Address.parse("KJ6YWD-10"),
                destination=Address.parse("APYWD1"),
                info=b"X" * 250,
                include_fcs=True,
            )
            with self.assertRaisesRegex(TXBrokerFrameRejected, "selector limit"):
                broker.submit_frame(oversized)

            self.assertEqual(owner.status_calls, 0)
            self.assertEqual(owner.calls, [])
            self.assertEqual(broker.snapshot.invalid_rejections, 2)
        finally:
            broker.stop()

    def test_busy_modem_fails_closed_without_tx_command(self) -> None:
        owner = DirectFakeOwner(busy=True)
        broker = TXBroker(owner, transmit_enabled=True)
        broker.start()
        try:
            with self.assertRaisesRegex(TXBrokerBusy, "refusing overlap"):
                broker.submit_frame(p5_reference_frame())
            self.assertEqual(owner.status_calls, 1)
            self.assertEqual(owner.calls, [])
            snap = broker.snapshot
            self.assertEqual(snap.submitted, 1)
            self.assertEqual(snap.accepted, 0)
            self.assertEqual(snap.failed, 1)
            self.assertEqual(snap.busy_rejections, 1)
        finally:
            broker.stop()

    def test_queue_is_bounded_and_fails_closed_when_full(self) -> None:
        release = threading.Event()
        owner = DirectFakeOwner(block_event=release)
        broker = TXBroker(
            owner,
            transmit_enabled=True,
            queue_capacity=1,
            submit_timeout=0.05,
            default_transaction_timeout=1.0,
        )
        broker.start()
        results = []
        errors: list[BaseException] = []

        def submit() -> None:
            try:
                results.append(broker.submit_frame(p5_reference_frame(), timeout=1.0))
            except BaseException as exc:
                errors.append(exc)

        first = threading.Thread(target=submit)
        second = threading.Thread(target=submit)
        first.start()

        deadline = time.monotonic() + 1.0
        while len(owner.calls) < 1 and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertEqual(len(owner.calls), 1)

        second.start()
        deadline = time.monotonic() + 1.0
        while broker.snapshot.queue_depth < 1 and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertEqual(broker.snapshot.queue_depth, 1)

        with self.assertRaises(TXBrokerQueueFull):
            broker.submit_frame(p5_reference_frame(), timeout=1.0)

        release.set()
        first.join(3.0)
        second.join(3.0)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(len(owner.calls), 2)
        self.assertEqual(broker.snapshot.queue_full_rejections, 1)
        broker.stop()


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TXBrokerTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("BOUNDED_TX_BROKER=PASS")
    print("DEFAULT_TX_STATE=DISABLED")
    print("VALID_FCS_REQUIRED=PASS")
    print("P5_SERIALIZER_REUSED=PASS")
    print("P5_SELECTOR_COUNT=691")
    print(f"P5_PACKED_SHA256={P5_PACKED_SHA256}")
    print("MODEM_BUSY_PREFLIGHT=PASS")
    print("QUEUE_FULL_FAIL_CLOSED=PASS")
    print("SINGLE_MODEM_OWNER_TX_PATH=PASS")
    print("KISS_TX_CONNECTED=NO")
    print("HARDWARE_UART_OPENED=NO")
    print("RF_TRANSMITTED=NO")
