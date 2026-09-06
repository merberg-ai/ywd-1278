#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from queue import Queue
import tempfile
import threading
import time
import unittest

from ywd1278.ax25 import Address
from ywd1278.kiss.framing import DATA, KISSMessage
from ywd1278.kiss.server import PacketEvent
from ywd1278.link.data_link import Modulo8DataLink
from ywd1278.link.modulo8 import LinkState
from ywd1278.service.node_mailbox_config import ProductNodeMailboxConfig
from ywd1278.service.persistent_bbs_service import (
    ProductPersistentBBSService,
    ProductPersistentBBSServiceError,
)


LOCAL = Address.parse("KJ6YWD-10")
REMOTE = Address.parse("KJ6YWD-15")


@dataclass(frozen=True)
class Ingress:
    admitted: bool
    reason: str


class StepClock:
    def __init__(self, step: float = 0.10) -> None:
        self.value = 0.0
        self.step = step
        self.lock = threading.Lock()

    def __call__(self) -> float:
        with self.lock:
            self.value += self.step
            return self.value


class NSClock:
    def __init__(self) -> None:
        self.value = 1_000_000_000

    def __call__(self) -> int:
        self.value += 1_000_000_000
        return self.value


class LoopbackBackend:
    def __init__(self, peer: Modulo8DataLink, history=()) -> None:  # type: ignore[no-untyped-def]
        self.peer = peer
        self.history = list(history)
        self.queue: Queue[PacketEvent] | None = None
        self.closed = False
        self.tx_messages: list[KISSMessage] = []
        self.peer_delivered: list[bytes] = []
        self.reject_next = False

    def open_stream(self):  # type: ignore[no-untyped-def]
        self.queue = Queue(maxsize=64)
        return list(self.history), self.queue

    def close_stream(self, queue) -> None:  # type: ignore[no-untyped-def]
        self.assert_queue(queue)
        self.closed = True

    def publish(self, frame_no_fcs: bytes) -> None:
        assert self.queue is not None
        self.queue.put(PacketEvent(frame_no_fcs=bytes(frame_no_fcs)))

    def reject_client_message(self, message: KISSMessage) -> Ingress:
        self.tx_messages.append(message)
        if self.reject_next:
            self.reject_next = False
            return Ingress(False, "injected queue refusal")
        if message.port != 0 or message.command != DATA:
            return Ingress(False, "not port-0 DATA")
        handled = self.peer.handle_frame(message.frame)
        if not handled.accepted:
            return Ingress(False, f"simulated peer rejected frame: {handled.reason}")
        self.peer_delivered.extend(handled.delivered)
        for action in handled.actions:
            self.publish(action.frame_no_fcs)
        return Ingress(True, "fake product DATA admitted")

    def assert_queue(self, queue) -> None:  # type: ignore[no-untyped-def]
        if queue is not self.queue:
            raise AssertionError("wrong subscriber queue closed")


