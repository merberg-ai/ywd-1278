from __future__ import annotations

import threading
import time
import unittest

from ywd1278.modem import protocol
from ywd1278.modem.owner import ModemOwner, ModemOwnerError, ModemOwnerQueueFull


IDENTITY = "MMDVM_HS_Hat-YWD-AX25R3-v0.2.2"


def version_response() -> bytes:
    return protocol.build_frame(
        protocol.GET_VERSION,
        bytes((1,)) + IDENTITY.encode("ascii") + b"\0",
    )


def rx_status_response() -> bytes:
    samples = 0x12345678
    return protocol.build_frame(
        protocol.YWD_RX,
        bytes(
            (
                protocol.RX_STATUS,
                protocol.RX_PROTOCOL_REVISION,
                0x0D,
                3,
                0,
                samples & 0xFF,
                (samples >> 8) & 0xFF,
                (samples >> 16) & 0xFF,
                (samples >> 24) & 0xFF,
                0,
                0,
            )
        ),
    )


def rf_diag_response() -> bytes:
    return protocol.build_frame(
        protocol.YWD_RF,
        bytes((protocol.RF_GET_DIAG, 0x34, 0x12, 0, 0, 0, 0)),
    )


class ThreadBoundFakeTransport:
    """Fake modem that refuses every call outside its construction thread."""

    def __init__(self, *, block_event: threading.Event | None = None) -> None:
        self.owner_thread_id = threading.get_ident()
        self.call_thread_ids: list[int] = []
        self.requests: list[bytes] = []
        self.close_thread_id: int | None = None
        self.block_event = block_event
        self._block_once = block_event is not None

    def _assert_owner(self) -> None:
        if threading.get_ident() != self.owner_thread_id:
            raise RuntimeError("fake transport accessed outside owner thread")

    def transact(self, request: bytes, *, timeout: float) -> bytes:
        self._assert_owner()
        self.call_thread_ids.append(threading.get_ident())
        self.requests.append(request)

        if self._block_once:
            self._block_once = False
            assert self.block_event is not None
            if not self.block_event.wait(timeout=2.0):
                raise TimeoutError("test transport block was not released")

        frame = protocol.parse_frame(request)
        if frame.command == protocol.GET_VERSION:
            return version_response()
        if frame.command == protocol.YWD_RX:
            subcommand = frame.payload[0]
            if subcommand in (protocol.RX_START, protocol.RX_STOP):
                return protocol.ack_for(protocol.YWD_RX)
            if subcommand == protocol.RX_STATUS:
                return rx_status_response()
            if subcommand == protocol.RX_READ:
                return protocol.build_frame(
                    protocol.YWD_RX,
                    bytes((protocol.RX_READ, 3, 0xAA, 0xBB, 0xCC)),
                )
        if frame.command == protocol.YWD_RF and frame.payload == bytes((protocol.RF_GET_DIAG,)):
            return rf_diag_response()
        raise AssertionError(f"unexpected fake-modem request: {request.hex()}")

    def close(self) -> None:
        self._assert_owner()
        self.close_thread_id = threading.get_ident()


class ModemOwnerTests(unittest.TestCase):
    def test_all_transport_io_occurs_in_exactly_one_owner_thread(self) -> None:
        created: list[ThreadBoundFakeTransport] = []

        def factory() -> ThreadBoundFakeTransport:
            transport = ThreadBoundFakeTransport()
            created.append(transport)
            return transport

        owner = ModemOwner(factory, queue_capacity=4)
        owner.start()
        try:
            self.assertEqual(len(created), 1)
            fake = created[0]
            snapshot = owner.snapshot
            self.assertTrue(snapshot.running)
            self.assertEqual(snapshot.owner_thread_id, fake.owner_thread_id)
            self.assertNotEqual(snapshot.owner_thread_id, threading.get_ident())

            version = owner.get_version()
            self.assertEqual(version.identity, IDENTITY)

            owner.rx_start()
            status = owner.rx_status()
            self.assertEqual(status.flags, 0x0D)
            self.assertEqual(status.available_bytes, 3)
            self.assertEqual(status.samples, 0x12345678)
            self.assertEqual(status.dropped_bytes, 0)

            self.assertEqual(owner.rx_read(20), b"\xAA\xBB\xCC")
            diag = owner.rf_diagnostics()
            self.assertEqual(diag.interrupt_count, 0x1234)
            self.assertEqual(diag.keyups, 0)
            self.assertEqual(diag.generated_samples, 0)
            self.assertEqual(diag.tx_active, 0)
            owner.rx_stop()

            self.assertFalse(hasattr(owner, "rf_tx_tones"))
            self.assertFalse(hasattr(owner, "transact"))
            self.assertEqual(len(fake.call_thread_ids), 6)
            self.assertEqual(set(fake.call_thread_ids), {fake.owner_thread_id})
            self.assertEqual(owner.snapshot.transactions, 6)

            # Even if another component somehow retains a transport reference,
            # the transport-level thread binding still rejects direct access.
            with self.assertRaisesRegex(RuntimeError, "outside owner thread"):
                fake.transact(protocol.get_version_request(), timeout=0.1)
        finally:
            owner.stop()

        self.assertEqual(created[0].close_thread_id, created[0].owner_thread_id)
        self.assertFalse(owner.snapshot.running)

    def test_request_queue_is_bounded_and_fails_closed_when_full(self) -> None:
        release = threading.Event()
        created: list[ThreadBoundFakeTransport] = []

        def factory() -> ThreadBoundFakeTransport:
            transport = ThreadBoundFakeTransport(block_event=release)
            created.append(transport)
            return transport

        owner = ModemOwner(
            factory,
            queue_capacity=1,
            submit_timeout=0.05,
            default_transaction_timeout=1.0,
        )
        owner.start()
        errors: list[BaseException] = []

        def call_version() -> None:
            try:
                owner.get_version(timeout=1.0)
            except BaseException as exc:
                errors.append(exc)

        first = threading.Thread(target=call_version)
        second = threading.Thread(target=call_version)
        first.start()

        # Wait until the owner is inside the first blocked transaction.
        deadline = time.monotonic() + 1.0
        while len(created[0].requests) < 1 and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertEqual(len(created[0].requests), 1)

        second.start()
        deadline = time.monotonic() + 1.0
        while owner.snapshot.queue_depth < 1 and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertEqual(owner.snapshot.queue_depth, 1)

        with self.assertRaises(ModemOwnerQueueFull):
            owner.get_version(timeout=1.0)

        release.set()
        first.join(2.0)
        second.join(2.0)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])
        owner.stop()

    def test_transport_or_parse_failure_returns_through_owner_boundary(self) -> None:
        class BadTransport(ThreadBoundFakeTransport):
            def transact(self, request: bytes, *, timeout: float) -> bytes:
                self._assert_owner()
                return b"\x00bad"

        owner = ModemOwner(BadTransport)
        owner.start()
        try:
            with self.assertRaises(ModemOwnerError) as caught:
                owner.get_version()
            self.assertIsInstance(caught.exception.__cause__, ValueError)
        finally:
            owner.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
