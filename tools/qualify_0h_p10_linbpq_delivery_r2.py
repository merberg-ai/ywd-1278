#!/usr/bin/env python3
"""0H-P10 R2 physical harness with stop-and-wait RF turnaround policy.

The original P10 physical attempt proved live LinBPQ submission through /EX, but
its MAXFRAME=4 burst could miss the peer's immediate post-submission response on
the half-duplex Bell-202 path.  R2 leaves the frozen P9 dialogue and all bytes
unchanged and only serializes connected I frames: at most one is outstanding on
RF at a time.
"""
from __future__ import annotations

from collections import deque
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import qualify_0h_p10_linbpq_delivery as p10  # noqa: E402
from ywd1278.link.modulo8 import LinkState  # noqa: E402
from ywd1278.link.timed_link import TimedLinkResult  # noqa: E402


_OriginalTimedModulo8DataLink = p10.TimedModulo8DataLink
_original_print_plan = p10.print_plan


class StopAndWaitTimedModulo8DataLink:
    """Compatibility adapter that releases exactly one queued I frame per ACK."""

    def __init__(
        self,
        *,
        local,
        remote,
        maxframe: int = 4,
        paclen: int = 128,
        timers,
    ) -> None:
        # R2 intentionally ignores the caller's larger window.  The live RF path
        # is half-duplex Bell-202 and must turn around between connected frames.
        self._inner = _OriginalTimedModulo8DataLink(
            local=local,
            remote=remote,
            maxframe=1,
            paclen=paclen,
            timers=timers,
        )
        self._queued: deque[bytes] = deque()
        self.requested_maxframe = maxframe

    @property
    def snapshot(self):  # type: ignore[no-untyped-def]
        return self._inner.snapshot

    @property
    def queued_count(self) -> int:
        return len(self._queued)

    def connect(self, *, now: float) -> TimedLinkResult:
        return self._inner.connect(now=now)

    def disconnect(self, *, now: float) -> TimedLinkResult:
        if self._queued:
            return TimedLinkResult(False, "stop-and-wait queue is not empty")
        return self._inner.disconnect(now=now)

    def set_local_busy(self, busy: bool, *, now: float) -> TimedLinkResult:
        return self._inner.set_local_busy(busy, now=now)

    def send_information(self, info: bytes, *, now: float) -> TimedLinkResult:
        if self._queued or self._inner.snapshot.link.outstanding:
            self._queued.append(bytes(info))
            return TimedLinkResult(
                True,
                f"stop-and-wait payload queued; depth={len(self._queued)}",
            )
        return self._inner.send_information(info, now=now)

    def handle_frame(self, frame_no_fcs: bytes, *, now: float) -> TimedLinkResult:
        result = self._inner.handle_frame(frame_no_fcs, now=now)
        return self._release_one_if_ready(result, now=now)

    def poll(self, *, now: float) -> TimedLinkResult:
        result = self._inner.poll(now=now)
        return self._release_one_if_ready(result, now=now)

    def _release_one_if_ready(
        self,
        result: TimedLinkResult,
        *,
        now: float,
    ) -> TimedLinkResult:
        if not result.accepted:
            return result
        if not self._queued:
            return result
        snap = self._inner.snapshot.link
        if snap.state is not LinkState.CONNECTED or snap.outstanding:
            return result

        payload = self._queued.popleft()
        released = self._inner.send_information(payload, now=now)
        if not released.accepted:
            return TimedLinkResult(
                False,
                f"{result.reason}; queued stop-and-wait send failed: {released.reason}",
                result.actions,
                result.delivered,
            )
        return TimedLinkResult(
            True,
            f"{result.reason}; released one stop-and-wait payload",
            result.actions + released.actions,
            result.delivered,
        )


def _r2_print_plan() -> None:
    _original_print_plan()
    print("P10_HARNESS_REVISION=R2")
    print("RF_LINK_POLICY=STOP_AND_WAIT_MAXFRAME_1")
    print("P10_R2_TURNAROUND_GUARD=YES")


def main() -> int:
    # Patch only the P10 physical driver boundary.  P9 dialogue, work item,
    # authorization, RF profile, cleanup, and pass criteria remain unchanged.
    p10.TimedModulo8DataLink = StopAndWaitTimedModulo8DataLink
    p10.print_plan = _r2_print_plan
    return p10.main()


if __name__ == "__main__":
    raise SystemExit(main())