class PersistentBBSServiceP4bTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="ywd-0i-p4b-")
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "mailbox.sqlite3"
        self.clock = StepClock()
        self.wall = NSClock()

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

    def start_loop(self, history=()):  # type: ignore[no-untyped-def]
        peer = Modulo8DataLink(local=REMOTE, remote=LOCAL, maxframe=1, paclen=256)
        backend = LoopbackBackend(peer, history=history)
        service = ProductPersistentBBSService(
            self.config(),
            backend_getter=lambda: backend,
            tx_enabled=True,
            monotonic=self.clock,
            time_ns=self.wall,
            poll_interval_seconds=0.01,
        )
        service.start()
        self.addCleanup(service.stop)
        return service, backend, peer

    @staticmethod
    def wait_until(predicate, timeout: float = 2.0) -> None:  # type: ignore[no-untyped-def]
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.005)
        raise AssertionError("condition not reached before timeout")

    def connect(self, backend: LoopbackBackend, peer: Modulo8DataLink) -> None:
        connect = peer.connect()
        self.assertTrue(connect.accepted)
        backend.publish(connect.actions[0].frame_no_fcs)
        self.wait_until(lambda: peer.snapshot.state is LinkState.CONNECTED)
        self.wait_until(lambda: any(b"de KJ6YWD-10>" in x for x in backend.peer_delivered))

    def send(self, backend: LoopbackBackend, peer: Modulo8DataLink, text: bytes) -> None:
        self.wait_until(lambda: peer.snapshot.outstanding == 0)
        sent = peer.send_information(text)
        self.assertTrue(sent.accepted, sent.reason)
        backend.publish(sent.actions[0].frame_no_fcs)
        self.wait_until(lambda: peer.snapshot.outstanding == 0)

    def test_history_is_discarded_and_only_live_sabm_opens_session(self) -> None:
        stale_peer = Modulo8DataLink(local=REMOTE, remote=LOCAL, maxframe=1, paclen=256)
        stale = stale_peer.connect().actions[0].frame_no_fcs
        service, backend, peer = self.start_loop(history=(PacketEvent(stale),))
        time.sleep(0.05)
        self.assertEqual(service.snapshot.history_discarded, 1)
        self.assertEqual(service.snapshot.relevant_frames, 0)
        self.assertEqual(backend.tx_messages, [])

        self.connect(backend, peer)
        self.assertEqual(service.snapshot.active_peer, "KJ6YWD-15")
        self.assertGreaterEqual(service.snapshot.tx_actions_admitted, 2)

    def test_full_product_backend_loop_persists_personal_message(self) -> None:
        service, backend, peer = self.start_loop()
        self.connect(backend, peer)
        self.send(backend, peer, b"SP KJ6YWD-1\r")
        self.send(backend, peer, b"SERVICE TEST\r")
        self.send(backend, peer, b"persistent through backend worker\r")
        self.send(backend, peer, b"/EX\r")
        self.wait_until(lambda: service.store is not None and service.store.counts_for(REMOTE).visible == 1)
        self.send(backend, peer, b"LN\r")
        self.wait_until(lambda: any(b"SERVICE TEST" in x for x in backend.peer_delivered))
        self.send(backend, peer, b"R 1\r")
        self.wait_until(lambda: any(b"persistent through backend worker" in x for x in backend.peer_delivered))
        self.assertEqual(service.snapshot.tx_admission_failures, 0)
        self.assertEqual(service.snapshot.failure, "")

    def test_irrelevant_live_frames_do_not_reach_runtime_or_tx(self) -> None:
        service, backend, _peer = self.start_loop()
        other_local = Address.parse("N0CALL-1")
        irrelevant_peer = Modulo8DataLink(local=REMOTE, remote=other_local, maxframe=1, paclen=256)
        sabm = irrelevant_peer.connect().actions[0].frame_no_fcs
        before = len(backend.tx_messages)
        backend.publish(sabm)
        self.wait_until(lambda: service.snapshot.live_events_seen >= 1)
        self.assertEqual(service.snapshot.relevant_frames, 0)
        self.assertEqual(len(backend.tx_messages), before)
        self.assertIsNone(service.snapshot.active_peer)

    def test_backend_admission_failure_latches_service_failure_without_retry(self) -> None:
        service, backend, peer = self.start_loop()
        backend.reject_next = True
        connect = peer.connect()
        backend.publish(connect.actions[0].frame_no_fcs)
        self.wait_until(lambda: bool(service.snapshot.failure))
        snapshot = service.snapshot
        self.assertEqual(snapshot.tx_admission_failures, 1)
        self.assertEqual(len(backend.tx_messages), 1)
        with self.assertRaises(ProductPersistentBBSServiceError):
            service.check_health()
        time.sleep(0.03)
        self.assertEqual(len(backend.tx_messages), 1)

    def test_service_requires_enabled_config_tx_and_backend_contract(self) -> None:
        config = self.config()
        with self.assertRaisesRegex(ProductPersistentBBSServiceError, "tx_enabled=true"):
            ProductPersistentBBSService(
                config, backend_getter=lambda: object(), tx_enabled=False
            )
        disabled = ProductNodeMailboxConfig(
            node_enabled=False,
            local=None,
            alias="YWDNOD",
            max_sessions=1,
            mailbox_enabled=False,
            mailbox_database=self.db,
            mailbox_paclen=128,
            mailbox_info="disabled",
        )
        with self.assertRaisesRegex(ProductPersistentBBSServiceError, "requires enabled"):
            ProductPersistentBBSService(
                disabled, backend_getter=lambda: object(), tx_enabled=True
            )
        service = ProductPersistentBBSService(
            config, backend_getter=lambda: object(), tx_enabled=True
        )
        with self.assertRaisesRegex(ProductPersistentBBSServiceError, "open_stream"):
            service.start()

    def test_stop_unregisters_stream_and_keeps_database(self) -> None:
        service, backend, peer = self.start_loop()
        self.connect(backend, peer)
        path = service.store.path if service.store is not None else None
        self.assertEqual(path, self.db)
        service.stop()
        self.assertTrue(backend.closed)
        self.assertTrue(self.db.exists())
        self.assertFalse(service.snapshot.running)


if __name__ == "__main__":
    unittest.main(verbosity=2)
