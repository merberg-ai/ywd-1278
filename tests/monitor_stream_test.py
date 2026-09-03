#!/usr/bin/env python3
from __future__ import annotations

from queue import Empty
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.ax25 import Address, build_ui_frame, encode_address  # noqa: E402
from ywd1278.kiss.server import PacketEvent, RXOnlyBackend  # noqa: E402
from ywd1278.monitor import DecodedMonitorStream  # noqa: E402


def event_for(body: bytes) -> PacketEvent:
    from ywd1278.ax25 import parse_frame

    parsed = parse_frame(body, has_fcs=False)
    return PacketEvent(
        body,
        source=str(parsed["source"]),
        destination=str(parsed["destination"]),
        frame_type=str(parsed["frame_type"]),
    )


class TickClock:
    def __init__(self) -> None:
        self.value = 1000

    def __call__(self) -> int:
        current = self.value
        self.value += 1000
        return current


class MonitorStreamTests(unittest.TestCase):
    def test_ui_history_then_live_preserves_order_and_path_flags(self) -> None:
        first = build_ui_frame(
            source=Address.parse("KJ6YWD"),
            destination=Address.parse("APRS"),
            path=[Address.parse("WIDE1-1", flag=True), Address.parse("WIDE2-1")],
            info=b"hello\r\n\\\x00",
            include_fcs=False,
        )
        second = build_ui_frame(
            source=Address.parse("N0CALL-2"),
            destination=Address.parse("TEST"),
            info=b"live",
            include_fcs=False,
        )
        backend = RXOnlyBackend([event_for(first)], history_capacity=8, subscriber_queue_capacity=4)
        stream = DecodedMonitorStream(backend, clock_ns=TickClock())

        with stream.open() as monitor:
            backend.publish(event_for(second))
            a = monitor.get(timeout=0.1)
            b = monitor.get(timeout=0.1)

            self.assertEqual((a.sequence, b.sequence), (1, 2))
            self.assertTrue(a.history_replay)
            self.assertFalse(b.history_replay)
            self.assertEqual(a.observed_at_ns, 1000)
            self.assertEqual(b.observed_at_ns, 2000)
            self.assertEqual(a.path, ("WIDE1-1*", "WIDE2-1"))
            self.assertEqual(
                a.line,
                r"KJ6YWD>APRS,WIDE1-1*,WIDE2-1:hello\r\n\\\x00",
            )
            self.assertEqual(b.line, "N0CALL-2>TEST:live")
            self.assertEqual(monitor.snapshot.records_returned, 2)

        self.assertEqual(backend.snapshot.subscribers, 0)

    def test_frozen_physical_i_frame_gets_structured_connected_mode_line(self) -> None:
        # 2026-09-01 physical AX25R3 capture. FCS 00 28 removed because
        # PacketEvent is explicitly the no-FCS backend representation.
        body = bytes.fromhex(
            "a4 88 8e 40 40 40 e0 "
            "96 94 6c b2 ae 88 63 "
            "20 f0 6e 0d"
        )
        backend = RXOnlyBackend([event_for(body)], history_capacity=4)
        with DecodedMonitorStream(backend, clock_ns=lambda: 123).open() as monitor:
            record = monitor.get(timeout=0.1)

        self.assertEqual(record.source, "KJ6YWD-1")
        self.assertEqual(record.destination, "RDG")
        self.assertEqual(record.frame_class, "I")
        self.assertEqual(record.frame_type, "I")
        self.assertEqual(record.ns, 0)
        self.assertEqual(record.nr, 1)
        self.assertEqual(record.pid, 0xF0)
        self.assertEqual(record.info, b"n\r")
        self.assertEqual(
            record.line,
            r"KJ6YWD-1>RDG:[I ns=0 nr=1 pf=0 pid=0xF0] n\r",
        )

    def test_supervisory_frame_is_not_discarded(self) -> None:
        body = bytearray()
        body.extend(encode_address(Address.parse("NODE"), last=False))
        body.extend(encode_address(Address.parse("N0CALL-2"), last=True))
        body.append(0x61)  # modulo-8 RR, N(R)=3, P/F=0
        backend = RXOnlyBackend([event_for(bytes(body))])
        with DecodedMonitorStream(backend).open() as monitor:
            record = monitor.get(timeout=0.1)
        self.assertEqual(record.frame_class, "S")
        self.assertEqual(record.frame_type, "RR")
        self.assertEqual(record.nr, 3)
        self.assertEqual(record.line, "N0CALL-2>NODE:[RR nr=3 pf=0]")

    def test_invalid_internal_event_is_counted_and_skipped(self) -> None:
        valid = build_ui_frame(
            source=Address.parse("GOOD"),
            destination=Address.parse("MON"),
            info=b"after-bad",
            include_fcs=False,
        )
        backend = RXOnlyBackend(
            [PacketEvent(b"not-an-ax25-frame"), event_for(valid)],
            history_capacity=4,
        )
        with DecodedMonitorStream(backend).open() as monitor:
            record = monitor.get(timeout=0.1)
            snap = monitor.snapshot
        self.assertEqual(record.line, "GOOD>MON:after-bad")
        self.assertEqual(record.sequence, 1)
        self.assertEqual(snap.decode_failures, 1)
        self.assertEqual(snap.records_returned, 1)

    def test_packet_event_metadata_mismatch_is_counted_and_skipped(self) -> None:
        body = build_ui_frame(
            source=Address.parse("RIGHT"),
            destination=Address.parse("MON"),
            info=b"metadata",
            include_fcs=False,
        )
        good = event_for(body)
        backend = RXOnlyBackend(
            [PacketEvent(body, source="WRONG", destination="MON", frame_type="UI"), good]
        )
        with DecodedMonitorStream(backend).open() as monitor:
            record = monitor.get(timeout=0.1)
            snap = monitor.snapshot
        self.assertEqual(record.source, "RIGHT")
        self.assertEqual(snap.decode_failures, 1)

    def test_monitor_uses_existing_bounded_backend_queue(self) -> None:
        one = build_ui_frame(
            source=Address.parse("ONE"),
            destination=Address.parse("MON"),
            info=b"1",
            include_fcs=False,
        )
        two = build_ui_frame(
            source=Address.parse("TWO"),
            destination=Address.parse("MON"),
            info=b"2",
            include_fcs=False,
        )
        backend = RXOnlyBackend(history_capacity=0, subscriber_queue_capacity=1)
        with DecodedMonitorStream(backend).open() as monitor:
            backend.publish(event_for(one))
            backend.publish(event_for(two))
            self.assertEqual(monitor.snapshot.queued_live_events, 1)
            self.assertEqual(monitor.snapshot.source_subscriber_drops, 1)
            record = monitor.get(timeout=0.1)
            self.assertEqual(record.source, "ONE")
            with self.assertRaises(Empty):
                monitor.get(timeout=0.0)

    def test_monitor_surface_has_no_write_or_tx_operation(self) -> None:
        backend = RXOnlyBackend()
        stream = DecodedMonitorStream(backend)
        self.assertFalse(hasattr(stream, "publish"))
        self.assertFalse(hasattr(stream, "transmit"))
        with stream.open() as monitor:
            self.assertFalse(hasattr(monitor, "publish"))
            self.assertFalse(hasattr(monitor, "transmit"))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(MonitorStreamTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("YWD1278_0D_P1_MONITOR_STREAM=PASS")
    print("MONITOR_HISTORY_THEN_LIVE=PASS")
    print("MONITOR_UI_I_S_U_STRUCTURED=PASS")
    print("MONITOR_PATH_REPEAT_FLAGS=PASS")
    print("MONITOR_BINARY_ESCAPE=PASS")
    print("MONITOR_SOURCE_QUEUE_BOUNDED=PASS")
    print("MONITOR_TX_CAPABILITY=ABSENT")
    print("MODEM_UART_OPENED=NO")
    print("RF_TRANSMITTED=NO")
