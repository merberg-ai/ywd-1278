#!/usr/bin/env python3
"""Regression for the real AX25R4 continuously-producing RX FIFO.

The P8 host fake modem historically used a finite bytearray and eventually
returned an empty RX_READ.  Real AX25R4 never has that property while RX is
active: the 19.2 ksps sampler keeps packing raw bits even during RF silence.
This test makes that distinction explicit so the sustained scheduler can never
again wait for a zero-length read before allowing RSSI/CSMA to run.
"""

from __future__ import annotations

from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.service.tnc_runtime import (  # noqa: E402
    RX_FIFO_DRAIN_READ_LIMIT,
    SustainedTNCRuntime,
)


class ContinuousRXOwner:
    def __init__(self) -> None:
        self.reads = 0

    def rx_read(self, maximum: int) -> bytes:
        self.reads += 1
        time.sleep(0.001)
        return bytes([self.reads & 1]) * int(maximum)


class PartialRXOwner:
    def __init__(self) -> None:
        self.reads = 0

    def rx_read(self, maximum: int) -> bytes:
        self.reads += 1
        if self.reads == 1:
            return b"\x00" * int(maximum)
        if self.reads == 2:
            return b"\x00" * 37
        raise AssertionError("bounded drain read past the first partial RX_READ")


def runtime_for(owner) -> SustainedTNCRuntime:  # type: ignore[no-untyped-def]
    return SustainedTNCRuntime(
        owner,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        expected_identity="test",
        monotonic=time.monotonic,
        random_byte_source=lambda: 0,
        read_maximum=200,
        idle_sleep_seconds=0.0,
        status_interval_seconds=0.25,
    )


# A continuously-producing fake never returns zero or partial data.  The drain
# still must return promptly after the fixed hardware-derived read budget.
continuous = ContinuousRXOwner()
continuous_runtime = runtime_for(continuous)
thread = threading.Thread(target=continuous_runtime._drain_rx_fifo, daemon=True)
thread.start()
thread.join(timeout=0.25)
assert not thread.is_alive(), "P8 RX drain chased a continuously-producing sampler forever"
assert continuous.reads == RX_FIFO_DRAIN_READ_LIMIT == 4
assert continuous_runtime.runtime_counters.rx_read_transactions == 4
assert continuous_runtime.runtime_counters.packed_rx_bytes == 800

# A partial read means the pre-existing backlog has been overtaken, so no extra
# read is permitted just to seek an exact zero-length transaction.
partial = PartialRXOwner()
partial_runtime = runtime_for(partial)
partial_runtime._drain_rx_fifo()
assert partial.reads == 2
assert partial_runtime.runtime_counters.rx_read_transactions == 2
assert partial_runtime.runtime_counters.packed_rx_bytes == 237

print("P8_CONTINUOUS_RX_FIFO_REGRESSION=PASS")
print("RX_FIFO_DRAIN_READ_LIMIT=4")
print("FULL_READS_BEFORE_SCHEDULER_PROGRESS=4")
print("PARTIAL_READ_STOPS_DRAIN=PASS")
print("ZERO_LENGTH_READ_REQUIRED=NO")
