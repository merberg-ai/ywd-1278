#!/usr/bin/env python3
"""Contract for the preserved, invalidated 0C-P8 R2 physical run."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware" / "qualification" / "0c-p8-r2-live-physical-evidence.json"


def main() -> int:
    d = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert d["schema"] == 1
    assert d["phase"] == "0C-P8-R2-live"
    assert d["status"] == "invalidated-self-echo-gate"
    assert d["qualification_complete"] is False
    assert d["rerun_same_stage_permitted"] is False
    assert d["execution_head_sha"] == "69eaec38efe6d3ab1f97c1f09d082e04a632567c"
    assert d["frequency_hz"] == 145050000
    assert d["rf_power"] == 200
    assert d["r2_accepted_tx"] == 3
    assert d["external_direct_decode_observed"] == 3
    assert d["external_decode_result"] == "pass"
    assert d["external_decoder_screenshot_sha256"] == "48cb562a7c11c5a20962196f19bd6d6ce9eeb0bdb1f6c21c1f1f18cc3b9f5dde"
    assert [x["packet"] for x in d["external_decoder_observations"]] == [
        "KJ6YWD-10>YWD8,YWDNOD:YWD-1278 P8 SUSTAINED 1/3",
        "KJ6YWD-10>YWD8,YWDNOD:YWD-1278 P8 SUSTAINED 2/3",
        "KJ6YWD-10>YWD8,YWDNOD:YWD-1278 P8 SUSTAINED 3/3",
    ]
    assert d["complete_rx_tx_rx_cycles"] == 3
    assert d["fifo_dropped_bytes"] == 0
    assert d["uart_released"] is True
    assert d["duplicate_dispatch"] is False
    assert d["automatic_tx_retry"] is False
    assert d["subproofs"]["three_external_direct_decodes"] == "pass"
    assert d["subproofs"]["three_rx_stop_tx_rx_restart_cycles"] == "pass"
    assert d["subproofs"]["fresh_non_qualification_rx_gate"] == "invalid"
    assert d["subproofs"]["final_queue_empty_non_qualification_rx_proof"] == "invalid"
    assert d["defect"]["id"] == "P8-R2-SELF-ECHO-CLASSIFIER"
    assert d["defect"]["r2_rerun_forbidden"] is True
    assert d["defect"]["next_stage"] == "0C-P8-R3-live"

    print("P8_R2_PHYSICAL_EVIDENCE=INVALIDATED_PRESERVED")
    print("R2_EXTERNAL_DIRECT_DECODE=PASS_3_OF_3")
    print("R2_HALF_DUPLEX_LIFECYCLE=PASS_3_OF_3")
    print("R2_FRESH_NONQUAL_RX_GATE=INVALID")
    print("R2_RERUN_PERMITTED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
