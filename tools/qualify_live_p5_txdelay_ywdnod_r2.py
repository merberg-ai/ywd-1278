#!/usr/bin/env python3
"""0C-P5-R2 guarded live TXDELAY qualification VIA YWDNOD.

R2 supersedes the unrun R1 staging harness before physical use. It preserves
P4e's physically-qualified half-duplex/channel-access lifecycle and varies only
the construction-time TXDelayBroker profile:

  cycle 1: TXDELAY=30 -> 300 ms -> 45 opening HDLC flags
  cycle 2: TXDELAY=50 -> 500 ms -> 75 opening HDLC flags

Both fixed frames contain AX.25 path YWDNOD, the configured alias for the
operator's KJ6YWD-5 digipeater. Each transmit requires both a live BUSY
observation and a fresh FCS-valid *non-qualification* inbound frame. A returned
YWDNOD repeat of either P5 qualification frame is decoded and reported but is
not permitted to trigger another qualification TX. After cycle 2, another
non-qualification FCS-valid frame must be decoded with no TX request queued.

Independent receiver evidence must later show both direct frames and both
YWDNOD* repeats before physical P5 can be promoted.

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
import qualify_live_p4e_multicycle as p4e_live  # noqa: E402

from ywd1278.ax25 import (  # noqa: E402
    Address,
    build_ui_frame,
    parse_frame as parse_ax25_frame,
    verify_fcs,
)
from ywd1278.modem._serial import posix_serial_transport_factory  # noqa: E402
from ywd1278.modem.tx_owner import TXModemOwner  # noqa: E402
from ywd1278.phy import MARK, frame_to_selectors, pack_selectors  # noqa: E402
from ywd1278.phy.bell202_rx import StreamingBell202Decoder  # noqa: E402
from ywd1278.tx.access_queue import (  # noqa: E402
    AccessRequestState,
    BoundedChannelAccessQueue,
)
from ywd1278.tx.broker import TXReceipt  # noqa: E402
from ywd1278.tx.channel_busy import ChannelBusyState  # noqa: E402
from ywd1278.tx.csma import CSMAState  # noqa: E402
from ywd1278.tx.half_duplex import (  # noqa: E402
    HalfDuplexParameters,
    PersistentHalfDuplexSubmitter,
)
from ywd1278.tx.txdelay import TXDelayBroker, resolve_txdelay  # noqa: E402


STAGE_PATH = ROOT / "firmware" / "qualification" / "0c-p5-live-txdelay-ywdnod.json"
CONFIRMATION_TOKEN = "P5-LIVE-YWDNOD-TXDELAY-30-50-R2"
INTERACTIVE_CONFIRMATION = "TRANSMIT-P5-R2-TXDELAY-VIA-YWDNOD-TWO"
MIN_FULL_SLOT_SECONDS = 0.100


def load_stage() -> dict:
    stage = json.loads(STAGE_PATH.read_text(encoding="utf-8"))
    required = {
        "schema": 1,
        "phase": "0C-P5-live",
        "status": "staged",
        "base_checkpoint": "checkpoint/0c-p5-txdelay-host-qualified",
        "base_checkpoint_sha": "30cc677fbcc9fc9bab1aa1a18c18850ed1ef40a1",
        "target_id": p4d_r1.TARGET_ID,
        "device": p4d_r1.DEVICE,
        "expected_identity": (
            "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz "
            "ADF7021 FW based on CA6JAU GitID #7ff74ed"
        ),
        "frequency_hz": 145050000,
        "rf_power": 200,
        "cycles": 2,
        "per_cycle_access_timeout_seconds": 30.0,
        "final_post_tx_receive_timeout_seconds": 60.0,
        "rssi_poll_seconds": 0.05,
        "rx_status_interval_seconds": 0.25,
        "rx_read_maximum": 200,
        "source": "KJ6YWD-10",
        "destination": "YWD5TD",
        "digipeater_station": "KJ6YWD-5",
        "digipeater_alias": "YWDNOD",
        "path": ["YWDNOD"],
        "post_flags": 3,
        "initial_tone": "MARK",
        "samples_per_selector": 16,
        "requires_fresh_fcs_valid_rx_trigger_before_each_tx": True,
        "required_pre_tx_decoded_frames": 2,
        "requires_final_fcs_valid_rx_after_cycle_2_restart": True,
        "required_total_inbound_decoded_frames": 3,
        "requires_live_busy_before_each_tx": True,
        "rx_fifo_dropped_bytes_required": 0,
        "requires_rx_active_after_each_tx": True,
        "requires_direct_external_decode_of_all_outgoing_frames": True,
        "requires_ywdnod_repeated_decode_of_all_outgoing_frames": True,
        "expected_repeated_path_marker": "YWDNOD*",
        "required_external_direct_decodes": 2,
        "required_external_ywdnod_repeat_decodes": 2,
        "maximum_transmit_submissions": 2,
        "automatic_tx_retry": False,
        "kiss_parameter_ingress_connected": False,
        "kiss_data_tx_connected": False,
        "product_tx_enabled": False,
        "flash_permitted": False,
        "gpio_reset_permitted": False,
        "option_bytes_permitted": False,
    }
    for key, expected in required.items():
        if stage.get(key) != expected:
            raise SystemExit(
                f"FAIL: P5-live staging mismatch for {key}: "
                f"expected={expected!r} actual={stage.get(key)!r}"
            )
    if stage.get("qualification_randomness") != {
        "before_fresh_decoded_busy_trigger": 255,
        "after_fresh_decoded_busy_trigger": [255, 0],
    }:
        raise SystemExit("FAIL: P5-live qualification randomness changed")
    if len(stage.get("frames", [])) != 2:
        raise SystemExit("FAIL: P5-live must contain exactly two fixed frames")
    return stage


def build_vectors(stage: dict) -> list[bytes]:
    frames: list[bytes] = []
    path = tuple(Address.parse(item) for item in stage["path"])
    for index, vector in enumerate(stage["frames"], start=1):
        if vector.get("cycle") != index:
            raise SystemExit(f"FAIL: P5-live frame cycle order changed at {index}")
        profile = resolve_txdelay(vector["txdelay_units"])
        if profile.pre_flags != vector["pre_flags"]:
            raise SystemExit(f"FAIL: P5-live cycle {index} TXDELAY flag resolution changed")
        if round(profile.requested_seconds * 1000) != vector["requested_txdelay_ms"]:
            raise SystemExit(f"FAIL: P5-live cycle {index} requested TXDELAY changed")
        frame = build_ui_frame(
            source=Address.parse(stage["source"]),
            destination=Address.parse(stage["destination"]),
            path=path,
            info=vector["information_text"].encode("ascii"),
            include_fcs=True,
        )
        if not verify_fcs(frame):
            raise SystemExit(f"FAIL: P5-live cycle {index} frame FCS is invalid")
        selectors = frame_to_selectors(
            frame,
            pre_flags=profile.pre_flags,
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
            (hashlib.sha256(packed).hexdigest(), vector["packed_selector_sha256"], "packed selector SHA256"),
            (
                len(selectors) * stage["samples_per_selector"],
                vector["expected_generated_samples"],
                "generated samples",
            ),
        )
        for actual, expected, label in checks:
            if actual != expected:
                raise SystemExit(
                    f"FAIL: P5-live cycle {index} {label} changed: "
                    f"expected={expected!r} actual={actual!r}"
                )
        frames.append(frame)
    return frames


def is_qualification_frame(frame: bytes, qualification_frames: set[bytes]) -> bool:
    """Return True only for one of our exact two FCS-bearing qualification frames."""

    return bytes(frame) in qualification_frames


def print_plan(stage: dict) -> None:
    print("=== YWD-1278 0C-P5-R2 LIVE TXDELAY VIA YWDNOD ===")
    print(f"Target                    : {stage['target_id']}")
    print(f"Device                    : {stage['device']}")
    print(f"AX25R4 identity           : {stage['expected_identity']}")
    print(f"TX/RX frequency           : {stage['frequency_hz']} Hz")
    print(f"RF power byte             : {stage['rf_power']}/255")
    print(f"Digipeater station        : {stage['digipeater_station']}")
    print(f"AX.25 qualification path  : VIA {stage['digipeater_alias']}")
    print("Detector                  : busy<=83 clear>=90 hold=250ms")
    print("P1                        : PERSIST=63 SLOTTIME=100ms max-wait=30s")
    print("Persistent lifecycle      : RX_STOP -> TX once -> RF idle -> RX_START")
    print("Fresh inbound trigger     : REQUIRED before each outgoing frame")
    print("Own P5 digipeat as trigger: FORBIDDEN (decoded/reported, not authorization)")
    print("Final post-TX RX decode   : REQUIRED, non-qualification frame")
    print("Qualification RNG/cycle   : 255 until decoded BUSY trigger; then 255,0")
    print("Automatic TX retry        : NO")
    print("KISS parameter/DATA TX    : DISCONNECTED")
    print("Product TX                : DISABLED")
    print("Flash/GPIO/options        : FORBIDDEN")
    print("External direct decode    : both outgoing frames REQUIRED")
    print("External YWDNOD* repeat   : both outgoing frames REQUIRED")
    for vector in stage["frames"]:
        print(
            f"TX[{vector['cycle']}]                     : TXDELAY={vector['txdelay_units']} "
            f"({vector['requested_txdelay_ms']}ms / {vector['pre_flags']} flags)"
        )
        print(
            f"  packet                  : {stage['source']}>{stage['destination']},"
            f"{stage['digipeater_alias']}:{vector['information_text']}"
        )
        print(
            f"  bytes/selectors/samples : {vector['frame_bytes']} / "
            f"{vector['selector_count']} / {vector['expected_generated_samples']}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="YWD-1278 P5-R2 guarded live TXDELAY VIA YWDNOD")
    ap.add_argument("--transmit", action="store_true")
    ap.add_argument("--confirm", default="")
    args = ap.parse_args()

    p4d_r1.load_target()
    stage = load_stage()
    frames = build_vectors(stage)
    qualification_frames = set(frames)
    print_plan(stage)

    for vector in stage["frames"]:
        direct = (
            f"{stage['source']}>{stage['destination']},{stage['digipeater_alias']}:"
            f"{vector['information_text']}"
        )
        repeated = (
            f"{stage['source']}>{stage['destination']},{stage['digipeater_alias']}*:"
            f"{vector['information_text']}"
        )
        print(f"EXPECTED_EXTERNAL_DIRECT[{vector['cycle']}]={direct}")
        print(f"EXPECTED_EXTERNAL_REPEAT[{vector['cycle']}]={repeated}")

    if not args.transmit:
        print("P5_R2_LIVE_TXDELAY_YWDNOD_DRY_RUN=PASS")
        print("TX_MODEM_OWNER_CONSTRUCTED=NO")
        print("HARDWARE_UART_OPENED=NO")
        print("RF_TRANSMITTED=NO")
        return 0

    if args.confirm != CONFIRMATION_TOKEN:
        raise SystemExit(
            "FAIL: physical P5-R2 requires exact confirmation token "
            f"--confirm {CONFIRMATION_TOKEN}"
        )
    if not p4d_r1.uart_is_free():
        raise SystemExit(f"FAIL: modem UART already has an owner: {stage['device']}")
    typed = input(f"Type exactly {INTERACTIVE_CONFIRMATION} to arm two fixed TX packets: ").strip()
    if typed != INTERACTIVE_CONFIRMATION:
        raise SystemExit("FAIL: P5-R2 confirmation did not match; no UART opened")

    owner = TXModemOwner(
        posix_serial_transport_factory(stage["device"]),
        queue_capacity=8,
        submit_timeout=0.20,
        default_transaction_timeout=1.50,
    )
    owner_started = False
    rx_started = False
    active_broker: TXDelayBroker | None = None
    active_lifecycle: PersistentHalfDuplexSubmitter | None = None
    active_cycle_base = 0
    accepted_tx_count = 0
    total_packed_bytes = 0
    total_status_checks = 0
    total_rssi_samples = 0
    total_inbound_decodes = 0
    qualifying_inbound_decodes = 0
    ignored_qualification_echoes = 0
    peak_fifo_available = 0
    max_fifo_drops = 0
    cycle_records: list[dict] = []

    def exact_accepted_count() -> int:
        count = accepted_tx_count
        if active_lifecycle is not None:
            count = max(
                count,
                active_cycle_base + active_lifecycle.snapshot.downstream_accepted,
            )
        if active_broker is not None:
            count = max(count, active_cycle_base + active_broker.snapshot.accepted)
        return count

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
            raise RuntimeError("modem is not idle before P5-R2 setup")

        owner.apply_tx_qualification_profile(timeout=1.5)
        owner.arm_rx_modem_io(timeout=1.5)
        owner.rx_start(timeout=1.5)
        rx_started = True
        active = owner.rx_status(timeout=1.5)
        total_status_checks += 1
        p4e_live.require_active_rx(active, context="at initial P5-R2 RX start")
        peak_fifo_available = max(peak_fifo_available, active.available_bytes)

        for cycle_index, (frame, vector) in enumerate(zip(frames, stage["frames"]), start=1):
            active_cycle_base = accepted_tx_count
            if active_cycle_base != cycle_index - 1:
                raise RuntimeError("accepted-TX accounting drift before cycle start")

            broker = TXDelayBroker(
                owner,
                txdelay_units=vector["txdelay_units"],
                transmit_enabled=True,
                queue_capacity=1,
                submit_timeout=0.05,
                default_transaction_timeout=1.5,
                thread_name=f"ywd1278-0c-p5-r2-broker-{cycle_index}",
            )
            broker.start()
            active_broker = broker
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
            active_lifecycle = lifecycle
            access_queue = BoundedChannelAccessQueue(
                lifecycle,
                queue_capacity=1,
                request_timeout_seconds=stage["per_cycle_access_timeout_seconds"],
                downstream_timeout_seconds=1.5,
            )
            decoder = StreamingBell202Decoder()
            decoded_trigger = False
            seen_busy = False
            clear_elapsed: float | None = None
            defer_elapsed: float | None = None
            dispatch_elapsed: float | None = None
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
                "ACTION: send/allow one non-qualification AX.25 packet on 145.050 MHz now; "
                f"TXDELAY {vector['txdelay_units']} cannot TX until it is decoded and BUSY is observed."
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

                drained, fresh = p4e_live.drain_rx(owner, decoder, stage["rx_read_maximum"])
                packed_bytes += drained
                total_packed_bytes += drained
                for item in fresh:
                    if not verify_fcs(item.frame):
                        raise RuntimeError("streaming decoder emitted a frame with invalid FCS")
                    total_inbound_decodes += 1
                    p4e_live.describe_inbound(
                        total_inbound_decodes,
                        f"p5-r2-cycle-{cycle_index}",
                        item,
                    )
                    if is_qualification_frame(item.frame, qualification_frames):
                        ignored_qualification_echoes += 1
                        parsed = parse_ax25_frame(item.frame, has_fcs=True)
                        print(
                            "QUALIFICATION_ECHO_IGNORED_AS_TRIGGER=YES "
                            f"source={parsed['source']} destination={parsed['destination']}"
                        )
                        continue
                    qualifying_inbound_decodes += 1
                    decoded_trigger = True

                if now >= next_status:
                    live_status = owner.rx_status(timeout=1.25)
                    status_checks += 1
                    total_status_checks += 1
                    p4e_live.require_active_rx(
                        live_status,
                        context=f"during P5-R2 cycle {cycle_index}",
                    )
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
                            f"decoded_trigger={'yes' if decoded_trigger else 'no'} "
                            f"request={obs.request_state.value if obs.request_state else '-'}"
                        )
                        last_state = state
                    if obs.access.detector.state is ChannelBusyState.BUSY:
                        seen_busy = True
                    if (
                        seen_busy
                        and obs.access.detector.state is ChannelBusyState.CLEAR
                        and clear_elapsed is None
                    ):
                        clear_elapsed = elapsed
                    if (
                        seen_busy
                        and decoded_trigger
                        and obs.access.random_byte == 255
                        and obs.access.csma.state is CSMAState.WAIT_SLOT
                    ):
                        defer_elapsed = elapsed

                if obs.downstream_called:
                    accepted_tx_count = exact_accepted_count()
                    if not seen_busy or not decoded_trigger:
                        raise RuntimeError(
                            f"cycle {cycle_index} reached TX before non-qualification decoded BUSY trigger"
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
                    restarted = owner.rx_status(timeout=1.25)
                    total_status_checks += 1
                    p4e_live.require_active_rx(
                        restarted,
                        context=f"after P5-R2 cycle {cycle_index} TX restart",
                    )
                    peak_fifo_available = max(peak_fifo_available, restarted.available_bytes)
                    max_fifo_drops = max(max_fifo_drops, restarted.dropped_bytes)
                    diag = owner.rf_diagnostics(timeout=1.25)
                    if diag.tx_active != 0 or diag.keyups != 1:
                        raise RuntimeError(
                            f"cycle {cycle_index} completed-burst diagnostics invalid: {diag}"
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

                if obs.request_state in {
                    AccessRequestState.TIMED_OUT,
                    AccessRequestState.DOWNSTREAM_FAILED,
                }:
                    accepted_tx_count = exact_accepted_count()
                    raise RuntimeError(
                        f"cycle {cycle_index} request terminated: "
                        f"{obs.request_state.value} {obs.downstream_error}"
                    )

                next_sample += stage["rssi_poll_seconds"]
                while next_sample <= now:
                    next_sample += stage["rssi_poll_seconds"]

            if accepted_tx_count != cycle_index:
                raise RuntimeError(
                    f"cycle {cycle_index} accepted-TX accounting expected {cycle_index}, "
                    f"got {accepted_tx_count}"
                )
            if post_trigger_trials != 2:
                raise RuntimeError(
                    f"cycle {cycle_index} expected exactly two post-trigger persistence trials, "
                    f"got {post_trigger_trials}"
                )
            if clear_elapsed is None or defer_elapsed is None or dispatch_elapsed is None:
                raise RuntimeError(f"cycle {cycle_index} did not record complete access timing")
            if defer_elapsed - clear_elapsed + 1e-9 < MIN_FULL_SLOT_SECONDS:
                raise RuntimeError(f"cycle {cycle_index} defer happened before full 100ms slot")
            if dispatch_elapsed - defer_elapsed + 1e-9 < MIN_FULL_SLOT_SECONDS:
                raise RuntimeError(f"cycle {cycle_index} dispatch happened before second full 100ms slot")
            if lifecycle.snapshot.cycles_completed != 1 or lifecycle.snapshot.rx_restart_operations != 1:
                raise RuntimeError(f"cycle {cycle_index} P4e lifecycle did not complete exactly once")
            if broker.snapshot.submitted != 1 or broker.snapshot.accepted != 1 or broker.snapshot.failed != 0:
                raise RuntimeError(f"cycle {cycle_index} broker counters changed: {broker.snapshot}")

            cycle_records.append(
                {
                    "cycle": cycle_index,
                    "txdelay_units": vector["txdelay_units"],
                    "requested_txdelay_ms": vector["requested_txdelay_ms"],
                    "pre_flags": vector["pre_flags"],
                    "pre_trigger_defers": pre_trigger_defers,
                    "rssi_samples": samples,
                    "packed_bytes": packed_bytes,
                    "status_checks": status_checks,
                    "clear_elapsed": clear_elapsed,
                    "defer_elapsed": defer_elapsed,
                    "dispatch_elapsed": dispatch_elapsed,
                }
            )
            print(f"CYCLE[{cycle_index}]_TXDELAY_UNITS={vector['txdelay_units']}")
            print(f"CYCLE[{cycle_index}]_OPENING_FLAGS={vector['pre_flags']}")
            print(f"CYCLE[{cycle_index}]_TX_COMPLETE=YES")
            print(f"CYCLE[{cycle_index}]_RX_RESTART_ACTIVE=YES")
            print(f"CYCLE[{cycle_index}]_FIFO_DROPS=0")
            print(
                f"CYCLE[{cycle_index}]_TX_DIAG=keyups:1 generated_samples:"
                f"{vector['expected_generated_samples']}"
            )
            broker.stop(timeout=2.0)
            active_broker = None
            active_lifecycle = None
            active_cycle_base = accepted_tx_count

        # Final receive-only proof after the 500 ms TX restart. Qualification
        # echoes/repeats are visible evidence but may not satisfy this gate.
        final_decoder = StreamingBell202Decoder()
        final_started = time.monotonic()
        final_deadline = final_started + stage["final_post_tx_receive_timeout_seconds"]
        next_status = final_started
        final_decode = False
        print("FINAL_POST_TX_RX_WINDOW=OPEN")
        print(
            "ACTION: send/allow one non-qualification AX.25 packet now; "
            "no TX request is queued."
        )
        while not final_decode:
            now = time.monotonic()
            if now >= final_deadline:
                raise RuntimeError(
                    "final post-P5-R2 RX restart did not decode a fresh non-qualification FCS-valid frame"
                )
            drained, fresh = p4e_live.drain_rx(owner, final_decoder, stage["rx_read_maximum"])
            total_packed_bytes += drained
            for item in fresh:
                if not verify_fcs(item.frame):
                    raise RuntimeError("final RX decoder emitted invalid FCS")
                total_inbound_decodes += 1
                p4e_live.describe_inbound(
                    total_inbound_decodes,
                    "p5-r2-final-post-tx-rx",
                    item,
                )
                if is_qualification_frame(item.frame, qualification_frames):
                    ignored_qualification_echoes += 1
                    print("FINAL_QUALIFICATION_ECHO_IGNORED_AS_RX_PROOF=YES")
                    continue
                qualifying_inbound_decodes += 1
                final_decode = True
                break
            if now >= next_status:
                status = owner.rx_status(timeout=1.25)
                total_status_checks += 1
                p4e_live.require_active_rx(
                    status,
                    context="during P5-R2 final post-TX receive proof",
                )
                peak_fifo_available = max(peak_fifo_available, status.available_bytes)
                max_fifo_drops = max(max_fifo_drops, status.dropped_bytes)
                next_status = now + stage["rx_status_interval_seconds"]
            if not final_decode:
                time.sleep(0.005)

        if qualifying_inbound_decodes < stage["required_total_inbound_decoded_frames"]:
            raise RuntimeError(
                f"P5-R2 decoded only {qualifying_inbound_decodes} qualifying inbound frames; "
                f"need {stage['required_total_inbound_decoded_frames']}"
            )
        if accepted_tx_count != stage["maximum_transmit_submissions"]:
            raise RuntimeError(
                f"P5-R2 accepted {accepted_tx_count} TX submissions; expected 2"
            )
        if max_fifo_drops != 0:
            raise RuntimeError(f"P5-R2 observed FIFO drops: {max_fifo_drops}")

        owner.rx_stop(timeout=1.25)
        rx_started = False
        stopped = owner.rx_status(timeout=1.25)
        total_status_checks += 1
        if stopped.flags & 0x01:
            raise RuntimeError("RX remained active after final P5-R2 qualification RX_STOP")
        if stopped.dropped_bytes != 0:
            raise RuntimeError(f"FIFO drops at final stop: {stopped.dropped_bytes}")

        owner.stop(timeout=2.0)
        owner_started = False
        owner_snap = owner.snapshot
        if owner_snap.running or owner_snap.owner_thread_id is None:
            raise RuntimeError("single TXModemOwner lifecycle did not close cleanly")

        print("YWD1278_0C_P5_R2_LIVE_TXDELAY_YWDNOD_EXECUTION=PASS")
        print("COMPLETE_RX_TX_RX_CYCLES=2")
        print("INITIAL_RX_STARTS=1")
        print("POST_TX_RX_RESTARTS=2")
        print("TOTAL_RX_STARTS=3")
        print("TX_SUBMISSIONS=2")
        print(f"INBOUND_FCS_VALID_FRAMES_TOTAL={total_inbound_decodes}")
        print(f"QUALIFYING_NON_P5_INBOUND_FRAMES={qualifying_inbound_decodes}")
        print(f"P5_QUALIFICATION_ECHOES_IGNORED={ignored_qualification_echoes}")
        print("PRE_TX_FRESH_DECODED_TRIGGERS=2")
        print("FINAL_POST_TX_NON_QUALIFICATION_FCS_VALID_RX=PASS")
        print(f"RSSI_SAMPLES={total_rssi_samples}")
        print(f"PACKED_RX_BYTES_DRAINED={total_packed_bytes}")
        print(f"RX_STATUS_CHECKS={total_status_checks}")
        print(f"PEAK_FIFO_AVAILABLE={peak_fifo_available}")
        print(f"FIFO_DROPPED_BYTES={max_fifo_drops}")
        for record in cycle_records:
            index = record["cycle"]
            print(f"CYCLE_{index}_LIVE_BUSY=PASS")
            print(f"CYCLE_{index}_FRESH_NON_P5_RX_DECODE=PASS")
            print(f"CYCLE_{index}_PERSIST_255_DEFER=PASS")
            print(f"CYCLE_{index}_PERSIST_0_DISPATCH=PASS")
            print(f"CYCLE_{index}_RX_STOP_TX_RX_RESTART=PASS")
            print(f"CYCLE_{index}_TXDELAY_UNITS={record['txdelay_units']}")
            print(f"CYCLE_{index}_TXDELAY_REQUESTED_MS={record['requested_txdelay_ms']}")
            print(f"CYCLE_{index}_OPENING_FLAGS={record['pre_flags']}")
            print(
                f"CYCLE_{index}_CLEAR_TO_DEFER_SECONDS="
                f"{record['defer_elapsed'] - record['clear_elapsed']:.3f}"
            )
            print(
                f"CYCLE_{index}_DEFER_TO_DISPATCH_SECONDS="
                f"{record['dispatch_elapsed'] - record['defer_elapsed']:.3f}"
            )
        print("DIGIPEATER_STATION=KJ6YWD-5")
        print("AX25_PATH=VIA_YWDNOD")
        print("SINGLE_MODEM_OWNER=PASS")
        print("UART_RELEASED=YES")
        print("DUPLICATE_DISPATCH=NO")
        print("AUTOMATIC_TX_RETRY=NO")
        print("KISS_PARAMETER_INGRESS=DISCONNECTED")
        print("KISS_DATA_TX_CONNECTED=NO")
        print("PRODUCT_TX_ENABLED=NO")
        print("FLASH_WRITTEN=NO")
        print("GPIO_ACCESSED=NO")
        print("OPTION_BYTES_WRITTEN=NO")
        print("RF_TRANSMITTED=YES_EXACTLY_TWO_FIXED_BURSTS")
        print("EXTERNAL_DIRECT_DECODE_REQUIRED=2")
        print("EXTERNAL_YWDNOD_REPEAT_DECODE_REQUIRED=2")
        print("QUALIFICATION_COMPLETE=NO_PENDING_EXTERNAL_DIRECT_AND_YWDNOD_REPEAT_DECODE")
        return 0

    except BaseException:
        actual_accepted = exact_accepted_count()
        print(f"P5_R2_LIVE_ACCEPTED_TX_BEFORE_FAILURE={actual_accepted}", file=sys.stderr)
        if actual_accepted:
            print("DO_NOT_RERUN_FULL_P5_R2_LIVE_HARNESS=YES", file=sys.stderr)
            print("PRESERVE_OUTPUT_AND_DIAGNOSE_FROM_CURRENT_STATE=YES", file=sys.stderr)
        else:
            print("RF_TX_ACCEPTED_BEFORE_FAILURE=NO", file=sys.stderr)
        raise
    finally:
        if active_broker is not None:
            try:
                active_broker.stop(timeout=2.0)
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
