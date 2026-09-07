#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import time
import unittest

from ywd1278.ax25 import Address, parse_frame, verify_fcs
from ywd1278.kiss.control import TNCParameterSnapshot, TNCSessionState
from ywd1278.kiss.framing import DATA, KISSMessage
from ywd1278.kiss.server import PacketEvent
from ywd1278.kiss.sustained import ThreadSafeKISSDataAdmissionQueue
from ywd1278.link.data_link import Modulo8DataLink
from ywd1278.service.appliance import ProductTNCBackend
from ywd1278.service.node_mailbox_config import ProductNodeMailboxConfig
from ywd1278.service.persistent_bbs_service import (
    ProductPersistentBBSService,
    ProductPersistentBBSServiceError,
)


LOCAL = Address.parse("KJ6YWD-10")
REMOTE = Address.parse("KJ6YWD-15")


class ManualClock:
    def __init__(self) -> None:
        self.value = 0.0
        self.lock = threading.Lock()

    def __call__(self) -> float:
        with self.lock:
            return self.value

    def advance(self, seconds: float) -> float:
        with self.lock:
            self.value += float(seconds)
            return self.value


class RecordingFinalEdge:
    """Fake only the final contextual hardware/RF submission edge."""

    def __init__(self) -> None:
        self.calls: list[tuple[bytes, object, float | None]] = []

    def submit_frame(self, frame_with_fcs: bytes, context, *, timeout=None):  # type: ignore[no-untyped-def]
        self.calls.append((bytes(frame_with_fcs), context, timeout))
        return {"fake_final_edge": True, "call": len(self.calls)}


