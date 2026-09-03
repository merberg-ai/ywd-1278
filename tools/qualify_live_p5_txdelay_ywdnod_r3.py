#!/usr/bin/env python3
"""Final 0C-P5 guarded live TXDELAY qualification VIA YWDNOD.

This narrow wrapper uses the reviewed R2 physical lifecycle while replacing
qualification-frame classification with semantic AX.25 matching.  A YWDNOD
repeat changes the repeater/H bit and FCS, so byte equality alone is not enough
to prevent our own returned qualification traffic from authorizing a later TX.

Both direct and digipeated copies of the two fixed P5 packets are therefore
recognized by source, destination, and exact information field.  They remain
visible to the decoder but cannot satisfy pre-TX trigger or final RX-proof
requirements.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(TOOLS))

import qualify_live_p5_txdelay_ywdnod_r2 as r2  # noqa: E402

from ywd1278.ax25 import parse_frame as parse_ax25_frame  # noqa: E402


QUALIFICATION_SOURCE = "KJ6YWD-10"
QUALIFICATION_DESTINATION = "YWD5TD"
QUALIFICATION_INFO = {
    b"YWD-1278 P5 TXDELAY 300MS 1/2",
    b"YWD-1278 P5 TXDELAY 500MS 2/2",
}


def semantic_qualification_frame(frame: bytes, _direct_frames: set[bytes]) -> bool:
    """Match direct or repeated P5 qualification traffic independent of H/FCS."""

    parsed = parse_ax25_frame(frame, has_fcs=True)
    return (
        str(parsed["source"]) == QUALIFICATION_SOURCE
        and str(parsed["destination"]) == QUALIFICATION_DESTINATION
        and bytes(parsed["info"]) in QUALIFICATION_INFO
    )


def main() -> int:
    r2.is_qualification_frame = semantic_qualification_frame
    return r2.main()


if __name__ == "__main__":
    raise SystemExit(main())
