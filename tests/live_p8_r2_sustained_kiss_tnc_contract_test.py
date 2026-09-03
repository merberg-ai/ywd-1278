#!/usr/bin/env python3
"""Historical safety contract for the invalidated 0C-P8 R2 physical stage."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tools" / "qualify_live_p8_r2_sustained_kiss_tnc.py"
MANIFEST = ROOT / "firmware" / "qualification" / "0c-p8-r2-live-sustained-kiss-tnc.json"
EVIDENCE = ROOT / "firmware" / "qualification" / "0c-p8-r2-live-physical-evidence.json"


def main() -> int:
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    e = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert m["phase"] == "0C-P8-R2-live"
    assert m["status"] == "invalidated-self-echo-gate"
    assert m["runnable"] is False
    assert m["superseded_by"] == "0C-P8-R3-live"
    assert m["r2_accepted_tx"] == 3
    assert m["r2_rerun_permitted"] is False
    assert m["invalidated_by"] == "P8-R2-SELF-ECHO-CLASSIFIER"

    assert e["status"] == "invalidated-self-echo-gate"
    assert e["qualification_complete"] is False
    assert e["rerun_same_stage_permitted"] is False
    assert e["r2_accepted_tx"] == 3
    assert e["external_direct_decode_observed"] == 3
    assert e["subproofs"]["three_external_direct_decodes"] == "pass"
    assert e["subproofs"]["three_rx_stop_tx_rx_restart_cycles"] == "pass"
    assert e["subproofs"]["fresh_non_qualification_rx_gate"] == "invalid"

    # The superseded R2 entrypoint must die during manifest validation before
    # opening UART or transmitting. Its old token is intentionally unusable.
    run = subprocess.run(
        [sys.executable, str(WRAPPER)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=15,
    )
    assert run.returncode != 0, run.stdout
    assert "P8-R2 staging mismatch for status" in run.stdout, run.stdout
    assert "KISS_LISTENER=" not in run.stdout
    assert "LIVE_RUNTIME=OPEN" not in run.stdout
    assert "RF_TRANSMITTED=YES" not in run.stdout

    print("P8_R2_HISTORICAL_STAGE=INVALIDATED_PRESERVED")
    print("R2_ACCEPTED_TX=3")
    print("R2_EXTERNAL_DIRECT_DECODE=PASS_3_OF_3")
    print("R2_FRESH_NONQUAL_RX_GATE=INVALID")
    print("R2_ENTRYPOINT=FAIL_CLOSED")
    print("R2_RERUN_PERMITTED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
