#!/usr/bin/env python3
"""0H-P10 R3 physical harness for LinBPQ large-response acceptance.

R1 proved live delivery through /EX but waited forever for the returned BBS
prompt. R2 serialized outbound I frames with stop-and-wait; the same symptom
remained. Live LinBPQ logs prove the post-/EX application response is produced,
and LinBPQ is known to emit connected-mode information frames larger than the
P10 harness's historical PACLEN=128 receive bound.

R3 preserves the R2 stop-and-wait transmit policy and every frozen P9 byte, but
uses PACLEN=256 at the AX.25 link boundary so a standards-bounded LinBPQ inbound
I frame up to 256 information bytes can be accepted. P10's _submit_information
function still independently caps every outbound information payload at 128
bytes, so this revision only widens what the physical qualification harness may
receive, not what it may transmit.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import qualify_0h_p10_linbpq_delivery as p10  # noqa: E402
import qualify_0h_p10_linbpq_delivery_r2 as r2  # noqa: E402
from ywd1278.ax25 import parse_frame  # noqa: E402


LINK_RECEIVE_PACLEN = 256


class LinBPQReceive256StopAndWait(r2.StopAndWaitTimedModulo8DataLink):
    """R2 stop-and-wait adapter with a 256-byte connected receive PACLEN."""

    def __init__(
        self,
        *,
        local,
        remote,
        maxframe: int = 4,
        paclen: int = 128,
        timers,
    ) -> None:
        self.requested_paclen = paclen
        super().__init__(
            local=local,
            remote=remote,
            maxframe=maxframe,
            paclen=LINK_RECEIVE_PACLEN,
            timers=timers,
        )

    @property
    def effective_paclen(self) -> int:
        return self._inner.snapshot.link.paclen

    def handle_frame(self, frame_no_fcs: bytes, *, now: float):  # type: ignore[no-untyped-def]
        result = super().handle_frame(frame_no_fcs, now=now)
        if not result.accepted:
            detail = "unparsed"
            try:
                parsed = parse_frame(bytes(frame_no_fcs), has_fcs=False)
                detail = (
                    f"type={parsed['frame_type']} class={parsed['frame_class']} "
                    f"info_len={len(parsed['info'])} "
                    f"ns={parsed.get('ns')} nr={parsed.get('nr')}"
                )
            except (TypeError, ValueError):
                pass
            print(f"P10_R3_RX_REJECTED={detail} reason={result.reason}")
        return result


_original_print_plan = p10.print_plan


def _r3_print_plan() -> None:
    _original_print_plan()
    print("P10_HARNESS_REVISION=R3")
    print("RF_LINK_POLICY=STOP_AND_WAIT_MAXFRAME_1")
    print(f"LINK_RECEIVE_PACLEN={LINK_RECEIVE_PACLEN}")
    print("OUTBOUND_INFORMATION_MAX=128")
    print("P10_R3_LINBPQ_LARGE_RESPONSE_GUARD=YES")


def main() -> int:
    # Patch only the P10 physical link adapter. Frozen P9 dialogue, prepared work,
    # authorization, RF profile, cleanup, and acceptance criteria are unchanged.
    p10.TimedModulo8DataLink = LinBPQReceive256StopAndWait
    p10.print_plan = _r3_print_plan
    return p10.main()


if __name__ == "__main__":
    raise SystemExit(main())
