from __future__ import annotations

import pathlib
import socket
import sys
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.kiss.control import TNCControlBackend  # noqa: E402
from ywd1278.kiss.framing import (  # noqa: E402
    DATA,
    FEND,
    FESC,
    FULLDUPLEX,
    PERSIST,
    SLOTTIME,
    TXDELAY,
    KISSStreamDecoder,
    encode,
)
from ywd1278.kiss.server import PacketEvent, start_server_thread, stop_server_thread  # noqa: E402


def wait_for(predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise TimeoutError("condition was not satisfied")


def recv_one(sock: socket.socket, timeout: float = 1.0):
    decoder = KISSStreamDecoder()
    deadline = time.monotonic() + timeout
    sock.settimeout(0.05)
    while time.monotonic() < deadline:
        try:
            data = sock.recv(4096)
        except socket.timeout:
            continue
        if not data:
            break
        messages = decoder.feed(data)
        if messages:
            return messages[0]
    raise TimeoutError("expected one KISS message")


class KISSControlPlaneServerTests(unittest.TestCase):
    def test_parameter_commands_work_over_tcp_while_data_stays_disconnected(self) -> None:
        backend = TNCControlBackend(history_capacity=0)
        self.assertFalse(hasattr(backend, "transmit"))
        self.assertFalse(hasattr(backend, "submit_frame"))
        server, thread = start_server_thread(backend, port=0)
        host, port = server.server_address[:2]
        try:
            with socket.create_connection((host, port), timeout=1.0) as client:
                client.sendall(encode(b"\x32", command=TXDELAY))
                client.sendall(encode(b"\x7f", command=PERSIST))
                client.sendall(encode(b"\x07", command=SLOTTIME))
                client.sendall(encode(b"\x00", command=FULLDUPLEX))

                wait_for(lambda: backend.control_counters.kiss_parameter_updates == 4)
                snap = backend.control_snapshot
                self.assertEqual((snap.generation, snap.txdelay, snap.persist, snap.slottime, snap.fullduplex), (4, 50, 127, 7, 0))

                client.sendall(encode(b"do-not-transmit", command=DATA))
                wait_for(lambda: backend.control_counters.kiss_data_tx_rejected == 1)
                self.assertEqual(backend.snapshot.tx_rejected, 1)
                self.assertEqual(backend.control_snapshot.generation, 4)
        finally:
            stop_server_thread(server, thread)

    def test_bad_controls_and_decoder_discards_are_counted_without_crashing_server(self) -> None:
        backend = TNCControlBackend(history_capacity=0)
        server, thread = start_server_thread(backend, port=0)
        host, port = server.server_address[:2]
        try:
            with socket.create_connection((host, port), timeout=1.0) as client:
                client.sendall(encode(b"\x1e\x1f", command=TXDELAY))
                client.sendall(encode(b"\x00", port=2, command=PERSIST))
                client.sendall(encode(b"\x01", command=0x04))
                client.sendall(encode(b"\x00", command=SLOTTIME))
                client.sendall(encode(b"\x01", command=FULLDUPLEX))

                # Invalid KISS escape: decoder must discard/resync and report it
                # through the optional P6 malformed-stream hook.
                client.sendall(bytes((FEND, TXDELAY, FESC, 0x99, FEND)))

                wait_for(lambda: backend.control_counters.kiss_malformed_frames >= 2)
                counters = backend.control_counters
                self.assertEqual(counters.kiss_parameter_updates, 0)
                self.assertEqual(counters.kiss_parameter_rejections, 3)
                self.assertEqual(counters.kiss_unsupported_ports, 1)
                self.assertEqual(counters.kiss_unknown_commands, 1)
                self.assertEqual(counters.kiss_slot_time_rejected, 1)
                self.assertEqual(counters.kiss_full_duplex_rejected, 1)
                self.assertEqual(counters.kiss_malformed_frames, 2)
                self.assertEqual(backend.control_snapshot.generation, 0)

                # Prove the same socket/server still functions after malformed
                # client input by accepting a valid parameter update.
                client.sendall(encode(b"\x40", command=PERSIST))
                wait_for(lambda: backend.control_snapshot.generation == 1)
                self.assertEqual(backend.control_snapshot.persist, 64)
        finally:
            stop_server_thread(server, thread)

    def test_rx_delivery_is_unchanged_for_control_aware_backend(self) -> None:
        backend = TNCControlBackend(
            [PacketEvent(b"history", source="A", destination="B", frame_type="UI")],
            history_capacity=8,
        )
        server, thread = start_server_thread(backend, port=0)
        host, port = server.server_address[:2]
        try:
            with socket.create_connection((host, port), timeout=1.0) as client:
                history = recv_one(client)
                self.assertEqual((history.port, history.command, history.frame), (0, DATA, b"history"))

                backend.publish(PacketEvent(b"live", source="C", destination="D", frame_type="UI"))
                live = recv_one(client)
                self.assertEqual((live.port, live.command, live.frame), (0, DATA, b"live"))
        finally:
            stop_server_thread(server, thread)


if __name__ == "__main__":
    unittest.main(verbosity=2)
