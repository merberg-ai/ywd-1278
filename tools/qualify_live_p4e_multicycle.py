#!/usr/bin/env python3
"""0C-P4e guarded physical persistent half-duplex multi-cycle qualification.

This is a fixed-vector qualification harness, not a transmitter UI. It proves
that the host-qualified P4e lifecycle survives repeated real half-duplex cycles:

    live RX -> decoded inbound BUSY -> qualified CSMA -> RX_STOP -> fixed TX
            -> RF idle -> RX_START -> live RX again

Three fixed outgoing frames are permitted. Before each one, the restarted RX
path must independently decode a fresh FCS-valid AX.25 frame and observe live
BUSY. After the third TX/restart, one additional FCS-valid inbound frame must be
decoded while no TX request exists. Independent over-air decoding of all three
outgoing frames is required before the phase can be promoted.

Default invocation is dry-run and exits before TXModemOwner construction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(TOOLS))

import qualify_live_csma_single_tx as p4d_r1  # noqa: E402

from ywd1278.ax25 import Address, build_ui_frame, parse_frame as parse_ax25_frame, verify_fcs  # noqa: E402
from ywd1278.modem._serial import posix_serial_transport_factory  # noqa: E402
from ywd1278.modem.tx_owner import TXModemOwner  # noqa: E402
from ywd1278.phy import MARK, frame_to_selectors, pack_selectors  # noqa: E402
from ywd1278.phy.bell202_rx import StreamingBell202Decoder  # noqa: E402
from ywd1278.tx.access_queue import AccessRequestState, BoundedChannelAccessQueue  # noqa: E402
from ywd1278.tx.broker import TXBroker, TXReceipt  # noqa: E402
from ywd1278.tx.channel_busy import ChannelBusyState  # noqa: E402
from ywd1278.tx.csma import CSMAState  # noqa: E402
from ywd1278.tx.half_duplex import HalfDuplexParameters, PersistentHalfDuplexSubmitter  # noqa: E402


STAGE_PATH = ROOT / "firmware" / "qualification" / "0c-p4e-live-multicycle.json"
CONFIRMATION_TOKEN = "P4E-LIVE-145050-P200-MULTICYCLE-3"
INTERACTIVE_CONFIRMATION = "TRANSMIT-P4E-LIVE-THREE-CYCLES"
ACTIVE_RX_REQUIRED_MASK = 0x0D
TX_FLAG = 0x02


def load_stage() -> dict:
    stage = json.loads(STAGE_PATH.read_text(encoding="utf-8"))
    required = {
        "schema": 1,
        "phase": "0C-P4e-live",
        "status": "staged",
        "base_checkpoint": "checkpoint/0c-p4e-persistent-half-duplex-host-qualified",
        "base_checkpoint_sha": "0257f9947aea60d943b6b6b52e2ad7d9e28766de",
        "target_id": p4d_r1.TARGET_ID,
        "device": p4d_r1.DEVICE,
        "expected_identity": (
            "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz "
            "ADF7021 FW based on CA6JAU GitID #7ff74ed"
        ),
        "frequency_hz": 145050000,
        "rf_power": 200,
        "cycles": 3,
        "per_cycle_access_timeout_seconds": 30.0,
        "final_post_tx_receive_timeout_seconds": 60.0,
        "rssi_poll_seconds": 0.05,
        "rx_status_interval_seconds": 0.25,
        "rx_read_maximum": 200,
        "source": "KJ6YWD-10",
        "destination": "YWD4E",
        "pre_flags": 45,
        "post_flags": 3,
        "initial_tone": "MARK",
        "samples_per_selector": 16,
        "requires_fresh_fcs_valid_rx_trigger_before_each_tx": True,
        "required_pre_tx_decoded_frames": 3,
        "requires_final_fcs_valid_rx_after_cycle_3_restart": True,
        "required_total_inbound_decoded_frames": 4,
        "requires_live_busy_before_each_tx": True,
        "rx_fifo_dropped_bytes_required": 0,
        "requires_rx_active_after_each_tx": True,
        "requires_external_decode_of_all_outgoing_frames": True,
        "required_external_tx_decodes": 3,
        "maximum_transmit_submissions": 3,
        "automatic_tx_retry": False,
        "confirmation_token": CONFIRMATION_TOKEN,
        "interactive_phrase": INTERACTIVE_CONFIRMATION,
        "kiss_tx_connected": False,
        "product_tx_enabled": False,
        "flash_permitted": False,
        "gpio_reset_permitted": False,
        "option_bytes_permitted": False,
    }
    for key, expected in required.items():
        if stage.get(key) != expected:
            raise SystemExit(
                f"FAIL: P4e-live staging mismatch for {key}: "
                f"expected={expected!r} actual={stage.get(key)!r}"
            )
    if stage.get("qualification_randomness") != {
        "before_fresh_decoded_busy_trigger": 255,
        "after_fresh_decoded_busy_trigger": [255, 0],
    }:
        raise SystemExit("FAIL: P4e-live qualification randomness changed")
    if len(stage.get("frames", [])) != 3:
        raise SystemExit("FAIL: P4e-live must contain exactly three fixed frames")
    return stage


def build_vectors(stage: dict) -> list[bytes]:
    frames: list[bytes] = []
    for index, vector in enumerate(stage["frames"], start=1):
        if vector.get("cycle") != index:
            raise SystemExit(f"FAIL: P4e-live frame cycle order changed at {index}")
        frame = build_ui_frame(
            source=Address.parse(stage["source"]),
            destination=Address.parse(stage["destination"]),
            info=vector["information_text"].encode("ascii"),
            include_fcs=True,
        )
        if not verify_fcs(frame):
            raise SystemExit(f"FAIL: P4e-live cycle {index} frame FCS is invalid")
        selectors = frame_to_selectors(
            frame,
            pre_flags=stage["pre_flags"],
            post_flags=stage["post_flags"],
            initial_tone=MARK,
        )
        packed = pack_selectors(selectors)
        checks = (
            (len(frame), vector["frame_bytes"], "frame bytes"),
            (frame.hex(), vector["frame_hex"], "frame hex"),
            (hashlib.sha256(frame).hexdigest(), vector["frame_sha256"], "frame SHA256"),
            (len(selectors), vector["selector_count"], "selector count"),
            (len(packed), vector["packed_selector_bytes"], "packed selector bytes"),
            (
                hashlib.sha256(packed).hexdigest(),
                vector["packed_selector_sha256"],
                "packed selector SHA256",
            ),
            (
                len(selectors) * stage["samples_per_selector"],
                vector["expected_generated_samples"],
                "generated samples",
            ),
        )
        for actual, expected, label in checks:
            if actual != expected:
                raise SystemExit(
                    f"FAIL: P4e-live cycle {index} {label} changed: "
                    f"expected={expected!r} actual={actual!r}"
                )
        frames.append(frame)
    return frames


def require_active_rx(status, *, context: str) -> None:
    if status.dropped_bytes != 0:
        raise RuntimeError(f"RX FIFO dropped {status.dropped_bytes} bytes {context}")
    if status.flags & TX_FLAG:
        raise RuntimeError(f"RX status reports TX active {context}: flags=0x{status.flags:02X}")
    if status.flags & ACTIVE_RX_REQUIRED_MASK != ACTIVE_RX_REQUIRED_MASK:
        raise RuntimeError(
            f"passive AX.25 RX not fully active {context}: "
            f"flags=0x{status.flags:02X} required=0x{ACTIVE_RX_REQUIRED_MASK:02X}"
        )


def describe_inbound(sequence: int, cycle_label: str, item) -> None:
    parsed = parse_ax25_frame(item.frame, has_fcs=True)
    source = str(parsed["source"])
    destination = str(parsed["destination"])
    path = ",".join(str(address) for address in parsed["path"])
    info = parsed["info"].decode("ascii", "replace")
    via = f" via={path}" if path else ""
    print(
        f"INBOUND[{sequence}] phase={cycle_label} source={source} destination={destination}"
        f"{via} type={parsed['frame_type']} bytes={len(item.frame)} info={info!r}"
    )


def drain_rx(owner: TXModemOwner, decoder: StreamingBell202Decoder, maximum: int) -> tuple[int, list]:
    drained = 0
    fresh_frames = []
    # Bound each sampling pass while still comfortably staying ahead of the
    # ~120 packed bytes produced per 50 ms at 19.2 ksps.
    for _ in range(4):
        chunk = owner.rx_read(maximum, timeout=1.25)
        drained += len(chunk)
        if chunk:
            fresh_frames.extend(decoder.feed(chunk))
        if len(chunk) < maximum:
            break
    return drained, fresh_frames


def print_plan(stage: dict) -> None:
    print("=== YWD-1278 0C-P4e LIVE PERSISTENT HALF-DUPLEX MULTI-CYCLE ===")
    print(f"Target                    : {stage['target_id']}")
    print(f"Device                    : {stage['device']}")
    print(f"AX25R4 identity           : {stage['expected_identity']}")
    print(f"TX/RX frequency           : {stage['frequency_hz']} Hz")
    print(f"RF power byte             : {stage['rf_power']}/255")
    print("Detector                  : busy<=83 clear>=90 hold=250ms")
    print("P1                        : PERSIST=63 SLOTTIME=100ms max-wait=30s")
    print("Persistent lifecycle      : RX_STOP -> TX once -> RF idle -> RX_START")
    print("Outgoing cycles           : 3 fixed frames")
    print("Fresh inbound trigger     : REQUIRED before each outgoing cycle")
    print("Final post-TX RX decode   : REQUIRED after cycle 3 restart")
    print("Qualification RNG/cycle   : 255 until decoded BUSY trigger; then 255,0")
    print("Automatic TX retry        : NO")
    print("KISS/product TX           : DISCONNECTED")
    print("Flash/GPIO/options        : FORBIDDEN")
    print("Independent TX decode     : all 3 outgoing frames REQUIRED")
    for vector in stage["frames"]:
        print(
            f"TX[{vector['cycle']}]                     : {stage['source']}>{stage['destination']}:"
            f"{vector['information_text']}"
        )
        print(
            f"  bytes/selectors/samples : {vector['frame_bytes']} / "
            f"{vector['selector_count']} / {vector['expected_generated_samples']}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="YWD-1278 P4e guarded live multi-cycle qualification")
    ap.add_argument("--transmit", action="store_true")
    ap.add_argument("--confirm", default="")
    args = ap.parse_args()

    p4d_r1.load_target()
    stage = load_stage()
    frames = build_vectors(stage)
    print_plan(stage)

    for vector in stage["frames"]:
        print(
            f"EXPECTED_EXTERNAL_DECODE[{vector['cycle']}]="
            f"{stage['source']}>{stage['destination']}:{vector['information_text']}"
        )

    if not args.transmit:
        print("P4E_LIVE_DRY_RUN=PASS")
        print("TX_MODEM_OWNER_CONSTRUCTED=NO")
        print("HARDWARE_UART_OPENED=NO")
        print("RF_TRANSMITTED=NO")
        return 0

    if args.confirm != CONFIRMATION_TOKEN:
        raise SystemExit(
            "FAIL: physical P4e requires exact confirmation token "
            f"--confirm {CONFIRMATION_TOKEN}"
        )
    if not p4d_r1.uart_is_free():
        raise SystemExit(f"FAIL: modem UART already has an owner: {stage['device']}")
    typed = input(f"Type exactly {INTERACTIVE_CONFIRMATION} to arm three fixed TX cycles: ").strip()
    if typed != INTERACTIVE_CONFIRMATION:
        raise SystemExit("FAIL: P4e-live confirmation did not match; no UART opened")

    owner = TXModemOwner(
        posix_serial_transport_factory(stage["device"]),
        queue_capacity=8,
        submit_timeout=0.20,
        default_transaction_timeout=1.50,
    )
    broker: TXBroker | None = None
    owner_started = False
    rx_started = False
    accepted_tx_count = 0
    total_packed_bytes = 0
    total_status_checks = 0
    total_rssi_samples = 0
    total_inbound_decodes = 0
    peak_fifo_available = 0
    max_fifo_drops = 0
    cycle_records: list[dict] = []

    try:
        owner.start(timeout=2.0)
        owner_started = True
        version = owner.get_version(timeout=1.5)
        if version.identity != stage["expected_identity"]:
            raise RuntimeError(
                "running firmware identity mismatch: "
                f"expected={stage['expected_identity']!r} actual={version.identity!r}"
            )

        rf_initial = owner.rf_status(timeout=1.5)
        diag_initial = owner.rf_diagnostics(timeout=1.5)
        if rf_initial.remaining_selectors != 0 or diag_initial.tx_active != 0:
            raise RuntimeError("modem is not idle before P4e-live setup")

        owner.apply_tx_qualification_profile(timeout=1.5)
        owner.arm_rx_modem_io(timeout=1.5)
        owner.rx_start(timeout=1.5)
        rx_started = True
        active = owner.rx_status(timeout=1.5)
        total_status_checks += 1
        require_active_rx(active, context="at initial P4e-live RX start")
        peak_fifo_available = max(peak_fifo_available, active.available_bytes)

        broker = TXBroker(
            owner,
            transmit_enabled=True,
            queue_capacity=1,
            submit_timeout=0.05,
            default_transaction_timeout=1.5,
            thread_name="ywd1278-0c-p4e-live-broker",
        )
        broker.start()
        lifecycle = PersistentHalfDuplexSubmitter(
            owner,
            broker,
            monotonic=time.monotonic,
            sleep=time.sleep,
            parameters=HalfDuplexParameters(
                transaction_timeout_seconds=1.5,
                tx_idle_poll_seconds=0.05,
                tx_idle_timeout_seconds=5.0,
            ),
        )
        access_queue = BoundedChannelAccessQueue(
            lifecycle,
            queue_capacity=1,
            request_timeout_seconds=stage["per_cycle_access_timeout_seconds"],
            downstream_timeout_seconds=1.5,
        )

        for cycle_index, (frame, vector) in enumerate(zip(frames, stage["frames"]), start=1):
            decoder = StreamingBell202Decoder()
            decoded_trigger = False
            seen_busy = False
            busy_elapsed = None
            decoded_elapsed = None
            clear_elapsed = None
            defer_elapsed = None
            dispatch_elapsed = None
            pre_trigger_defers = 0
            post_trigger_trials = 0
            samples = 0
            packed_bytes = 0
            status_checks = 0
            last_state = None

            cycle_started = time.monotonic()
            queued = access_queue.enqueue(frame, now=cycle_started)
            deadline = queued.deadline_at
            next_sample = cycle_started
            next_status = cycle_started
            print(f"CYCLE[{cycle_index}]_WINDOW=OPEN")
            print(
                f"ACTION: send/allow one real AX.25 packet on 145.050 MHz now; "
                f"cycle {cycle_index} cannot TX until it is decoded and BUSY is observed."
            )

            def qualification_random_byte() -> int:
                nonlocal pre_trigger_defers, post_trigger_trials
                if not (seen_busy and decoded_trigger):
                    pre_trigger_defers += 1
                    return 255
                post_trigger_trials += 1
                if post_trigger_trials == 1:
                    return 255
                if post_trigger_trials == 2:
                    return 0
                raise RuntimeError(
                    f"cycle {cycle_index} attempted more than two post-trigger persistence trials"
                )

            receipt: TXReceipt | None = None
            while receipt is None:
                now = time.monotonic()
                if now >= deadline:
                    raise RuntimeError(
                        f"cycle {cycle_index} timed out before one qualified dispatch; "
                        f"decoded_trigger={decoded_trigger} seen_busy={seen_busy}"
                    )
                if now < next_sample:
                    time.sleep(min(next_sample - now, 0.005))
                    continue

                drained, fresh = drain_rx(owner, decoder, stage["rx_read_maximum"])
                packed_bytes += drained
                total_packed_bytes += drained
                for item in fresh:
                    if not verify_fcs(item.frame):
                        raise RuntimeError("streaming decoder emitted a frame with invalid FCS")
                    total_inbound_decodes += 1
                    describe_inbound(total_inbound_decodes, f"cycle-{cycle_index}-trigger", item)
                    if not decoded_trigger:
                        decoded_trigger = True
                        decoded_elapsed = now - cycle_started

                if now >= next_status:
                    live_status = owner.rx_status(timeout=1.25)
                    status_checks += 1
                    total_status_checks += 1
                    require_active_rx(live_status, context=f"during cycle {cycle_index}")
                    peak_fifo_available = max(peak_fifo_available, live_status.available_bytes)
                    max_fifo_drops = max(max_fifo_drops, live_status.dropped_bytes)
                    next_status = now + stage["rx_status_interval_seconds"]

                rssi = owner.rx_rssi(timeout=1.25)
                obs = access_queue.observe_rssi(
                    now=now,
                    raw_magnitude=rssi.raw_magnitude,
                    random_byte_source=qualification_random_byte,
                )
                samples += 1
                total_rssi_samples += 1
                elapsed = now - cycle_started

                if obs.access is not None:
                    state = (obs.access.detector.state, obs.access.csma.state)
                    if state != last_state or obs.access.random_byte is not None or obs.downstream_called:
                        random_text = "-" if obs.access.random_byte is None else str(obs.access.random_byte)
                        print(
                            f"ACCESS[{cycle_index}:{samples:04d}] elapsed={elapsed:.3f} "
                            f"raw={obs.access.detector.raw_magnitude} "
                            f"detector={obs.access.detector.state.value} "
                            f"csma={obs.access.csma.state.value} random={random_text} "
                            f"trials={obs.access.csma.persistence_trials} "
                            f"busy_obs={obs.access.csma.busy_observations} "
                            f"decoded_trigger={'yes' if decoded_trigger else 'no'} "
                            f"request={obs.request_state.value if obs.request_state else '-'}"
                        )
                        last_state = state

                    if obs.access.detector.state is ChannelBusyState.BUSY:
                        if not seen_busy:
                            busy_elapsed = elapsed
                        seen_busy = True
                    if seen_busy and obs.access.detector.state is ChannelBusyState.CLEAR and clear_elapsed is None:
                        clear_elapsed = elapsed
                    if (
                        seen_busy
                        and decoded_trigger
                        and obs.access.random_byte == 255
                        and obs.access.csma.state is CSMAState.WAIT_SLOT
                    ):
                        defer_elapsed = elapsed

                if obs.downstream_called:
                    if not seen_busy or not decoded_trigger:
                        raise RuntimeError(
                            f"cycle {cycle_index} reached downstream before fresh decoded BUSY trigger"
                        )
                    if obs.request_state is not AccessRequestState.DISPATCHED:
                        raise RuntimeError(
                            f"cycle {cycle_index} downstream failed: "
                            f"{obs.request_state} {obs.downstream_error}"
                        )
                    if not isinstance(obs.downstream_result, TXReceipt):
                        raise RuntimeError(f"cycle {cycle_index} returned unexpected downstream receipt")
                    receipt = obs.downstream_result
                    dispatch_elapsed = elapsed
                    accepted_tx_count += 1
                    # PersistentHalfDuplexSubmitter returns only after RF idle
                    # and RX_START + active-status verification have succeeded.
                    restarted = owner.rx_status(timeout=1.25)
                    total_status_checks += 1
                    require_active_rx(restarted, context=f"after cycle {cycle_index} TX restart")
                    peak_fifo_available = max(peak_fifo_available, restarted.available_bytes)
                    max_fifo_drops = max(max_fifo_drops, restarted.dropped_bytes)
                    diag = owner.rf_diagnostics(timeout=1.25)
                    if diag.tx_active != 0:
                        raise RuntimeError(f"cycle {cycle_index} TX still active after lifecycle return")
                    if diag.keyups != 1:
                        raise RuntimeError(
                            f"cycle {cycle_index} completed-burst keyups expected 1, got {diag.keyups}"
                        )
                    if diag.generated_samples != vector["expected_generated_samples"]:
                        raise RuntimeError(
                            f"cycle {cycle_index} generated samples expected "
                            f"{vector['expected_generated_samples']}, got {diag.generated_samples}"
                        )
                    if receipt.frame_bytes != vector["frame_bytes"]:
                        raise RuntimeError(f"cycle {cycle_index} broker frame size changed")
                    if receipt.selector_count != vector["selector_count"]:
                        raise RuntimeError(f"cycle {cycle_index} selector count changed")
                    if receipt.packed_selector_bytes != vector["packed_selector_bytes"]:
                        raise RuntimeError(f"cycle {cycle_index} packed selector bytes changed")
                    if receipt.packed_selector_sha256 != vector["packed_selector_sha256"]:
                        raise RuntimeError(f"cycle {cycle_index} packed selector SHA256 changed")
                    break

                if obs.request_state in {AccessRequestState.TIMED_OUT, AccessRequestState.DOWNSTREAM_FAILED}:
                    raise RuntimeError(
                        f"cycle {cycle_index} request terminated: "
                        f"{obs.request_state.value} {obs.downstream_error}"
                    )

                next_sample += stage["rssi_poll_seconds"]
                while next_sample <= now:
                    next_sample += stage["rssi_poll_seconds"]

            if post_trigger_trials != 2:
                raise RuntimeError(
                    f"cycle {cycle_index} expected exactly two post-trigger persistence trials, "
                    f"got {post_trigger_trials}"
                )
            snap = lifecycle.snapshot
            if snap.cycles_completed != cycle_index or snap.downstream_accepted != cycle_index:
                raise RuntimeError(
                    f"P4e lifecycle counters changed after cycle {cycle_index}: {snap}"
                )
            cycle_records.append(
                {
                    "cycle": cycle_index,
                    "decoded_trigger": True,
                    "seen_busy": True,
                    "busy_elapsed": busy_elapsed,
                    "decoded_elapsed": decoded_elapsed,
                    "clear_elapsed": clear_elapsed,
                    "defer_elapsed": defer_elapsed,
                    "dispatch_elapsed": dispatch_elapsed,
                    "pre_trigger_defers": pre_trigger_defers,
                    "post_trigger_trials": post_trigger_trials,
                    "rssi_samples": samples,
                    "packed_bytes": packed_bytes,
                    "status_checks": status_checks,
                }
            )
            print(f"CYCLE[{cycle_index}]_TX_COMPLETE=YES")
            print(f"CYCLE[{cycle_index}]_RX_RESTART_ACTIVE=YES")
            print(f"CYCLE[{cycle_index}]_FIFO_DROPS=0")
            print(
                f"CYCLE[{cycle_index}]_TX_DIAG=keyups:1 generated_samples:"
                f"{vector['expected_generated_samples']}"
            )

        # There is intentionally no queued TX request from here on. Decode one
        # more frame after cycle-3 RX restart to prove persistent receive really
        # survived the final transmit handoff.
        if access_queue.snapshot.queue_depth != 0:
            raise RuntimeError("P4e-live queue not empty before final RX-only proof")
        final_decoder = StreamingBell202Decoder()
        final_started = time.monotonic()
        final_deadline = final_started + stage["final_post_tx_receive_timeout_seconds"]
        next_status = final_started
        final_decode = False
        print("FINAL_POST_TX_RX_WINDOW=OPEN")
        print("ACTION: send/allow one more real AX.25 packet now; no TX request is queued.")
        while not final_decode:
            now = time.monotonic()
            if now >= final_deadline:
                raise RuntimeError(
                    "final post-cycle-3 RX restart did not decode a fresh FCS-valid AX.25 frame"
                )
            drained, fresh = drain_rx(owner, final_decoder, stage["rx_read_maximum"])
            total_packed_bytes += drained
            for item in fresh:
                if not verify_fcs(item.frame):
                    raise RuntimeError("final RX decoder emitted invalid FCS")
                total_inbound_decodes += 1
                describe_inbound(total_inbound_decodes, "final-post-tx-rx", item)
                final_decode = True
                break
            if now >= next_status:
                status = owner.rx_status(timeout=1.25)
                total_status_checks += 1
                require_active_rx(status, context="during final post-TX receive proof")
                peak_fifo_available = max(peak_fifo_available, status.available_bytes)
                max_fifo_drops = max(max_fifo_drops, status.dropped_bytes)
                next_status = now + stage["rx_status_interval_seconds"]
            if not final_decode:
                time.sleep(0.005)

        if total_inbound_decodes < stage["required_total_inbound_decoded_frames"]:
            raise RuntimeError(
                f"P4e-live decoded only {total_inbound_decodes} inbound frames; "
                f"need {stage['required_total_inbound_decoded_frames']}"
            )
        if accepted_tx_count != stage["maximum_transmit_submissions"]:
            raise RuntimeError(
                f"P4e-live accepted {accepted_tx_count} TX submissions; expected 3"
            )
        if broker.snapshot.submitted != 3 or broker.snapshot.accepted != 3 or broker.snapshot.failed != 0:
            raise RuntimeError(f"P4e-live broker counters changed: {broker.snapshot}")
        if access_queue.snapshot.dispatched_requests != 3:
            raise RuntimeError(f"P4e-live access queue counters changed: {access_queue.snapshot}")
        lifecycle_snap = lifecycle.snapshot
        if lifecycle_snap.cycles_completed != 3 or lifecycle_snap.rx_restart_operations != 3:
            raise RuntimeError(f"P4e-live lifecycle did not complete three restarts: {lifecycle_snap}")
        if lifecycle_snap.failed_latched:
            raise RuntimeError("P4e-live lifecycle unexpectedly latched failed")
        if max_fifo_drops != 0:
            raise RuntimeError(f"P4e-live observed FIFO drops: {max_fifo_drops}")

        owner.rx_stop(timeout=1.25)
        rx_started = False
        stopped = owner.rx_status(timeout=1.25)
        total_status_checks += 1
        if stopped.flags & 0x01:
            raise RuntimeError("RX remained active after final qualification RX_STOP")
        if stopped.dropped_bytes != 0:
            raise RuntimeError(f"FIFO drops at final stop: {stopped.dropped_bytes}")

        broker.stop(timeout=2.0)
        broker = None
        owner.stop(timeout=2.0)
        owner_started = False
        owner_snap = owner.snapshot
        if owner_snap.running:
            raise RuntimeError("TXModemOwner still running after P4e-live stop")
        if owner_snap.owner_thread_id is None:
            raise RuntimeError("single modem owner thread ID was never established")

        print("YWD1278_0C_P4E_LIVE_MULTICYCLE_EXECUTION=PASS")
        print("COMPLETE_RX_TX_RX_CYCLES=3")
        print("INITIAL_RX_STARTS=1")
        print("POST_TX_RX_RESTARTS=3")
        print("TOTAL_RX_STARTS=4")
        print("TX_SUBMISSIONS=3")
        print(f"INBOUND_FCS_VALID_FRAMES={total_inbound_decodes}")
        print("PRE_TX_FRESH_DECODED_TRIGGERS=3")
        print("FINAL_POST_TX_FCS_VALID_RX=PASS")
        print(f"RSSI_SAMPLES={total_rssi_samples}")
        print(f"PACKED_RX_BYTES_DRAINED={total_packed_bytes}")
        print(f"RX_STATUS_CHECKS={total_status_checks}")
        print(f"PEAK_FIFO_AVAILABLE={peak_fifo_available}")
        print(f"FIFO_DROPPED_BYTES={max_fifo_drops}")
        for record in cycle_records:
            index = record["cycle"]
            print(f"CYCLE_{index}_LIVE_BUSY=PASS")
            print(f"CYCLE_{index}_FRESH_RX_DECODE=PASS")
            print(f"CYCLE_{index}_PERSIST_255_DEFER=PASS")
            print(f"CYCLE_{index}_PERSIST_0_DISPATCH=PASS")
            print(f"CYCLE_{index}_RX_STOP_TX_RX_RESTART=PASS")
        print("SINGLE_MODEM_OWNER=PASS")
        print("UART_RELEASED=YES")
        print("DUPLICATE_DISPATCH=NO")
        print("AUTOMATIC_TX_RETRY=NO")
        print("KISS_TX_CONNECTED=NO")
        print("PRODUCT_TX_ENABLED=NO")
        print("FLASH_WRITTEN=NO")
        print("GPIO_ACCESSED=NO")
        print("OPTION_BYTES_WRITTEN=NO")
        print("RF_TRANSMITTED=YES_EXACTLY_THREE_FIXED_BURSTS")
        print("EXTERNAL_TX_DECODE_REQUIRED=3")
        print("QUALIFICATION_COMPLETE=NO_PENDING_EXTERNAL_TX_DECODE")
        return 0

    except BaseException:
        print(f"P4E_LIVE_ACCEPTED_TX_BEFORE_FAILURE={accepted_tx_count}", file=sys.stderr)
        if accepted_tx_count:
            print("DO_NOT_RERUN_FULL_P4E_LIVE_HARNESS=YES", file=sys.stderr)
            print("PRESERVE_OUTPUT_AND_DIAGNOSE_FROM_CURRENT_STATE=YES", file=sys.stderr)
        else:
            print("RF_TX_ACCEPTED_BEFORE_FAILURE=NO", file=sys.stderr)
        raise
    finally:
        if broker is not None:
            try:
                broker.stop(timeout=2.0)
            except BaseException:
                pass
        if owner_started:
            if rx_started:
                try:
                    owner.rx_stop(timeout=1.0)
                except BaseException:
                    pass
            try:
                owner.stop(timeout=2.0)
            except BaseException:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
