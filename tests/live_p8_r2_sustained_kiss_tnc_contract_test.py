#!/usr/bin/env python3
"""Static/dry-run contract for guarded 0C-P8 R2 physical qualification."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tools" / "qualify_live_p8_r2_sustained_kiss_tnc.py"
BASE_HARNESS = ROOT / "tools" / "qualify_live_p8_sustained_kiss_tnc.py"
R2_MANIFEST = ROOT / "firmware" / "qualification" / "0c-p8-r2-live-sustained-kiss-tnc.json"
OLD_MANIFEST = ROOT / "firmware" / "qualification" / "0c-p8-live-sustained-kiss-tnc.json"


def git_blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True).strip()


def main() -> int:
    r2 = json.loads(R2_MANIFEST.read_text(encoding="utf-8"))
    old = json.loads(OLD_MANIFEST.read_text(encoding="utf-8"))
    wrapper = WRAPPER.read_text(encoding="utf-8")
    base = BASE_HARNESS.read_text(encoding="utf-8")

    assert old["status"] == "superseded"
    assert old["runnable"] is False
    assert old["superseded_by"] == "0C-P8-R2-live"

    assert r2["schema"] == 1
    assert r2["phase"] == "0C-P8-R2-live"
    assert r2["stage"] == "sustained-kiss-three-cycle-r2"
    assert r2["status"] == "staged"
    assert r2["base_checkpoint"] == "checkpoint/0c-p8-sustained-kiss-tnc-r1-host-qualified"
    assert r2["base_checkpoint_sha"] == "e8d104b2c6a295219e34733d2541f89ee90318f3"
    assert r2["supersedes_physical_stage_sha"] == "6b54fa8b3797ea5bc6faeadd911149b6d9dc8ae7"
    assert r2["attempt1_accepted_tx"] == 0
    assert r2["reuse_attempt1_vectors_safe"] is True
    assert r2["host_r1_bounded_live_fifo_drain_required"] is True
    assert r2["host_r1_tnc_runtime_blob"] == "f1a74ae44824bafc2b89c09e77fa416ac26bb4f1"
    assert r2["frequency_hz"] == 145050000
    assert r2["rf_power"] == 200
    assert r2["packet_count"] == 3
    assert r2["txdelay_sequence"] == [30, 50, 30]
    assert r2["persist"] == 63
    assert r2["slottime"] == 10
    assert r2["rx_read_maximum"] == 200
    assert r2["rx_fifo_drain_read_limit"] == 4
    assert r2["rx_fifo_drain_maximum_bytes_per_pass"] == 800
    assert r2["rx_fifo_zero_length_read_required"] is False
    assert r2["automatic_tx_retry"] is False
    assert r2["health_checked_while_waiting_for_dispatch"] is True
    assert r2["timeout_diagnostics_include_guard_runtime_queue"] is True
    assert r2["live_rx_decode_visibility_required"] is True
    assert r2["confirmation_token"] == "P8-R2-LIVE-145050-P200-SUSTAINED-3"
    assert r2["interactive_phrase"] == "TRANSMIT-P8-R2-SUSTAINED-KISS-THREE"
    assert r2["maximum_transmit_submissions"] == 3
    assert r2["product_tx_enabled"] is False
    assert r2["daemon_tx_enabled"] is False
    assert r2["systemd_tx_enabled"] is False
    assert r2["flash_permitted"] is False
    assert r2["gpio_reset_permitted"] is False
    assert r2["option_bytes_permitted"] is False

    # The corrected R1 scheduler and preserved attempt-1 physical implementation
    # are both exact hash anchors. R2 is a diagnostic/safety wrapper, not a fork
    # of the physical KISS/CSMA/half-duplex logic.
    assert git_blob("src/ywd1278/service/tnc_runtime.py") == "f1a74ae44824bafc2b89c09e77fa416ac26bb4f1"
    assert git_blob("tools/qualify_live_p8_sustained_kiss_tnc.py") == "30a4b92162d0c4a7560424694f41cd32ad7bcd9f"

    for required in (
        "import qualify_live_p8_sustained_kiss_tnc as base",
        "base.load_stage = load_r2_stage",
        "base.QualificationBackend = DiagnosticQualificationBackend",
        "base.verify_cycle = health_aware_verify_cycle",
        "runtime.check_health()",
        "P8_R2_RX_FRAME",
        "P8_R2_WAIT",
        "accounting.queue.tx_queue_depth",
        "guard={snap}",
        "runtime={counters}",
        "queue={accounting.queue}",
        "ingress={accounting.ingress}",
        "control={accounting.control}",
        "R1_TNC_RUNTIME_BLOB",
        "git_blob(\"src/ywd1278/service/tnc_runtime.py\")",
        "P8_R2_ATTEMPT1_ACCEPTED_TX=0",
    ):
        assert required in wrapper, required
    assert "accounting.queue.queue_depth" not in wrapper

    # Health must be checked inside the active dispatch wait, before dispatch is
    # accepted. This specifically prevents attempt 1's masked worker failure.
    wait_start = wrapper.index("while time.monotonic() < deadline:")
    wait_end = wrapper.index("else:", wait_start)
    wait_body = wrapper[wait_start:wait_end]
    assert wait_body.index("runtime.check_health()") < wait_body.index("if snap.dispatched")
    assert "next_report" in wait_body

    # Wrapper cannot expose new RF/frame/count/retry knobs and cannot bypass the
    # preserved physical graph with raw modem operations.
    assert "argparse" not in wrapper
    for forbidden in (
        "--frequency",
        "--freq",
        "--power",
        "--payload",
        "--frame",
        "--source",
        "--destination",
        "--path",
        "--count",
        "--retry",
        ".transmit_selector_burst(",
        ".transact(",
        "rf_abort(",
        "rf_exit(",
        "stm32flash",
        "RPi.GPIO",
        "/sys/class/gpio",
        "gpiozero",
        "flash.sh",
        "restore-stock",
    ):
        assert forbidden not in wrapper, forbidden

    # The preserved base harness remains exactly the two-switch fixed harness.
    assert base.count("ap.add_argument(") == 2
    assert 'ap.add_argument("--transmit"' in base
    assert 'ap.add_argument("--confirm"' in base

    # Old attempt-1 entrypoint must fail closed before it can get past manifest
    # validation. It is intentionally no longer a runnable dry-run on R2.
    old_run = subprocess.run(
        [sys.executable, str(BASE_HARNESS)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
    )
    assert old_run.returncode != 0
    assert "P8-live staging mismatch for status" in old_run.stdout
    assert "HARDWARE_UART_OPENED" not in old_run.stdout

    # R2 default invocation remains fully inert and validates the corrected R1
    # blob plus all locked vectors before returning.
    dry = subprocess.run(
        [sys.executable, str(WRAPPER)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=15,
        check=True,
    )
    for token in (
        "P8_R2_HARNESS=ACTIVE",
        "P8_R2_BASE_CHECKPOINT=checkpoint/0c-p8-sustained-kiss-tnc-r1-host-qualified",
        "P8_R2_ATTEMPT1_ACCEPTED_TX=0",
        "P8_R2_LIVE_RX_DIAGNOSTICS=ENABLED",
        "P8_LIVE_SUSTAINED_KISS_DRY_RUN=PASS",
        "TX_MODEM_OWNER_CONSTRUCTED=NO",
        "KISS_LISTENER_OPENED=NO",
        "HARDWARE_UART_OPENED=NO",
        "RF_TRANSMITTED=NO",
        "P8_R2_WRAPPER_RESULT=PASS",
    ):
        assert token in dry.stdout, (token, dry.stdout)

    print("P8_R2_LIVE_SUSTAINED_KISS_CONTRACT=PASS")
    print("ATTEMPT1_ENTRYPOINT=FAIL_CLOSED")
    print("R1_CONTINUOUS_RX_DRAIN_HASH=PASS")
    print("PRESERVED_PHYSICAL_HARNESS_HASH=PASS")
    print("DISPATCH_WAIT_RUNTIME_HEALTH=CONTINUOUS")
    print("LIVE_RX_OPERATOR_VISIBILITY=PASS")
    print("QUEUE_ACCOUNTING_FIELD=TX_QUEUE_DEPTH")
    print("R2_DRY_RUN_NO_UART_RF=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
