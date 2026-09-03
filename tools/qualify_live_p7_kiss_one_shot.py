#!/usr/bin/env python3
"""0C-P7 guarded physical one-shot KISS DATA -> RF qualification.

This is a fixed-vector qualification harness, not a transmitter UI.  It proves
that one real localhost KISS DATA message can traverse the host-qualified P7
path and produce exactly one channel-access-controlled RF burst:

    localhost KISS DATA (no FCS)
      -> P6 immutable parameter generation
      -> P7 bounded admission + TNC-owned FCS
      -> qualified P2/P1 channel access
      -> exact P4e RX_STOP/TX/RX_START lifecycle
      -> captured P5 TXDELAY serialization
      -> real single-owner modem transport

The localhost listener is closed before channel access is allowed to dispatch.
A fresh non-P7 FCS-valid inbound AX.25 frame plus live BUSY is required before
TX, and one more non-P7 FCS-valid inbound frame must decode after RX restart.
Independent direct over-air decoding of the one outgoing packet is required
before P7 may be called physically qualified.  A YWDNOD repeat is explicitly
non-blocking and is not part of this qualification gate.

Default invocation is dry-run and exits before TXModemOwner construction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(TOOLS))

import qualify_live_csma_single_tx as p4d_r1  # noqa: E402
import qualify_live_p4e_multicycle as p4e  # noqa: E402

from ywd1278.ax25 import (  # noqa: E402
    Address,
    append_fcs,
    build_ui_frame,
    parse_frame as parse_ax25_frame,
    verify_fcs,
)
from ywd1278.kiss.control import TNCSessionState  # noqa: E402
from ywd1278.kiss.framing import DATA, PERSIST, SLOTTIME, TXDELAY, encode  # noqa: E402
from ywd1278.kiss.server import start_server_thread, stop_server_thread  # noqa: E402
from ywd1278.kiss.tx_backend import TNCTransmitBackend  # noqa: E402
from ywd1278.kiss.tx_path import (  # noqa: E402
    KISSDataAdmissionQueue,
    KISSDataRequestState,
)
from ywd1278.modem._serial import posix_serial_transport_factory  # noqa: E402
from ywd1278.modem.tx_owner import TXModemOwner  # noqa: E402
from ywd1278.phy import MARK, frame_to_selectors, pack_selectors  # noqa: E402
from ywd1278.phy.bell202_rx import StreamingBell202Decoder  # noqa: E402
from ywd1278.tx.broker import TXReceipt  # noqa: E402
from ywd1278.tx.channel_busy import ChannelBusyState  # noqa: E402
from ywd1278.tx.contextual import (  # noqa: E402
    ContextualHalfDuplexSubmitter,
    ContextualTXDelayRouter,
)
from ywd1278.tx.csma import CSMAState  # noqa: E402
from ywd1278.tx.half_duplex import HalfDuplexParameters  # noqa: E402


STAGE_PATH = ROOT / "firmware" / "qualification" / "0c-p7-live-kiss-one-shot.json"
CONFIRMATION_TOKEN = "P7-LIVE-KISS-145050-P200-ONE"
INTERACTIVE_CONFIRMATION = "TRANSMIT-P7-KISS-ONE"
MIN_FULL_SLOT_SECONDS = 0.100


def load_stage() -> dict:
    stage = json.loads(STAGE_PATH.read_text(encoding="utf-8"))
    required = {
        "schema": 1,
        "phase": "0C-P7-live",
        "stage": "kiss-originated-one-shot",
        "status": "staged",
        "base_checkpoint": "checkpoint/0c-p7-kiss-data-admission-host-qualified",
        "base_checkpoint_sha": "3df9a46f0851876e55c078ab41504584304bef38",
        "target_id": p4d_r1.TARGET_ID,
        "device": p4d_r1.DEVICE,
        "expected_identity": (
            "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz "
            "ADF7021 FW based on CA6JAU GitID #7ff74ed"
        ),
        "frequency_hz": 145050000,
        "rf_power": 200,
        "packet_count": 1,
        "kiss_listener_host": "127.0.0.1",
        "kiss_listener_port": 0,
        "kiss_listener_ephemeral": True,
        "kiss_listener_closed_before_channel_access_dispatch": True,
        "kiss_data_messages_required": 1,
        "kiss_data_payload_includes_fcs": False,
        "tnc_appends_fcs_exactly_once": True,
        "kiss_port": 0,
        "expected_parameter_generation": 3,
        "source": "KJ6YWD-10",
        "destination": "YWD7",
        "path": ["YWDNOD"],
        "information_text": "YWD-1278 P7 KISS VERIFY 1/1",
        "pre_flags": 45,
        "post_flags": 3,
        "initial_tone": "MARK",
        "samples_per_selector": 16,
        "requires_live_busy_before_dispatch": True,
        "requires_fresh_fcs_valid_rx_trigger_before_tx": True,
        "required_pre_tx_decoded_frames": 1,
        "access_timeout_seconds": 30.0,
        "rssi_poll_seconds": 0.05,
        "rx_status_interval_seconds": 0.25,
        "rx_read_maximum": 200,
        "requires_rx_active_after_tx": True,
        "requires_final_non_qualification_fcs_valid_rx": True,
        "final_post_tx_receive_timeout_seconds": 60.0,
        "required_total_qualifying_non_p7_inbound_frames": 2,
        "p7_qualification_echo_must_not_count_as_rx_proof": True,
        "rx_fifo_dropped_bytes_required": 0,
        "maximum_transmit_submissions": 1,
        "automatic_tx_retry": False,
        "requires_direct_external_decode": True,
        "required_external_tx_decodes": 1,
        "require_ywdnod_repeated_decode": False,
        "confirmation_token": CONFIRMATION_TOKEN,
        "interactive_phrase": INTERACTIVE_CONFIRMATION,
        "product_tx_enabled": False,
        "persistent_kiss_tx_enabled": False,
        "flash_permitted": False,
        "gpio_reset_permitted": False,
        "option_bytes_permitted": False,
    }
    for key, expected in required.items():
        if stage.get(key) != expected:
            raise SystemExit(
                f"FAIL: P7-live staging mismatch for {key}: "
                f"expected={expected!r} actual={stage.get(key)!r}"
            )
    if stage.get("kiss_parameter_commands") != {
        "txdelay": 30,
        "persist": 63,
        "slottime": 10,
    }:
        raise SystemExit("FAIL: P7-live fixed KISS parameter commands changed")
    if stage.get("qualification_randomness") != {
        "before_fresh_decoded_busy_trigger": 255,
        "after_fresh_decoded_busy_trigger": [255, 0],
    }:
        raise SystemExit("FAIL: P7-live qualification randomness changed")
    return stage


def build_vector(stage: dict) -> tuple[bytes, bytes]:
    body = build_ui_frame(
        source=Address.parse(stage["source"]),
        destination=Address.parse(stage["destination"]),
        path=[Address.parse(item) for item in stage["path"]],
        info=stage["information_text"].encode("ascii"),
        include_fcs=False,
    )
    frame = append_fcs(body)
    if not verify_fcs(frame):
        raise SystemExit("FAIL: P7-live constructed frame FCS is invalid")
    selectors = frame_to_selectors(
        frame,
        pre_flags=stage["pre_flags"],
        post_flags=stage["post_flags"],
        initial_tone=MARK,
    )
    packed = pack_selectors(selectors)
    checks = (
        (len(body), stage["kiss_body_bytes"], "KISS body bytes"),
        (body.hex(), stage["kiss_body_hex"], "KISS body hex"),
        (hashlib.sha256(body).hexdigest(), stage["kiss_body_sha256"], "KISS body SHA256"),
        (len(frame), stage["frame_with_fcs_bytes"], "FCS-bearing frame bytes"),
        (frame.hex(), stage["frame_with_fcs_hex"], "FCS-bearing frame hex"),
        (
            hashlib.sha256(frame).hexdigest(),
            stage["frame_with_fcs_sha256"],
            "FCS-bearing frame SHA256",
        ),
        (len(selectors), stage["selector_count"], "selector count"),
        (len(packed), stage["packed_selector_bytes"], "packed selector bytes"),
        (
            hashlib.sha256(packed).hexdigest(),
            stage["packed_selector_sha256"],
            "packed selector SHA256",
        ),
        (
            len(selectors) * stage["samples_per_selector"],
            stage["expected_generated_samples"],
            "generated samples",
        ),
    )
    for actual, expected, label in checks:
        if actual != expected:
            raise SystemExit(
                f"FAIL: P7-live {label} changed: expected={expected!r} actual={actual!r}"
            )
    return body, frame


def is_p7_qualification_frame(frame_with_fcs: bytes, stage: dict) -> bool:
    try:
        parsed = parse_ax25_frame(frame_with_fcs, has_fcs=True)
    except ValueError:
        return False
    return (
        str(parsed["source"]) == stage["source"]
        and str(parsed["destination"]) == stage["destination"]
        and parsed["info"] == stage["information_text"].encode("ascii")
    )


def inject_exactly_one_kiss_message(
    backend: TNCTransmitBackend,
    admission: KISSDataAdmissionQueue,
    session: TNCSessionState,
    stage: dict,
    body: bytes,
) -> int:
    server = None
    thread = None
    try:
        server, thread = start_server_thread(
            backend,
            host=stage["kiss_listener_host"],
            port=stage["kiss_listener_port"],
        )
        host, port = server.server_address[:2]
        if host != stage["kiss_listener_host"] or not (1 <= int(port) <= 65535):
            raise RuntimeError(f"unexpected qualification KISS bind: {(host, port)!r}")

        wire = b"".join(
            (
                encode(bytes((stage["kiss_parameter_commands"]["txdelay"],)), command=TXDELAY),
                encode(bytes((stage["kiss_parameter_commands"]["persist"],)), command=PERSIST),
                encode(bytes((stage["kiss_parameter_commands"]["slottime"],)), command=SLOTTIME),
                encode(body, command=DATA),
            )
        )
        with socket.create_connection((host, int(port)), timeout=2.0) as client:
            client.sendall(wire)
            client.shutdown(socket.SHUT_WR)

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            ingress = backend.ingress_counters
            snap = session.snapshot
            queue_snap = admission.snapshot
            if (
                ingress.data_messages_received == 1
                and ingress.data_admitted == 1
                and snap.generation == stage["expected_parameter_generation"]
                and queue_snap.accepted_requests == 1
                and queue_snap.queue_depth == 1
            ):
                break
            time.sleep(0.01)
        else:
            raise RuntimeError(
                "localhost KISS message did not reach the exact one-shot admission state: "
                f"ingress={backend.ingress_counters} session={session.snapshot} "
                f"queue={admission.snapshot}"
            )

        return int(port)
    finally:
        if server is not None and thread is not None:
            stop_server_thread(server, thread)
            if thread.is_alive():
                raise RuntimeError("qualification KISS listener thread remained alive after shutdown")


def print_plan(stage: dict) -> None:
    print("=== YWD-1278 0C-P7 LIVE KISS DATA ONE-SHOT ===")
    print(f"Target                    : {stage['target_id']}")
    print(f"Device                    : {stage['device']}")
    print(f"AX25R4 identity           : {stage['expected_identity']}")
    print(f"TX/RX frequency           : {stage['frequency_hz']} Hz")
    print(f"RF power byte             : {stage['rf_power']}/255")
    print("KISS listener             : 127.0.0.1 ephemeral, closed before access dispatch")
    print("KISS DATA messages        : exactly 1")
    print("KISS DATA FCS             : absent on ingress; TNC appends exactly once")
    print(
        "KISS parameters           : "
        f"TXDELAY={stage['kiss_parameter_commands']['txdelay']} "
        f"PERSIST={stage['kiss_parameter_commands']['persist']} "
        f"SLOTTIME={stage['kiss_parameter_commands']['slottime']}"
    )
    print("Detector                  : busy<=83 clear>=90 hold=250ms")
    print("Qualification RNG         : 255 until decoded BUSY trigger; then 255,0")
    print("Lifecycle                 : RX_STOP -> one TX -> RF idle -> RX_START")
    print("Fresh inbound trigger     : one non-P7 FCS-valid packet REQUIRED before TX")
    print("Final post-TX RX proof    : one non-P7 FCS-valid packet REQUIRED")
    print("Automatic TX retry        : NO")
    print("Persistent/product TX     : DISABLED")
    print("Flash/GPIO/options        : FORBIDDEN")
    print("YWDNOD repeat proof       : DEFERRED / NON-BLOCKING")
    print(
        "TX                        : "
        f"{stage['source']}>{stage['destination']},{stage['path'][0]}:"
        f"{stage['information_text']}"
    )
    print(
        "  body/frame/selectors    : "
        f"{stage['kiss_body_bytes']} / {stage['frame_with_fcs_bytes']} / "
        f"{stage['selector_count']}"
    )
    print(f"  expected samples        : {stage['expected_generated_samples']}")


def main() -> int:
    ap = argparse.ArgumentParser(description="YWD-1278 P7 guarded live KISS one-shot qualification")
    ap.add_argument("--transmit", action="store_true")
    ap.add_argument("--confirm", default="")
    args = ap.parse_args()

    p4d_r1.load_target()
    stage = load_stage()
    body, expected_frame = build_vector(stage)
    print_plan(stage)
    print(
        "EXPECTED_EXTERNAL_DECODE="
        f"{stage['source']}>{stage['destination']},{stage['path'][0]}:{stage['information_text']}"
    )

    if not args.transmit:
        print("P7_LIVE_KISS_ONE_SHOT_DRY_RUN=PASS")
        print("TX_MODEM_OWNER_CONSTRUCTED=NO")
        print("KISS_LISTENER_OPENED=NO")
        print("HARDWARE_UART_OPENED=NO")
        print("RF_TRANSMITTED=NO")
        return 0

    if args.confirm != CONFIRMATION_TOKEN:
        raise SystemExit(
            "FAIL: physical P7 requires exact confirmation token "
            f"--confirm {CONFIRMATION_TOKEN}"
        )
    if not p4d_r1.uart_is_free():
        raise SystemExit(f"FAIL: modem UART already has an owner: {stage['device']}")
    typed = input(f"Type exactly {INTERACTIVE_CONFIRMATION} to arm one KISS-originated TX: ").strip()
    if typed != INTERACTIVE_CONFIRMATION:
        raise SystemExit("FAIL: P7-live confirmation did not match; no UART opened")

    owner = TXModemOwner(
        posix_serial_transport_factory(stage["device"]),
        queue_capacity=8,
        submit_timeout=0.20,
        default_transaction_timeout=1.50,
    )
    router: ContextualTXDelayRouter | None = None
    lifecycle: ContextualHalfDuplexSubmitter | None = None
    admission: KISSDataAdmissionQueue | None = None
    backend: TNCTransmitBackend | None = None
    session: TNCSessionState | None = None
    owner_started = False
    rx_started = False
    accepted_tx_count = 0
    total_packed_bytes = 0
    total_status_checks = 0
    total_rssi_samples = 0
    total_inbound_decodes = 0
    qualifying_non_p7_frames = 0
    qualification_echoes_ignored = 0
    peak_fifo_available = 0
    max_fifo_drops = 0

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
            raise RuntimeError("modem is not idle before P7-live setup")

        owner.apply_tx_qualification_profile(timeout=1.5)
        owner.arm_rx_modem_io(timeout=1.5)
        owner.rx_start(timeout=1.5)
        rx_started = True
        active = owner.rx_status(timeout=1.5)
        total_status_checks += 1
        p4e.require_active_rx(active, context="at initial P7-live RX start")
        peak_fifo_available = max(peak_fifo_available, active.available_bytes)

        router = ContextualTXDelayRouter(
            owner,
            transmit_enabled=True,
            broker_queue_capacity=1,
            broker_submit_timeout=0.05,
            default_transaction_timeout=1.5,
        )
        lifecycle = ContextualHalfDuplexSubmitter(
            owner,
            router,
            monotonic=time.monotonic,
            sleep=time.sleep,
            parameters=HalfDuplexParameters(
                transaction_timeout_seconds=1.5,
                tx_idle_poll_seconds=0.05,
                tx_idle_timeout_seconds=5.0,
            ),
        )
        admission = KISSDataAdmissionQueue(
            lifecycle,
            queue_capacity=1,
            request_timeout_seconds=stage["access_timeout_seconds"],
            downstream_timeout_seconds=1.5,
        )
        session = TNCSessionState()
        backend = TNCTransmitBackend(
            admission,
            monotonic=time.monotonic,
            session=session,
            history_capacity=0,
            subscriber_queue_capacity=1,
        )

        kiss_port = inject_exactly_one_kiss_message(backend, admission, session, stage, body)
        ingress = backend.ingress_counters
        control = backend.control_counters
        params = backend.control_snapshot
        if ingress.data_messages_received != 1 or ingress.data_admitted != 1:
            raise RuntimeError(f"P7-live DATA ingress counters changed: {ingress}")
        if any(
            (
                ingress.data_invalid_rejections,
                ingress.data_queue_full_drops,
                ingress.data_time_rejections,
                ingress.data_other_rejections,
            )
        ):
            raise RuntimeError(f"P7-live DATA ingress unexpectedly rejected input: {ingress}")
        if control.kiss_parameter_updates != 3 or control.kiss_parameter_rejections != 0:
            raise RuntimeError(f"P7-live KISS control counters changed: {control}")
        if (
            params.generation != 3
            or params.txdelay != 30
            or params.persist != 63
            or params.slottime != 10
            or params.fullduplex != 0
        ):
            raise RuntimeError(f"P7-live captured parameter state changed: {params}")
        q0 = admission.snapshot
        if q0.accepted_requests != 1 or q0.queue_depth != 1:
            raise RuntimeError(f"P7-live exactly-one queue state changed: {q0}")

        print(f"KISS_EPHEMERAL_PORT_USED={kiss_port}")
        print("KISS_LISTENER_CLOSED_BEFORE_ACCESS=PASS")
        print("KISS_DATA_MESSAGES_RECEIVED=1")
        print("KISS_DATA_ADMITTED=1")
        print("KISS_PARAMETER_GENERATION=3")
        print("CAPTURED_TXDELAY=30")
        print("CAPTURED_PERSIST=63")
        print("CAPTURED_SLOTTIME=10")
        print("TNC_FCS_APPENDED_EXACTLY_ONCE=PASS")

        decoder = StreamingBell202Decoder()
        decoded_trigger = False
        seen_busy = False
        busy_elapsed = None
        clear_elapsed = None
        defer_elapsed = None
        dispatch_elapsed = None
        pre_trigger_defers = 0
        post_trigger_trials = 0
        samples = 0
        last_state = None
        started = time.monotonic()
        deadline = started + stage["access_timeout_seconds"]
        next_sample = started
        next_status = started

        print("P7_TX_ACCESS_WINDOW=OPEN")
        print(
            "ACTION: send/allow one non-P7 real AX.25 packet on 145.050 MHz now; "
            "the queued KISS packet cannot TX until a fresh frame is decoded and BUSY is observed."
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
            raise RuntimeError("P7-live attempted more than two post-trigger persistence trials")

        receipt: TXReceipt | None = None
        while receipt is None:
            now = time.monotonic()
            if now >= deadline:
                raise RuntimeError(
                    "P7-live timed out before one qualified dispatch; "
                    f"decoded_trigger={decoded_trigger} seen_busy={seen_busy}"
                )
            if now < next_sample:
                time.sleep(min(next_sample - now, 0.005))
                continue

            drained, fresh = p4e.drain_rx(owner, decoder, stage["rx_read_maximum"])
            total_packed_bytes += drained
            for item in fresh:
                if not verify_fcs(item.frame):
                    raise RuntimeError("streaming decoder emitted a frame with invalid FCS")
                total_inbound_decodes += 1
                p4e.describe_inbound(total_inbound_decodes, "p7-pre-tx-trigger", item)
                if is_p7_qualification_frame(item.frame, stage):
                    qualification_echoes_ignored += 1
                    print("PRE_TX_P7_QUALIFICATION_ECHO_IGNORED=YES")
                    continue
                qualifying_non_p7_frames += 1
                if not decoded_trigger:
                    decoded_trigger = True

            if now >= next_status:
                live_status = owner.rx_status(timeout=1.25)
                total_status_checks += 1
                p4e.require_active_rx(live_status, context="during P7-live access")
                peak_fifo_available = max(peak_fifo_available, live_status.available_bytes)
                max_fifo_drops = max(max_fifo_drops, live_status.dropped_bytes)
                next_status = now + stage["rx_status_interval_seconds"]

            rssi = owner.rx_rssi(timeout=1.25)
            obs = admission.observe_rssi(
                now=now,
                raw_magnitude=rssi.raw_magnitude,
                random_byte_source=qualification_random_byte,
            )
            samples += 1
            total_rssi_samples += 1
            elapsed = now - started

            if obs.access is not None:
                state = (obs.access.detector.state, obs.access.csma.state)
                if state != last_state or obs.access.random_byte is not None or obs.downstream_called:
                    random_text = "-" if obs.access.random_byte is None else str(obs.access.random_byte)
                    print(
                        f"ACCESS[{samples:04d}] elapsed={elapsed:.3f} "
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
                accepted_tx_count = max(
                    accepted_tx_count,
                    lifecycle.half_duplex_snapshot.downstream_accepted,
                    lifecycle.router_snapshot.contextual_submissions,
                )
                if not seen_busy or not decoded_trigger:
                    raise RuntimeError("P7-live reached downstream before fresh decoded BUSY trigger")
                if obs.request_state is not KISSDataRequestState.DISPATCHED:
                    raise RuntimeError(
                        f"P7-live downstream failed: {obs.request_state} {obs.downstream_error}"
                    )
                if not isinstance(obs.downstream_result, TXReceipt):
                    raise RuntimeError("P7-live returned unexpected downstream receipt")
                receipt = obs.downstream_result
                dispatch_elapsed = elapsed
                break

            if obs.request_state in {
                KISSDataRequestState.TIMED_OUT,
                KISSDataRequestState.DOWNSTREAM_FAILED,
            }:
                accepted_tx_count = max(
                    accepted_tx_count,
                    lifecycle.half_duplex_snapshot.downstream_accepted,
                    lifecycle.router_snapshot.contextual_submissions,
                )
                raise RuntimeError(
                    f"P7-live request terminated: {obs.request_state.value} {obs.downstream_error}"
                )

            next_sample += stage["rssi_poll_seconds"]
            while next_sample <= now:
                next_sample += stage["rssi_poll_seconds"]

        if post_trigger_trials != 2:
            raise RuntimeError(
                f"P7-live expected exactly two post-trigger persistence trials, got {post_trigger_trials}"
            )
        if None in (busy_elapsed, clear_elapsed, defer_elapsed, dispatch_elapsed):
            raise RuntimeError("P7-live did not record the complete access timeline")
        assert clear_elapsed is not None
        assert defer_elapsed is not None
        assert dispatch_elapsed is not None
        if defer_elapsed - clear_elapsed + 1e-9 < MIN_FULL_SLOT_SECONDS:
            raise RuntimeError(
                "P7-live first post-clear persistence trial occurred before a full 100ms slot: "
                f"clear={clear_elapsed:.6f} defer={defer_elapsed:.6f}"
            )
        if dispatch_elapsed - defer_elapsed + 1e-9 < MIN_FULL_SLOT_SECONDS:
            raise RuntimeError(
                "P7-live dispatch occurred before a second full 100ms slot: "
                f"defer={defer_elapsed:.6f} dispatch={dispatch_elapsed:.6f}"
            )

        restarted = owner.rx_status(timeout=1.25)
        total_status_checks += 1
        p4e.require_active_rx(restarted, context="after P7-live KISS TX restart")
        peak_fifo_available = max(peak_fifo_available, restarted.available_bytes)
        max_fifo_drops = max(max_fifo_drops, restarted.dropped_bytes)
        diag = owner.rf_diagnostics(timeout=1.25)
        if diag.tx_active != 0 or diag.keyups != 1:
            raise RuntimeError(f"P7-live completed TX diagnostics changed: {diag}")
        if diag.generated_samples != stage["expected_generated_samples"]:
            raise RuntimeError(
                f"P7-live generated samples expected {stage['expected_generated_samples']}, "
                f"got {diag.generated_samples}"
            )
        if receipt.frame_bytes != stage["frame_with_fcs_bytes"]:
            raise RuntimeError("P7-live broker frame size changed")
        if receipt.frame_sha256 != stage["frame_with_fcs_sha256"]:
            raise RuntimeError("P7-live broker frame SHA256 changed")
        if receipt.selector_count != stage["selector_count"]:
            raise RuntimeError("P7-live selector count changed")
        if receipt.packed_selector_bytes != stage["packed_selector_bytes"]:
            raise RuntimeError("P7-live packed selector byte count changed")
        if receipt.packed_selector_sha256 != stage["packed_selector_sha256"]:
            raise RuntimeError("P7-live packed selector SHA256 changed")
        if expected_frame != append_fcs(body):
            raise RuntimeError("P7-live FCS ownership changed after admission")

        q1 = admission.snapshot
        if q1.queue_depth != 0 or q1.accepted_requests != 1 or q1.dispatched_requests != 1:
            raise RuntimeError(f"P7-live queue counters changed after dispatch: {q1}")
        if q1.timed_out_requests or q1.downstream_failures:
            raise RuntimeError(f"P7-live queue terminal counters changed: {q1}")
        half = lifecycle.half_duplex_snapshot
        if (
            half.cycles_completed != 1
            or half.rx_restart_operations != 1
            or half.downstream_accepted != 1
            or half.failed_latched
        ):
            raise RuntimeError(f"P7-live P4e lifecycle counters changed: {half}")
        route = lifecycle.router_snapshot
        if (
            route.broker_profiles != (30,)
            or route.contextual_submissions != 1
            or route.contextual_failures != 0
        ):
            raise RuntimeError(f"P7-live contextual router counters changed: {route}")
        accepted_tx_count = max(
            accepted_tx_count,
            half.downstream_accepted,
            route.contextual_submissions,
        )
        if accepted_tx_count != 1:
            raise RuntimeError(f"P7-live accepted TX count changed: {accepted_tx_count}")

        print("P7_KISS_TX_COMPLETE=YES")
        print("P7_RX_RESTART_ACTIVE=YES")
        print("P7_FIFO_DROPS=0")
        print(
            f"P7_TX_DIAG=keyups:1 generated_samples:{stage['expected_generated_samples']}"
        )

        if admission.snapshot.queue_depth != 0:
            raise RuntimeError("P7-live queue not empty before final RX-only proof")
        final_decoder = StreamingBell202Decoder()
        final_started = time.monotonic()
        final_deadline = final_started + stage["final_post_tx_receive_timeout_seconds"]
        next_status = final_started
        final_decode = False
        print("FINAL_POST_TX_RX_WINDOW=OPEN")
        print("ACTION: send/allow one non-P7 real AX.25 packet now; no TX request is queued.")
        while not final_decode:
            now = time.monotonic()
            if now >= final_deadline:
                raise RuntimeError(
                    "final post-P7-TX RX restart did not decode a non-P7 FCS-valid AX.25 frame"
                )
            drained, fresh = p4e.drain_rx(owner, final_decoder, stage["rx_read_maximum"])
            total_packed_bytes += drained
            for item in fresh:
                if not verify_fcs(item.frame):
                    raise RuntimeError("final RX decoder emitted invalid FCS")
                total_inbound_decodes += 1
                p4e.describe_inbound(total_inbound_decodes, "p7-final-post-tx-rx", item)
                if is_p7_qualification_frame(item.frame, stage):
                    qualification_echoes_ignored += 1
                    print("FINAL_P7_QUALIFICATION_ECHO_IGNORED_AS_RX_PROOF=YES")
                    continue
                qualifying_non_p7_frames += 1
                final_decode = True
                break
            if now >= next_status:
                status = owner.rx_status(timeout=1.25)
                total_status_checks += 1
                p4e.require_active_rx(status, context="during final P7 post-TX receive proof")
                peak_fifo_available = max(peak_fifo_available, status.available_bytes)
                max_fifo_drops = max(max_fifo_drops, status.dropped_bytes)
                next_status = now + stage["rx_status_interval_seconds"]
            if not final_decode:
                time.sleep(0.005)

        if qualifying_non_p7_frames < stage["required_total_qualifying_non_p7_inbound_frames"]:
            raise RuntimeError(
                f"P7-live decoded only {qualifying_non_p7_frames} qualifying non-P7 inbound frames; "
                f"need {stage['required_total_qualifying_non_p7_inbound_frames']}"
            )
        if max_fifo_drops != 0:
            raise RuntimeError(f"P7-live observed FIFO drops: {max_fifo_drops}")

        owner.rx_stop(timeout=1.25)
        rx_started = False
        stopped = owner.rx_status(timeout=1.25)
        total_status_checks += 1
        if stopped.flags & 0x01:
            raise RuntimeError("RX remained active after final P7 qualification RX_STOP")
        if stopped.dropped_bytes != 0:
            raise RuntimeError(f"FIFO drops at final P7 stop: {stopped.dropped_bytes}")

        router.close()
        router = None
        owner.stop(timeout=2.0)
        owner_started = False
        owner_snap = owner.snapshot
        if owner_snap.running:
            raise RuntimeError("TXModemOwner still running after P7-live stop")
        if owner_snap.owner_thread_id is None:
            raise RuntimeError("single modem owner thread ID was never established")

        print("YWD1278_0C_P7_LIVE_KISS_ONE_SHOT_EXECUTION=PASS")
        print("KISS_DATA_MESSAGES_RECEIVED=1")
        print("KISS_DATA_ADMITTED=1")
        print("KISS_DATA_WITHOUT_FCS=PASS")
        print("TNC_APPENDED_FCS_EXACTLY_ONCE=PASS")
        print("PARAMETER_GENERATION_CAPTURED=3")
        print("CAPTURED_TXDELAY=30")
        print("CAPTURED_PERSIST=63")
        print("CAPTURED_SLOTTIME=10")
        print("KISS_LISTENER_CLOSED_BEFORE_ACCESS=PASS")
        print("PRE_TX_FRESH_NON_P7_RX_DECODE=PASS")
        print("LIVE_BUSY_OBSERVED=YES")
        print("PERSIST_255_DEFER=PASS")
        print("PERSIST_0_DISPATCH=PASS")
        print(f"CLEAR_TO_DEFER_SECONDS={defer_elapsed - clear_elapsed:.3f}")
        print(f"DEFER_TO_DISPATCH_SECONDS={dispatch_elapsed - defer_elapsed:.3f}")
        print("RX_STOP_TX_RX_RESTART=PASS")
        print("TX_SUBMISSIONS=1")
        print(f"TX_FRAME_BYTES={receipt.frame_bytes}")
        print(f"TX_SELECTOR_COUNT={receipt.selector_count}")
        print(f"TX_PACKED_SELECTOR_BYTES={receipt.packed_selector_bytes}")
        print(f"TX_PACKED_SELECTOR_SHA256={receipt.packed_selector_sha256}")
        print("RF_KEYUPS_COMPLETED_BURST_ABSOLUTE=1")
        print(f"RF_GENERATED_SAMPLES_COMPLETED_BURST_ABSOLUTE={stage['expected_generated_samples']}")
        print(f"INBOUND_FCS_VALID_FRAMES_TOTAL={total_inbound_decodes}")
        print(f"QUALIFYING_NON_P7_INBOUND_FRAMES={qualifying_non_p7_frames}")
        print(f"P7_QUALIFICATION_ECHOES_IGNORED={qualification_echoes_ignored}")
        print("FINAL_POST_TX_NON_P7_FCS_VALID_RX=PASS")
        print(f"RSSI_SAMPLES={total_rssi_samples}")
        print(f"PACKED_RX_BYTES_DRAINED={total_packed_bytes}")
        print(f"RX_STATUS_CHECKS={total_status_checks}")
        print(f"PEAK_FIFO_AVAILABLE={peak_fifo_available}")
        print(f"FIFO_DROPPED_BYTES={max_fifo_drops}")
        print("DIGIPEATER_STATION=KJ6YWD-5")
        print("AX25_PATH=VIA_YWDNOD")
        print("YWDNOD_REPEAT_GATE=DEFERRED_NON_BLOCKING")
        print("SINGLE_MODEM_OWNER=PASS")
        print("UART_RELEASED=YES")
        print("DUPLICATE_DISPATCH=NO")
        print("AUTOMATIC_TX_RETRY=NO")
        print("PERSISTENT_KISS_TX_ENABLED=NO")
        print("PRODUCT_TX_ENABLED=NO")
        print("FLASH_WRITTEN=NO")
        print("GPIO_ACCESSED=NO")
        print("OPTION_BYTES_WRITTEN=NO")
        print("RF_TRANSMITTED=YES_EXACTLY_ONE_KISS_ORIGINATED_BURST")
        print("EXTERNAL_DIRECT_DECODE_REQUIRED=1")
        print("QUALIFICATION_COMPLETE=NO_PENDING_EXTERNAL_DIRECT_DECODE")
        return 0

    except BaseException:
        actual_accepted = accepted_tx_count
        if lifecycle is not None:
            actual_accepted = max(
                actual_accepted,
                lifecycle.half_duplex_snapshot.downstream_accepted,
                lifecycle.router_snapshot.contextual_submissions,
            )
        print(f"P7_LIVE_ACCEPTED_TX_BEFORE_FAILURE={actual_accepted}", file=sys.stderr)
        if actual_accepted:
            print("DO_NOT_RERUN_FULL_P7_LIVE_HARNESS=YES", file=sys.stderr)
            print("PRESERVE_OUTPUT_AND_DIAGNOSE_FROM_CURRENT_STATE=YES", file=sys.stderr)
        else:
            print("RF_TX_ACCEPTED_BEFORE_FAILURE=NO", file=sys.stderr)
        raise
    finally:
        if router is not None:
            try:
                router.close()
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