class PersistentBBSProductCompositionP4c2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="ywd-0i-p4c2-real-backend-")
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "mailbox.sqlite3"
        self.clock = ManualClock()
        self.final_edge = RecordingFinalEdge()

    def config(self) -> ProductNodeMailboxConfig:
        return ProductNodeMailboxConfig(
            node_enabled=True,
            local=LOCAL,
            alias="YWDNOD",
            max_sessions=1,
            mailbox_enabled=True,
            mailbox_database=self.db,
            mailbox_paclen=128,
            mailbox_info="KJ6YWD persistent packet mailbox",
        )

    def make_backend(self, *, tx_enabled: bool) -> tuple[ProductTNCBackend, ThreadSafeKISSDataAdmissionQueue]:
        admission = ThreadSafeKISSDataAdmissionQueue(
            self.final_edge,
            monotonic=self.clock,
            queue_capacity=4,
            request_timeout_seconds=30.0,
            downstream_timeout_seconds=1.5,
        )
        session = TNCSessionState(
            TNCParameterSnapshot(
                txdelay=30,
                persist=255,
                slottime=1,
            )
        )
        backend = ProductTNCBackend(
            admission,
            monotonic=self.clock,
            session=session,
            history_capacity=16,
            subscriber_queue_capacity=16,
            product_tx_enabled=tx_enabled,
        )
        return backend, admission

    @staticmethod
    def wait_until(predicate, timeout: float = 2.0) -> None:  # type: ignore[no-untyped-def]
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.005)
        raise AssertionError("condition not reached before timeout")

    @staticmethod
    def identity(address: Address) -> tuple[str, int]:
        # AX.25 command/response C/H bits are frame semantics, not peer identity.
        return address.callsign, address.ssid

    def dispatch_one(self, admission: ThreadSafeKISSDataAdmissionQueue) -> None:
        before = len(self.final_edge.calls)
        self.clock.advance(1.0)
        first = admission.observe_rssi(
            now=-999.0,
            raw_magnitude=97,
            random_byte_source=lambda: 0,
        )
        self.assertFalse(first.downstream_called)
        self.clock.advance(0.30)
        second = admission.observe_rssi(
            now=-999.0,
            raw_magnitude=97,
            random_byte_source=lambda: 0,
        )
        self.assertFalse(second.downstream_called)
        self.clock.advance(0.02)
        third = admission.observe_rssi(
            now=-999.0,
            raw_magnitude=97,
            random_byte_source=lambda: 0,
        )
        self.assertTrue(third.downstream_called)
        self.assertEqual(len(self.final_edge.calls), before + 1)

    def test_real_product_backend_is_the_service_stream_and_admission_boundary(self) -> None:
        backend, admission = self.make_backend(tx_enabled=True)
        service = ProductPersistentBBSService(
            self.config(),
            backend_getter=lambda: backend,
            tx_enabled=True,
            # Freeze connected timers for this composition test. Channel access
            # uses the independent explicit ManualClock above.
            monotonic=lambda: 0.0,
            time_ns=lambda: 1_000_000_000,
            poll_interval_seconds=0.01,
        )
        service.start()
        self.addCleanup(service.stop)

        self.assertIs(service._backend, backend)
        self.assertIsInstance(service._backend, ProductTNCBackend)
        self.assertIsNotNone(service.store)
        self.assertEqual(backend.snapshot.subscribers, 1)
        counters = backend.connection_counters
        self.assertEqual(counters.total_connections, 1)
        self.assertEqual(counters.active_connections, 1)

        peer = Modulo8DataLink(local=REMOTE, remote=LOCAL, maxframe=1, paclen=256)
        sabm = peer.connect()
        self.assertTrue(sabm.accepted)
        backend.publish(PacketEvent(sabm.actions[0].frame_no_fcs))

        # SABM produces UA plus the first connected BBS banner I-frame. Both
        # must enter the exact ProductTNCBackend -> real bounded DATA queue.
        self.wait_until(lambda: service.snapshot.tx_actions_admitted >= 2)
        self.assertEqual(service.snapshot.tx_admission_failures, 0)
        self.assertEqual(backend.ingress_counters.data_admitted, 2)
        self.assertEqual(admission.snapshot.queue_depth, 2)
        self.assertEqual(self.final_edge.calls, [])

        # No scheduler exists in the BBS service. Only explicit qualified
        # channel observations can consume the already-admitted requests.
        self.dispatch_one(admission)
        self.dispatch_one(admission)
        self.assertEqual(admission.snapshot.queue_depth, 0)
        self.assertEqual(admission.snapshot.dispatched_requests, 2)
        self.assertEqual(len(self.final_edge.calls), 2)

        ua_with_fcs = self.final_edge.calls[0][0]
        banner_with_fcs = self.final_edge.calls[1][0]
        self.assertTrue(verify_fcs(ua_with_fcs))
        self.assertTrue(verify_fcs(banner_with_fcs))
        ua = parse_frame(ua_with_fcs[:-2], has_fcs=False)
        banner = parse_frame(banner_with_fcs[:-2], has_fcs=False)
        self.assertEqual(ua["frame_type"], "UA")
        self.assertEqual(banner["frame_type"], "I")
        self.assertEqual(self.identity(ua["destination"]), self.identity(REMOTE))
        self.assertEqual(self.identity(banner["destination"]), self.identity(REMOTE))
        self.assertIn(b"YWDNOD:KJ6YWD-10} Connected to BBS", banner["info"])

        service.stop()
        self.assertEqual(backend.snapshot.subscribers, 0)
        counters = backend.connection_counters
        self.assertEqual(counters.total_connections, 1)
        self.assertEqual(counters.total_disconnects, 1)
        self.assertEqual(counters.active_connections, 0)
        self.assertTrue(self.db.exists())

    def test_real_product_backend_tx_disabled_fails_closed_before_queue_or_final_edge(self) -> None:
        backend, admission = self.make_backend(tx_enabled=False)
        peer = Modulo8DataLink(local=REMOTE, remote=LOCAL, maxframe=1, paclen=256)
        sabm = peer.connect().actions[0].frame_no_fcs
        result = backend.reject_client_message(KISSMessage(port=0, command=DATA, frame=sabm))

        self.assertFalse(bool(getattr(result, "updated", False)))
        self.assertEqual(backend.control_counters.kiss_data_tx_rejected, 1)
        self.assertEqual(backend.ingress_counters.data_messages_received, 0)
        self.assertEqual(admission.snapshot.queue_depth, 0)
        self.assertEqual(admission.snapshot.dispatched_requests, 0)
        self.assertEqual(self.final_edge.calls, [])

        with self.assertRaisesRegex(ProductPersistentBBSServiceError, "tx_enabled=true"):
            ProductPersistentBBSService(
                self.config(),
                backend_getter=lambda: backend,
                tx_enabled=False,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
