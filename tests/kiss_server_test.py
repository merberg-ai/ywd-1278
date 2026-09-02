from __future__ import annotations

import pathlib
import socket
import sys
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.kiss.framing import KISSStreamDecoder, encode  # noqa: E402
from ywd1278.kiss.server import (  # noqa: E402
    PacketEvent,
    RXOnlyBackend,
    start_server_thread,
    stop_server_thread,
)


def recv_messages(sock: socket.socket, count: int, timeout: float = 1.0):
    decoder = KISSStreamDecoder()
    out = []
    deadline = time.monotonic() + timeout
    sock.settimeout(0.05)
    while len(out) < count and time.monotonic() < deadline:
        try:
            data = sock.recv(4096)
        except socket.timeout:
            continue
        if not data:
            break
        out.extend(decoder.feed(data))
    if len(out) < count:
        raise TimeoutError(f"expected {count} KISS messages, got {len(out)}")
    return out


class KISSServerTests(unittest.TestCase):
    def test_history_and_live_events_are_emitted_as_standard_kiss_data(self) -> None:
        first = PacketEvent(b"first", source="A", destination="B", frame_type="UI")
        second = PacketEvent(b"second", source="C", destination="D", frame_type="I")
        backend = RXOnlyBackend([first], history_capacity=8, subscriber_queue_capacity=4)
        server, thread = start_server_thread(backend, port=0)
        host, port = server.server_address[:2]
        try:
            with socket.create_connection((host, port), timeout=1.0) as client:
                history = recv_messages(client, 1)
                self.assertEqual((history[0].port, history[0].command, history[0].frame), (0, 0, b"first"))

                backend.publish(second)
                live = recv_messages(client, 1)
                self.assertEqual((live[0].port, live[0].command, live[0].frame), (0, 0, b"second"))
        finally:
            stop_server_thread(server, thread)

        self.assertEqual(backend.snapshot.subscribers, 0)

    def test_client_data_is_counted_and_rejected_without_tx_callback(self) -> None:
        backend = RXOnlyBackend(history_capacity=0)
        self.assertFalse(hasattr(backend, "transmit"))
        server, thread = start_server_thread(backend, port=0)
        host, port = server.server_address[:2]
        try:
            with socket.create_connection((host, port), timeout=1.0) as client:
                client.sendall(encode(b"do-not-transmit"))
                client.sendall(encode(b"ignored-control", command=1))
                deadline = time.monotonic() + 1.0
                while time.monotonic() < deadline:
                    snap = backend.snapshot
                    if snap.tx_rejected == 1 and snap.control_ignored == 1:
                        break
                    time.sleep(0.01)
                snap = backend.snapshot
                self.assertEqual(snap.tx_rejected, 1)
                self.assertEqual(snap.control_ignored, 1)
        finally:
            stop_server_thread(server, thread)

    def test_subscriber_queue_is_bounded_and_drop_is_accounted(self) -> None:
        backend = RXOnlyBackend(history_capacity=0, subscriber_queue_capacity=1)
        _, queue = backend.open_stream()
        try:
            backend.publish(PacketEvent(b"one"))
            backend.publish(PacketEvent(b"two"))
            self.assertEqual(queue.qsize(), 1)
            self.assertEqual(backend.snapshot.subscriber_drops, 1)
        finally:
            backend.close_stream(queue)

    def test_history_is_bounded(self) -> None:
        backend = RXOnlyBackend(history_capacity=2)
        backend.publish(PacketEvent(b"one"))
        backend.publish(PacketEvent(b"two"))
        backend.publish(PacketEvent(b"three"))
        history, queue = backend.open_stream()
        try:
            self.assertEqual([event.frame_no_fcs for event in history], [b"two", b"three"])
            self.assertEqual(backend.snapshot.stored_events, 2)
        finally:
            backend.close_stream(queue)


if __name__ == "__main__":
    unittest.main(verbosity=2)
