#!/usr/bin/env python3
"""Regression for the R2 raw-body self-echo classification defect."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(TOOLS))

import qualify_live_p8_r3_sustained_kiss_tnc as r3  # noqa: E402


def toggle_ch_bits(body: bytes) -> bytes:
    """Change only destination/source/path C/H bits in a 3-address UI body."""

    out = bytearray(body)
    # SSID octets for destination, source, and first path address.
    for offset in (6, 13, 20):
        out[offset] ^= 0x80
    return bytes(out)


def main() -> int:
    r3.install_r3_overrides()
    stage = json.loads(r3.R3_STAGE_PATH.read_text(encoding="utf-8"))
    vectors = r3.base.build_vectors(stage)
    locked = tuple(body for body, _frame in vectors)

    # Exact locally-built bodies remain qualification frames.
    for body in locked:
        assert r3.semantic_is_qualification_body(body, locked)

    # Reproduce the R2 failure mode: raw bytes differ solely because AX.25 C/H
    # bits changed after an RF trip, yet semantic identity must remain P8.
    for body in locked:
        heard = toggle_ch_bits(body)
        assert heard != body
        assert not r3.base.is_qualification_body.__name__ == "is_qualification_body"
        assert r3.semantic_frame_key(heard) == r3.semantic_frame_key(body)
        assert r3.semantic_is_qualification_body(heard, locked)

    # Exercise the real guard after R3 overrides. A C/H-mutated P8 echo must not
    # arm fresh_non_qualification_decode or increment non-qualification counts.
    guard = r3.base.PhysicalCycleGuard(
        qualification_bodies=locked,
        busy_raw_maximum=83,
    )
    guard.arm(1)
    guard.note_inbound(toggle_ch_bits(locked[0]))
    snap = guard.snapshot
    assert snap.fresh_non_qualification_decode is False
    assert snap.non_qualification_decodes == 0
    assert guard.total_non_qualification_decodes == 0

    # A genuinely different packet must still arm the gate.
    nonqual = r3.base.build_ui_frame(
        source=r3.base.Address.parse("KJ6YWD"),
        destination=r3.base.Address.parse("JIM"),
        path=[r3.base.Address.parse("KRDG")],
        info=b"P8 R3 REAL NONQUAL RX PROOF",
        include_fcs=False,
    )
    assert not r3.semantic_is_qualification_body(nonqual, locked)
    guard.note_inbound(nonqual)
    snap = guard.snapshot
    assert snap.fresh_non_qualification_decode is True
    assert snap.non_qualification_decodes == 1
    assert guard.total_non_qualification_decodes == 1

    # Same R3 information text with a different destination is not silently
    # suppressed; source/destination/path are part of semantic identity.
    same_info_other_dest = r3.base.build_ui_frame(
        source=r3.base.Address.parse("KJ6YWD-10"),
        destination=r3.base.Address.parse("JIM"),
        path=[r3.base.Address.parse("YWDNOD")],
        info=stage["frames"][0]["information_text"].encode("ascii"),
        include_fcs=False,
    )
    assert not r3.semantic_is_qualification_body(same_info_other_dest, locked)

    print("P8_R3_SEMANTIC_ECHO_FILTER=PASS")
    print("R2_RAW_BODY_DEFECT_REPRODUCED=PASS")
    print("DEST_SOURCE_PATH_CH_BITS_IGNORED=PASS")
    print("QUALIFICATION_ECHO_ARMS_FRESH_RX=NO")
    print("GENUINE_NONQUAL_PACKET_ARMS_FRESH_RX=YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
