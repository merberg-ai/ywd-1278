#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.modem import protocol  # noqa: E402
from ywd1278.tx.half_duplex import (  # noqa: E402
    HalfDuplexDownstreamError,
    HalfDuplexLatched,
    HalfDuplexParameters,
    HalfDuplexPostTransmitError,
    HalfDuplexPreTransmitError,
    PersistentHalfDuplexSubmitter,
)


ACTIVE_FLAGS = 0x0D
IDLE_FLAGS = 0x04


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(float(seconds))
        self.now += float(seconds)


class FakeModem:
    def __init__(self) -> None:
        self.rx_active = True
        self.dropped = 0
        self.busy_pairs_remaining = 0
        self._last_poll_busy = False
        self.rx_status_calls = 0
        self.rx_stop_calls = 0
        self.rx_start_calls = 0
        self.rf_status_calls = 0
        self.rf_diag_calls = 0
        self.fail_rx_stop = False
        self.fail_rx_start = False
        self.keep_tx_busy = False

    def rx_status(self, *, timeout: float | None = None) -> protocol.RX3Status:
        self.rx_status_calls += 1
        return protocol.RX3Status(
            flags=ACTIVE_FLAGS if self.rx_active else IDLE_FLAGS,
            available_bytes=0,
            samples=1000 + self.rx_status_calls,
            dropped_bytes=self.dropped,
        )

    def rx_stop(self, *, timeout: float | None = None) -> None:
        self.rx_stop_calls += 1
        if self.fail_rx_stop:
            raise RuntimeError("injected RX_STOP failure")
        self.rx_active = False

    def rx_start(self, *, timeout: float | None = None) -> None:
        self.rx_start_calls += 1
        if self.fail_rx_start:
            raise RuntimeError("injected RX_START failure")
        if self.busy_pairs_remaining or self.keep_tx_busy:
            raise RuntimeError("RX_START attempted while TX busy")
        self.rx_active = True

    def rf_status(self, *, timeout: float | None = None) -> protocol.RFStatus:
        self.rf_status_calls += 1
        busy = self.keep_tx_busy or self.busy_pairs_remaining > 0
        self._last_poll_busy = busy
        return protocol.RFStatus(
            flags=0x08 if busy else 0x04,
            remaining_selectors=1 if busy else 0,
            mode=3 if busy else 0,
        )

    def rf_diagnostics(self, *, timeout: float | None = None) -> protocol.RFDiagnostics:
        self.rf_diag_calls += 1
        busy = self._last_poll_busy
        if busy and not self.keep_tx_busy and self.busy_pairs_remaining > 0:
            self.busy_pairs_remaining -= 1
        return protocol.RFDiagnostics(
            interrupt_count=123,
            keyups=1 if busy else 0,
            generated_samples=100 if busy else 0,
            tx_active=1 if busy else 0,
        )


class FakeSubmitter:
    def __init__(self, modem: FakeModem) -> None:
        self.modem = modem
        self.calls = 0
        self.fail_next = False
        self.accepted_frames: list[bytes] = []

    def submit_frame(self, frame_with_fcs: bytes, *, timeout: float | None = None) -> object:
        self.calls += 1
        if self.modem.rx_active:
            raise AssertionError("downstream submit occurred while RX was active")
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("injected downstream failure")
        frame = bytes(frame_with_fcs)
        self.accepted_frames.append(frame)
        self.modem.busy_pairs_remaining = 2
        return ("accepted", self.calls, frame)


def make_lifecycle(modem: FakeModem, submitter: FakeSubmitter, clock: FakeClock):
    return PersistentHalfDuplexSubmitter(
        modem,
        submitter,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        parameters=HalfDuplexParameters(
            transaction_timeout_seconds=1.5,
            tx_idle_poll_seconds=0.05,
            tx_idle_timeout_seconds=0.20,
        ),
    )


# Repeated healthy cycles always restore RX before returning.
clock = FakeClock()
modem = FakeModem()
submitter = FakeSubmitter(modem)
lifecycle = make_lifecycle(modem, submitter, clock)
frames = [b"frame-1", b"frame-2", b"frame-3"]
for index, frame in enumerate(frames, start=1):
    result = lifecycle.submit_frame(frame)
    assert result == ("accepted", index, frame)
    assert modem.rx_active is True
    assert lifecycle.snapshot.failed_latched is False
assert submitter.calls == 3
assert submitter.accepted_frames == frames
assert lifecycle.snapshot.cycles_started == 3
assert lifecycle.snapshot.cycles_completed == 3
assert lifecycle.snapshot.downstream_accepted == 3
assert lifecycle.snapshot.rx_stop_operations == 3
assert lifecycle.snapshot.rx_restart_operations == 3
assert lifecycle.snapshot.post_transmit_failures == 0
assert lifecycle.snapshot.downstream_failures == 0

