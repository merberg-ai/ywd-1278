#!/usr/bin/env python3
"""Guarded 0C-P8 R2 sustained KISS physical qualification.

R2 intentionally wraps the preserved attempt-1 physical harness instead of
forking its radio/KISS/half-duplex logic.  The only behavioral additions are:

* load a new R2 manifest rooted at the host-qualified P8 R1 checkpoint;
* require the corrected R1 sustained-runtime git blob;
* use a new R2 CLI confirmation token and interactive phrase;
* surface every decoded live RX frame to the operator;
* check SustainedTNCRuntime health continuously while waiting for each dispatch;
* print bounded progress diagnostics during that wait and include guard/runtime/
  queue state in any timeout.

The underlying three fixed vectors, KISS ingress, P2/P1 CSMA policy, P4e
half-duplex lifecycle, P5 TXDELAY routing, modem owner, and RF profile remain the
preserved physical harness implementation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import qualify_live_p8_sustained_kiss_tnc as base  # noqa: E402


R2_STAGE_PATH = ROOT / "firmware" / "qualification" / "0c-p8-r2-live-sustained-kiss-tnc.json"
R2_CONFIRMATION_TOKEN = "P8-R2-LIVE-145050-P200-SUSTAINED-3"
R2_INTERACTIVE_CONFIRMATION = "TRANSMIT-P8-R2-SUSTAINED-KISS-THREE"
R1_TNC_RUNTIME_BLOB = "f1a74ae44824bafc2b89c09e77fa416ac26bb4f1"
R1_CHECKPOINT = "checkpoint/0c-p8-sustained-kiss-tnc-r1-host-qualified"
R1_CHECKPOINT_SHA = "e8d104b2c6a295219e34733d2541f89ee90318f3"


def git_blob(path: str) -> str:
    return subprocess.check_output(
        ["git", "hash-object", path], cwd=ROOT, text=True
    ).strip()


def load_r2_stage() -> dict:
    stage = json.loads(R2_STAGE_PATH.read_text(encoding="utf-8"))
    required = {
        "schema": 1,
        "phase": "0C-P8-R2-live",
        "stage": "sustained-kiss-three-cycle-r2",
        "status": "staged",
        "base_checkpoint": R1_CHECKPOINT,
        "base_checkpoint_sha": R1_CHECKPOINT_SHA,
        "supersedes_physical_stage_sha": "6b54fa8b3797ea5bc6faeadd911149b6d9dc8ae7",
        "attempt1_accepted_tx": 0,
        "reuse_attempt1_vectors_safe": True,
        "host_r1_bounded_live_fifo_drain_required": True,
        "host_r1_tnc_runtime_blob": R1_TNC_RUNTIME_BLOB,
        "target_id": base.p4d_r1.TARGET_ID,
        "device": base.p4d_r1.DEVICE,
        "expected_identity": (
            "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz "
            "ADF7021 FW based on CA6JAU GitID #7ff74ed"
        ),
        "frequency_hz": 145050000,
        "rf_power": 200,
        "packet_count": 3,
        "source": "KJ6YWD-10",
        "destination": "YWD8",
        "path": ["YWDNOD"],
        "kiss_listener_host": "127.0.0.1",
        "kiss_listener_port": 0,
        "kiss_listener_ephemeral": True,
        "kiss_client_sessions_required": 2,
        "kiss_client_reconnect_required": True,
        "kiss_data_payload_includes_fcs": False,
        "tnc_appends_fcs_exactly_once": True,
        "kiss_port": 0,
        "parameter_generations": [3, 4, 5],
        "persist": 63,
        "slottime": 10,
        "fullduplex": 0,
        "txdelay_sequence": [30, 50, 30],
        "request_timeout_seconds": 30.0,
        "downstream_timeout_seconds": 1.5,
        "rssi_poll_nominal_seconds": 0.05,
        "rx_status_interval_seconds": 0.25,
        "rx_read_maximum": 200,
        "rx_fifo_drain_read_limit": 4,
        "rx_fifo_drain_maximum_bytes_per_pass": 800,
        "rx_fifo_zero_length_read_required": False,
        "busy_assert_raw_maximum": 83,
        "clear_release_raw_minimum": 90,
        "recent_rx_hold_seconds": 0.25,
        "requires_live_busy_before_each_dispatch": True,
        "requires_fresh_non_qualification_fcs_valid_rx_before_each_tx": True,
        "minimum_full_slot_seconds": 0.1,
        "requires_rx_fifo_drained_before_tx_access": True,
        "requires_rx_active_after_each_tx": True,
        "rx_fifo_dropped_bytes_required": 0,
        "requires_final_queue_empty_fcs_valid_rx": True,
        "requires_final_queue_empty_kiss_delivery": True,
        "final_receive_timeout_seconds": 60.0,
        "required_non_qualification_inbound_frames": 4,
        "qualification_echo_must_not_count_as_rx_proof": True,
        "maximum_transmit_submissions": 3,
        "automatic_tx_retry": False,
        "health_checked_while_waiting_for_dispatch": True,
        "timeout_diagnostics_include_guard_runtime_queue": True,
        "live_rx_decode_visibility_required": True,
        "requires_direct_external_decode": True,
        "required_external_tx_decodes": 3,
        "require_ywdnod_repeated_decode": False,
        "confirmation_token": R2_CONFIRMATION_TOKEN,
        "interactive_phrase": R2_INTERACTIVE_CONFIRMATION,
        "product_tx_enabled": False,
        "daemon_tx_enabled": False,
        "systemd_tx_enabled": False,
        "flash_permitted": False,
        "gpio_reset_permitted": False,
        "option_bytes_permitted": False,
    }
    for key, expected in required.items():
        actual = stage.get(key)
        if actual != expected:
            raise SystemExit(
                f"FAIL: P8-R2 staging mismatch for {key}: expected={expected!r} actual={actual!r}"
            )
    if stage.get("qualification_randomness") != {
        "before_fresh_decoded_busy_trigger": 255,
        "after_fresh_decoded_busy_trigger": [255, 0],
    }:
        raise SystemExit("FAIL: P8-R2 qualification randomness changed")
    if len(stage.get("frames", [])) != 3:
        raise SystemExit("FAIL: P8-R2 requires exactly three locked frame vectors")

    actual_blob = git_blob("src/ywd1278/service/tnc_runtime.py")
    if actual_blob != R1_TNC_RUNTIME_BLOB:
        raise SystemExit(
            "FAIL: P8-R2 corrected sustained runtime blob mismatch: "
            f"expected={R1_TNC_RUNTIME_BLOB} actual={actual_blob}"
        )

    # Reuse the original vector builder so every body/FCS/selector/sample hash
    # remains locked to the same proven physical serialization.
    base.build_vectors(stage)
    return stage


class DiagnosticQualificationBackend(base.QualificationBackend):
    """The original backend plus operator-visible decoded-frame evidence."""

    def publish(self, event: base.PacketEvent) -> None:
        super().publish(event)
        snap = self._guard.snapshot
        print(
            "P8_R2_RX_FRAME "
            f"source={event.source} destination={event.destination} "
            f"type={event.frame_type} body_bytes={len(event.frame_no_fcs)} "
            f"cycle={snap.cycle} fresh_non_p8={int(snap.fresh_non_qualification_decode)} "
            f"non_p8_total={snap.non_qualification_decodes}",
            flush=True,
        )


_ORIGINAL_VERIFY_CYCLE = base.verify_cycle


def health_aware_verify_cycle(
    *,
    cycle: int,
    guard: base.PhysicalCycleGuard,
    expected_generation: int,
    expected_txdelay: int,
    expected_samples: int,
    runtime: base.SustainedTNCRuntime,
    owner: base.TXModemOwner,
) -> base.CycleSnapshot:
    deadline = time.monotonic() + 29.0
    next_report = time.monotonic()
    while time.monotonic() < deadline:
        # Attempt 1 checked health only after successful dispatch. R2 checks it
        # throughout the wait so a worker failure surfaces immediately instead
        # of being hidden behind a generic 29-second timeout.
        runtime.check_health()
        snap = guard.snapshot
        counters = runtime.runtime_counters
        if snap.dispatched and counters.tx_dispatches >= cycle:
            break

        now = time.monotonic()
        if now >= next_report:
            accounting = runtime.accounting
            print(
                f"P8_R2_WAIT cycle={cycle} "
                f"rx_reads={counters.rx_read_transactions} "
                f"packed_rx={counters.packed_rx_bytes} "
                f"decoded_rx={counters.decoded_rx_frames} "
                f"rssi={counters.rssi_samples} "
                f"queue_depth={accounting.queue.queue_depth} "
                f"seen_busy={int(snap.seen_busy)} "
                f"fresh_non_p8={int(snap.fresh_non_qualification_decode)} "
                f"post_trials={snap.post_trigger_trials}",
                flush=True,
            )
            next_report = now + 2.0
        time.sleep(0.01)
    else:
        runtime.check_health()
        snap = guard.snapshot
        counters = runtime.runtime_counters
        accounting = runtime.accounting
        raise RuntimeError(
            f"timed out waiting for cycle {cycle} guarded sustained TX; "
            f"guard={snap}; runtime={counters}; queue={accounting.queue}; "
            f"ingress={accounting.ingress}; control={accounting.control}"
        )

    # The preserved verifier now sees an already-dispatched cycle and performs
    # all original immutable-parameter, CSMA timing, RX restart, and RF
    # diagnostic checks without changing those qualification semantics.
    return _ORIGINAL_VERIFY_CYCLE(
        cycle=cycle,
        guard=guard,
        expected_generation=expected_generation,
        expected_txdelay=expected_txdelay,
        expected_samples=expected_samples,
        runtime=runtime,
        owner=owner,
    )


def install_r2_overrides() -> None:
    base.CONFIRMATION_TOKEN = R2_CONFIRMATION_TOKEN
    base.INTERACTIVE_CONFIRMATION = R2_INTERACTIVE_CONFIRMATION
    base.load_stage = load_r2_stage
    base.QualificationBackend = DiagnosticQualificationBackend
    base.verify_cycle = health_aware_verify_cycle


def main() -> int:
    install_r2_overrides()
    print("P8_R2_HARNESS=ACTIVE", flush=True)
    print(f"P8_R2_BASE_CHECKPOINT={R1_CHECKPOINT}", flush=True)
    print(f"P8_R2_BASE_SHA={R1_CHECKPOINT_SHA}", flush=True)
    print("P8_R2_ATTEMPT1_ACCEPTED_TX=0", flush=True)
    print("P8_R2_LIVE_RX_DIAGNOSTICS=ENABLED", flush=True)
    rc = base.main()
    if rc == 0:
        print("P8_R2_WRAPPER_RESULT=PASS", flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
