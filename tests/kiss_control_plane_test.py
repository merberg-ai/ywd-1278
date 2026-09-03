from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.kiss.control import (  # noqa: E402
    ControlDisposition,
    TNCParameterSnapshot,
    TNCQueueAccounting,
    TNCSessionState,
)
from ywd1278.kiss.framing import (  # noqa: E402
    DATA,
    FULLDUPLEX,
    PERSIST,
    SLOTTIME,
    TXDELAY,
    KISSMessage,
)


def msg(command: int, payload: bytes, *, port: int = 0) -> KISSMessage:
    return KISSMessage(port=port, command=command, frame=payload)


class KISSControlPlaneTests(unittest.TestCase):
    def test_default_snapshot_matches_qualified_tnc_defaults(self) -> None:
        state = TNCSessionState()
        snap = state.snapshot
        self.assertEqual(
            (snap.generation, snap.port, snap.txdelay, snap.persist, snap.slottime, snap.fullduplex),
            (0, 0, 30, 63, 10, 0),
        )
        self.assertEqual(snap.txdelay_profile.pre_flags, 45)
        self.assertAlmostEqual(snap.txdelay_profile.requested_seconds, 0.300)
        self.assertEqual(snap.csma_parameters().persist, 63)
        self.assertEqual(snap.csma_parameters().slot_time_10ms, 10)

    def test_supported_parameters_update_atomically_and_advance_generation(self) -> None:
        state = TNCSessionState()
        cases = (
            (TXDELAY, 50, "txdelay"),
            (PERSIST, 127, "persist"),
            (SLOTTIME, 7, "slottime"),
            (FULLDUPLEX, 0, "fullduplex"),
        )
        for generation, (command, value, field) in enumerate(cases, start=1):
            result = state.apply(msg(command, bytes((value,))))
            self.assertEqual(result.disposition, ControlDisposition.PARAMETER_UPDATED)
            self.assertTrue(result.updated)
            self.assertEqual(result.current.generation, generation)
            self.assertEqual(getattr(result.current, field), value)
            self.assertEqual(state.snapshot, result.current)

        counters = state.counters
        self.assertEqual(counters.kiss_messages_received, 4)
        self.assertEqual(counters.kiss_parameter_updates, 4)
        self.assertEqual(counters.kiss_parameter_rejections, 0)

    def test_snapshot_context_is_immutable_after_later_parameter_updates(self) -> None:
        state = TNCSessionState()
        state.apply(msg(TXDELAY, b"\x32"))  # 50 -> 500 ms / 75 flags
        state.apply(msg(PERSIST, b"\x7f"))
        state.apply(msg(SLOTTIME, b"\x07"))
        captured = state.capture_tx_context(max_wait_seconds=12.5)

        state.apply(msg(TXDELAY, b"\x1e"))
        state.apply(msg(PERSIST, b"\x01"))
        state.apply(msg(SLOTTIME, b"\x02"))

        self.assertEqual(captured.parameters.generation, 3)
        self.assertEqual(
            (captured.parameters.txdelay, captured.parameters.persist, captured.parameters.slottime),
            (50, 127, 7),
        )
        self.assertEqual(captured.txdelay_profile.pre_flags, 75)
        self.assertEqual(captured.csma_parameters.persist, 127)
        self.assertEqual(captured.csma_parameters.slot_time_10ms, 7)
        self.assertEqual(captured.csma_parameters.max_wait_seconds, 12.5)
        self.assertEqual(state.snapshot.generation, 6)
        self.assertEqual((state.snapshot.txdelay, state.snapshot.persist, state.snapshot.slottime), (30, 1, 2))

    def test_data_unknown_port_malformed_and_unsafe_values_fail_closed(self) -> None:
        state = TNCSessionState()
        initial = state.snapshot

        data = state.apply(msg(DATA, b"not-connected"))
        self.assertEqual(data.disposition, ControlDisposition.DATA_REJECTED)

        wrong_port = state.apply(msg(TXDELAY, b"\x32", port=1))
        self.assertEqual(wrong_port.disposition, ControlDisposition.UNSUPPORTED_PORT)

        unknown = state.apply(msg(0x04, b"\x01"))
        self.assertEqual(unknown.disposition, ControlDisposition.UNKNOWN_COMMAND)

        malformed_empty = state.apply(msg(PERSIST, b""))
        malformed_long = state.apply(msg(TXDELAY, b"\x1e\x1f"))
        self.assertEqual(malformed_empty.disposition, ControlDisposition.MALFORMED)
        self.assertEqual(malformed_long.disposition, ControlDisposition.MALFORMED)

        zero_slot = state.apply(msg(SLOTTIME, b"\x00"))
        duplex = state.apply(msg(FULLDUPLEX, b"\x01"))
        self.assertEqual(zero_slot.disposition, ControlDisposition.PARAMETER_REJECTED)
        self.assertEqual(duplex.disposition, ControlDisposition.PARAMETER_REJECTED)

        self.assertEqual(state.snapshot, initial)
        counters = state.counters
        self.assertEqual(counters.kiss_messages_received, 7)
        self.assertEqual(counters.kiss_parameter_updates, 0)
        self.assertEqual(counters.kiss_parameter_rejections, 4)
        self.assertEqual(counters.kiss_malformed_frames, 2)
        self.assertEqual(counters.kiss_unknown_commands, 1)
        self.assertEqual(counters.kiss_unsupported_ports, 1)
        self.assertEqual(counters.kiss_slot_time_rejected, 1)
        self.assertEqual(counters.kiss_full_duplex_rejected, 1)
        self.assertEqual(counters.kiss_data_tx_rejected, 1)

    def test_malformed_stream_accounting_is_separate_from_decoded_message_count(self) -> None:
        state = TNCSessionState()
        state.note_malformed_stream_frames(3)
        self.assertEqual(state.counters.kiss_malformed_frames, 3)
        self.assertEqual(state.counters.kiss_messages_received, 0)
        with self.assertRaises(ValueError):
            state.note_malformed_stream_frames(-1)

    def test_queue_accounting_maps_existing_access_queue_snapshot_without_mutation(self) -> None:
        source = SimpleNamespace(
            queue_depth=3,
            queue_capacity=4,
            accepted_requests=11,
            invalid_rejections=2,
            queue_full_rejections=5,
            dispatched_requests=7,
            timed_out_requests=1,
            downstream_failures=1,
        )
        accounting = TNCQueueAccounting.from_access_snapshot(source)
        self.assertEqual(accounting.tx_queue_depth, 3)
        self.assertEqual(accounting.tx_queue_capacity, 4)
        self.assertEqual(accounting.tx_queue_accepted, 11)
        self.assertEqual(accounting.tx_invalid_rejections, 2)
        self.assertEqual(accounting.tx_queue_full_drops, 5)
        self.assertEqual(accounting.tx_dispatched, 7)
        self.assertEqual(accounting.tx_access_timeouts, 1)
        self.assertEqual(accounting.tx_downstream_failures, 1)

    def test_threaded_parameter_updates_are_atomic_and_never_lose_generations(self) -> None:
        state = TNCSessionState(TNCParameterSnapshot())

        def worker(value: int) -> None:
            for _ in range(100):
                result = state.apply(msg(PERSIST, bytes((value,))))
                self.assertTrue(result.updated)

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(worker, (1, 63, 127, 255)))

        self.assertEqual(state.snapshot.generation, 400)
        self.assertEqual(state.counters.kiss_parameter_updates, 400)
        self.assertEqual(state.counters.kiss_messages_received, 400)
        self.assertIn(state.snapshot.persist, {1, 63, 127, 255})


if __name__ == "__main__":
    unittest.main(verbosity=2)