# A downstream failure is terminal for that frame, is never retried, but the
# lifecycle may continue if RF idle and RX recovery are both proven.
clock = FakeClock()
modem = FakeModem()
submitter = FakeSubmitter(modem)
submitter.fail_next = True
lifecycle = make_lifecycle(modem, submitter, clock)
try:
    lifecycle.submit_frame(b"terminal-failure")
    raise AssertionError("expected downstream failure")
except HalfDuplexDownstreamError:
    pass
assert submitter.calls == 1
assert submitter.accepted_frames == []
assert modem.rx_active is True
assert lifecycle.snapshot.downstream_failures == 1
assert lifecycle.snapshot.recovered_downstream_failures == 1
assert lifecycle.snapshot.failed_latched is False
result = lifecycle.submit_frame(b"different-next-frame")
assert result[0] == "accepted"
assert submitter.calls == 2
assert submitter.accepted_frames == [b"different-next-frame"]
assert lifecycle.snapshot.cycles_completed == 1

# If RX_STOP itself is uncertain, no downstream TX is called and the lifecycle
# latches fail-closed rather than trying another request.
clock = FakeClock()
modem = FakeModem()
modem.fail_rx_stop = True
submitter = FakeSubmitter(modem)
lifecycle = make_lifecycle(modem, submitter, clock)
try:
    lifecycle.submit_frame(b"never-tx")
    raise AssertionError("expected pre-transmit failure")
except HalfDuplexPreTransmitError:
    pass
assert submitter.calls == 0
assert lifecycle.snapshot.pre_transmit_failures == 1
assert lifecycle.snapshot.failed_latched is True
try:
    lifecycle.submit_frame(b"blocked-after-latch")
    raise AssertionError("latched lifecycle accepted another call")
except HalfDuplexLatched:
    pass
assert submitter.calls == 0

# TX accepted + RF never becomes idle is a post-transmit failure. The exact
# frame must not be retried and RX must not be restarted into an active TX.
clock = FakeClock()
modem = FakeModem()
modem.keep_tx_busy = True
submitter = FakeSubmitter(modem)
lifecycle = make_lifecycle(modem, submitter, clock)
try:
    lifecycle.submit_frame(b"accepted-but-stuck")
    raise AssertionError("expected post-transmit timeout")
except HalfDuplexPostTransmitError as exc:
    assert exc.transmission_accepted is True
assert submitter.calls == 1
assert submitter.accepted_frames == [b"accepted-but-stuck"]
assert modem.rx_active is False
assert modem.rx_start_calls == 0
assert lifecycle.snapshot.downstream_accepted == 1
assert lifecycle.snapshot.post_transmit_failures == 1
assert lifecycle.snapshot.failed_latched is True
try:
    lifecycle.submit_frame(b"must-not-retry")
    raise AssertionError("latched post-TX lifecycle accepted another call")
except HalfDuplexLatched:
    pass
assert submitter.calls == 1

# TX accepted + RX_START failure is also latched post-transmit. No duplicate
# dispatch is possible even though the service needs operator reconstruction.
clock = FakeClock()
modem = FakeModem()
modem.fail_rx_start = True
submitter = FakeSubmitter(modem)
lifecycle = make_lifecycle(modem, submitter, clock)
try:
    lifecycle.submit_frame(b"accepted-rx-restart-fails")
    raise AssertionError("expected RX restart failure")
except HalfDuplexPostTransmitError:
    pass
assert submitter.calls == 1
assert submitter.accepted_frames == [b"accepted-rx-restart-fails"]
assert modem.rx_active is False
assert lifecycle.snapshot.downstream_accepted == 1
assert lifecycle.snapshot.post_transmit_failures == 1
assert lifecycle.snapshot.failed_latched is True

print("P4E_HALF_DUPLEX_LIFECYCLE_REGRESSION=PASS")
print("REPEATED_RX_TX_RX_CYCLES=3")
print("DOWNSTREAM_FAILURE_RETRY=NO")
print("DOWNSTREAM_FAILURE_RX_RECOVERY=PASS")
print("PRE_TX_UNCERTAINTY_LATCHES=YES")
print("POST_TX_IDLE_TIMEOUT_LATCHES=YES")
print("POST_TX_RX_RESTART_FAILURE_LATCHES=YES")
print("POST_TX_DUPLICATE_RETRY=IMPOSSIBLE")
print("UART_OPENED=NO")
print("RF_TRANSMITTED=NO")
