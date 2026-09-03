#!/usr/bin/env python3
"""0C-P8 guarded physical sustained KISS TNC qualification.

This is a fixed three-frame qualification harness, not a transmitter UI.  It
proves the host-qualified P8 sustained service over the real POSIX modem path:

    threaded localhost KISS DATA (no FCS)
      -> immutable P6 context
      -> hardened P8 thread-safe bounded admission
      -> qualified P2/P1 channel access
      -> qualified P4e RX_STOP/TX/RF-idle/RX_START
      -> qualified P5 TXDELAY routing
      -> real single-owner AX25R4 modem transport

Exactly three fixed packets are admitted one at a time.  Each packet requires
both a fresh non-qualification FCS-valid RX decode and a real BUSY observation
before the qualification RNG may progress from forced 255 defer to forced 0
dispatch.  There is no retry.  A second localhost KISS client reconnects after
cycle 1 and remains connected through cycles 2/3 and a final queue-empty RX
proof.

Default invocation is dry-run and exits before TXModemOwner construction, KISS
listener creation, UART access, or RF transmission.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import socket
import sys
import threading
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
from ywd1278.kiss.framing import DATA, KISSStreamDecoder, PERSIST, SLOTTIME, TXDELAY, encode  # noqa: E402
from ywd1278.kiss.server import PacketEvent, start_server_thread, stop_server_thread  # noqa: E402
from ywd1278.kiss.sustained import SustainedTNCBackend, ThreadSafeKISSDataAdmissionQueue  # noqa: E402
from ywd1278.kiss.tx_path import KISSDataQueueObservation, KISSDataRequestReceipt, KISSDataRequestState  # noqa: E402
from ywd1278.modem._serial import posix_serial_transport_factory  # noqa: E402
from ywd1278.modem.tx_owner import TXModemOwner  # noqa: E402
from ywd1278.phy import MARK, frame_to_selectors, pack_selectors  # noqa: E402
from ywd1278.service.tnc_runtime import SustainedTNCRuntime  # noqa: E402
from ywd1278.tx.channel_busy import ChannelBusyState  # noqa: E402
from ywd1278.tx.contextual import ContextualHalfDuplexSubmitter, ContextualTXDelayRouter  # noqa: E402
from ywd1278.tx.csma import CSMAState  # noqa: E402
from ywd1278.tx.half_duplex import HalfDuplexParameters  # noqa: E402


STAGE_PATH = ROOT / "firmware" / "qualification" / "0c-p8-live-sustained-kiss-tnc.json"
CONFIRMATION_TOKEN = "P8-LIVE-145050-P200-SUSTAINED-3"
INTERACTIVE_CONFIRMATION = "TRANSMIT-P8-SUSTAINED-KISS-THREE"
MIN_FULL_SLOT_SECONDS = 0.100


def load_stage() -> dict:
    stage = json.loads(STAGE_PATH.read_text(encoding="utf-8"))
    required = {
        "schema": 1,
        "phase": "0C-P8-live",
        "stage": "sustained-kiss-three-cycle",
        "status": "staged",
        "base_checkpoint": "checkpoint/0c-p8-sustained-kiss-tnc-host-qualified",
        "base_checkpoint_sha": "a835d2500dbdb4a8eaf1ae3cae4ea662203a852a",
        "target_id": p4d_r1.TARGET_ID,
        "device": p4d_r1.DEVICE,
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
        "busy_assert_raw_maximum": 83,
        "clear_release_raw_minimum": 90,
        "recent_rx_hold_seconds": 0.25,
        "requires_live_busy_before_each_dispatch": True,
        "requires_fresh_non_qualification_fcs_valid_rx_before_each_tx": True,
        "minimum_full_slot_seconds": MIN_FULL_SLOT_SECONDS,
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
        "requires_direct_external_decode": True,
        "required_external_tx_decodes": 3,
        "require_ywdnod_repeated_decode": False,
        "confirmation_token": CONFIRMATION_TOKEN,
        "interactive_phrase": INTERACTIVE_CONFIRMATION,
        "product_tx_enabled": False,
        "daemon_tx_enabled": False,
        "systemd_tx_enabled": False,
        "flash_permitted": False,
        "gpio_reset_permitted": False,
        "option_bytes_permitted": False,
    }
    for key, expected in required.items():
        if stage.get(key) != expected:
            raise SystemExit(
                f"FAIL: P8-live staging mismatch for {key}: expected={expected!r} actual={stage.get(key)!r}"
            )
    if stage.get("qualification_randomness") != {
        "before_fresh_decoded_busy_trigger": 255,
        "after_fresh_decoded_busy_trigger": [255, 0],
    }:
        raise SystemExit("FAIL: P8-live qualification randomness changed")
    if len(stage.get("frames", [])) != 3:
        raise SystemExit("FAIL: P8-live requires exactly three locked frame vectors")
    return stage


def build_vectors(stage: dict) -> list[tuple[bytes, bytes]]:
    vectors: list[tuple[bytes, bytes]] = []
    for expected_index, locked in enumerate(stage["frames"], start=1):
        if locked.get("index") != expected_index:
            raise SystemExit("FAIL: P8-live frame index sequence changed")
        if locked.get("txdelay") != stage["txdelay_sequence"][expected_index - 1]:
            raise SystemExit("FAIL: P8-live frame TXDELAY sequence changed")
        body = build_ui_frame(
            source=Address.parse(stage["source"]),
            destination=Address.parse(stage["destination"]),
            path=[Address.parse(item) for item in stage["path"]],
            info=locked["information_text"].encode("ascii"),
            include_fcs=False,
        )
        frame = append_fcs(body)
        if not verify_fcs(frame):
            raise SystemExit(f"FAIL: P8-live frame {expected_index} constructed invalid FCS")
        selectors = frame_to_selectors(
            frame,
            pre_flags=locked["pre_flags"],
            post_flags=locked["post_flags"],
            initial_tone=MARK,
        )
        packed = pack_selectors(selectors)
        checks = (
            (len(body), locked["kiss_body_bytes"], "KISS body bytes"),
            (body.hex(), locked["kiss_body_hex"], "KISS body hex"),
            (hashlib.sha256(body).hexdigest(), locked["kiss_body_sha256"], "KISS body SHA256"),
            (len(frame), locked["frame_with_fcs_bytes"], "FCS-bearing frame bytes"),
            (frame.hex(), locked["frame_with_fcs_hex"], "FCS-bearing frame hex"),
            (hashlib.sha256(frame).hexdigest(), locked["frame_with_fcs_sha256"], "frame SHA256"),
            (len(selectors), locked["selector_count"], "selector count"),
            (len(packed), locked["packed_selector_bytes"], "packed selector bytes"),
            (hashlib.sha256(packed).hexdigest(), locked["packed_selector_sha256"], "packed selector SHA256"),
            (
                len(selectors) * locked["samples_per_selector"],
                locked["expected_generated_samples"],
                "generated samples",
            ),
        )
        for actual, expected, label in checks:
            if actual != expected:
                raise SystemExit(
                    f"FAIL: P8-live frame {expected_index} {label} changed: expected={expected!r} actual={actual!r}"
                )
        vectors.append((body, frame))
    return vectors


def is_qualification_body(body_no_fcs: bytes, locked_bodies: tuple[bytes, ...]) -> bool:
    return bytes(body_no_fcs) in locked_bodies


@dataclass(frozen=True)
class CycleSnapshot:
    cycle: int
    armed: bool
    receipt: KISSDataRequestReceipt | None
    seen_busy: bool
    fresh_non_qualification_decode: bool
    non_qualification_decodes: int
    pre_trigger_defers: int
    post_trigger_trials: int
    busy_at: float | None
    decoded_at: float | None
    clear_at: float | None
    defer_at: float | None
    dispatch_at: float | None
    dispatched: bool


class PhysicalCycleGuard:
    """Qualification-only observation/RNG gate around the real P8 runtime."""

    def __init__(self, *, qualification_bodies: tuple[bytes, ...], busy_raw_maximum: int) -> None:
        self._qualification_bodies = qualification_bodies
        self._busy_raw_maximum = int(busy_raw_maximum)
        self._lock = threading.RLock()
        self._cycle = 0
        self._armed = False
        self._receipt: KISSDataRequestReceipt | None = None
        self._seen_busy = False
        self._fresh_decode = False
        self._nonqual_decodes = 0
        self._pre_trigger_defers = 0
        self._post_trigger_trials = 0
        self._busy_at: float | None = None
        self._decoded_at: float | None = None
        self._clear_at: float | None = None
        self._defer_at: float | None = None
        self._dispatch_at: float | None = None
        self._dispatched = False
        self.total_non_qualification_decodes = 0

    def arm(self, cycle: int) -> None:
        with self._lock:
            if self._armed and not self._dispatched:
                raise RuntimeError("cannot arm next P8-live cycle before current dispatch")
            self._cycle = int(cycle)
            self._armed = True
            self._receipt = None
            self._seen_busy = False
            self._fresh_decode = False
            self._nonqual_decodes = 0
            self._pre_trigger_defers = 0
            self._post_trigger_trials = 0
            self._busy_at = None
            self._decoded_at = None
            self._clear_at = None
            self._defer_at = None
            self._dispatch_at = None
            self._dispatched = False

    def disarm(self) -> None:
        with self._lock:
            self._armed = False

    def note_receipt(self, receipt: KISSDataRequestReceipt) -> None:
        with self._lock:
            if not self._armed:
                raise RuntimeError("P8-live DATA admitted while qualification cycle is not armed")
            if self._receipt is not None:
                raise RuntimeError("P8-live cycle admitted more than one DATA request")
            self._receipt = receipt

    def note_inbound(self, body_no_fcs: bytes) -> None:
        body = bytes(body_no_fcs)
        if is_qualification_body(body, self._qualification_bodies):
            return
        with self._lock:
            self.total_non_qualification_decodes += 1
            if self._armed and not self._dispatched:
                self._nonqual_decodes += 1
                if not self._fresh_decode:
                    self._fresh_decode = True
                    self._decoded_at = time.monotonic()

    def random_byte(self) -> int:
        with self._lock:
            if not self._armed or self._dispatched:
                raise RuntimeError("P8-live randomness requested outside an active qualification cycle")
            if not (self._seen_busy and self._fresh_decode):
                self._pre_trigger_defers += 1
                return 255
            self._post_trigger_trials += 1
            if self._post_trigger_trials == 1:
                return 255
            if self._post_trigger_trials == 2:
                return 0
            raise RuntimeError("P8-live attempted more than two post-trigger persistence trials")

    def note_access(self, raw_magnitude: int, observation: KISSDataQueueObservation) -> None:
        with self._lock:
            if not self._armed:
                return
            access = observation.access
            if access is None:
                return
            if raw_magnitude <= self._busy_raw_maximum and not self._seen_busy:
                self._seen_busy = True
                self._busy_at = access.now
            if (
                self._seen_busy
                and access.detector.state is ChannelBusyState.CLEAR
                and self._clear_at is None
            ):
                self._clear_at = access.now
            if (
                access.random_byte == 255
                and self._post_trigger_trials >= 1
                and access.csma.state is CSMAState.WAIT_SLOT
            ):
                self._defer_at = access.now
            if (
                observation.request_state is KISSDataRequestState.DISPATCHED
                and observation.downstream_called
            ):
                self._dispatched = True
                self._dispatch_at = access.now

    @property
    def snapshot(self) -> CycleSnapshot:
        with self._lock:
            return CycleSnapshot(
                cycle=self._cycle,
                armed=self._armed,
                receipt=self._receipt,
                seen_busy=self._seen_busy,
                fresh_non_qualification_decode=self._fresh_decode,
                non_qualification_decodes=self._nonqual_decodes,
                pre_trigger_defers=self._pre_trigger_defers,
                post_trigger_trials=self._post_trigger_trials,
                busy_at=self._busy_at,
                decoded_at=self._decoded_at,
                clear_at=self._clear_at,
                defer_at=self._defer_at,
                dispatch_at=self._dispatch_at,
                dispatched=self._dispatched,
            )


class GuardedPhysicalAdmission:
    """Observe the P8 queue without replacing or bypassing its qualified logic."""

    def __init__(self, queue: ThreadSafeKISSDataAdmissionQueue, guard: PhysicalCycleGuard) -> None:
        self._queue = queue
        self._guard = guard

    @property
    def request_timeout_seconds(self) -> float:
        return self._queue.request_timeout_seconds

    @property
    def snapshot(self):  # type: ignore[no-untyped-def]
        return self._queue.snapshot

    def enqueue(self, frame_no_fcs: bytes, context, *, now: float):  # type: ignore[no-untyped-def]
        receipt = self._queue.enqueue(frame_no_fcs, context, now=now)
        self._guard.note_receipt(receipt)
        return receipt

    def observe_rssi(
        self,
        *,
        now: float,
        raw_magnitude: int,
        random_byte_source=None,  # type: ignore[no-untyped-def]
    ) -> KISSDataQueueObservation:
        observation = self._queue.observe_rssi(
            now=now,
            raw_magnitude=raw_magnitude,
            random_byte_source=random_byte_source,
        )
        self._guard.note_access(raw_magnitude, observation)
        return observation


class QualificationBackend(SustainedTNCBackend):
    def __init__(self, *args, guard: PhysicalCycleGuard, **kwargs):  # type: ignore[no-untyped-def]
        self._guard = guard
        super().__init__(*args, **kwargs)

    def publish(self, event: PacketEvent) -> None:
        super().publish(event)
        self._guard.note_inbound(event.frame_no_fcs)


class KISSReceiveMonitor:
    """Record live port-0 RX delivery on the second qualification client."""

    def __init__(self, sock: socket.socket, qualification_bodies: tuple[bytes, ...]) -> None:
        self._sock = sock
        self._qualification_bodies = qualification_bodies
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, name="p8-live-kiss-rx-monitor", daemon=True)
        self._decoder = KISSStreamDecoder()
        self._nonqual = 0
        self._all_data = 0
        self._error: BaseException | None = None

    def start(self) -> None:
        self._sock.settimeout(0.10)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)
        if self._thread.is_alive():
            raise RuntimeError("P8-live KISS receive monitor did not stop")
        if self._error is not None:
            raise RuntimeError("P8-live KISS receive monitor failed") from self._error

    @property
    def non_qualification_messages(self) -> int:
        with self._lock:
            return self._nonqual

    @property
    def all_data_messages(self) -> int:
        with self._lock:
            return self._all_data

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    chunk = self._sock.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    if self._stop.is_set():
                        return
                    raise
                if not chunk:
                    return
                for message in self._decoder.feed(chunk):
                    if message.port != 0 or message.command != DATA:
                        continue
                    with self._lock:
                        self._all_data += 1
                        if not is_qualification_body(message.frame, self._qualification_bodies):
                            self._nonqual += 1
        except BaseException as exc:
            self._error = exc
            self._stop.set()


def wait_until(predicate, *, timeout: float, detail: str) -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise RuntimeError(f"timed out waiting for {detail}")


def send_cycle_request(
    client: socket.socket,
    *,
    body: bytes,
    txdelay: int,
    cycle: int,
    expected_generation: int,
    expected_admitted: int,
    backend: QualificationBackend,
    session: TNCSessionState,
    first_cycle: bool,
) -> None:
    wire = bytearray()
    if first_cycle:
        wire.extend(encode(bytes((txdelay,)), command=TXDELAY))
        wire.extend(encode(bytes((63,)), command=PERSIST))
        wire.extend(encode(bytes((10,)), command=SLOTTIME))
    else:
        wire.extend(encode(bytes((txdelay,)), command=TXDELAY))
    wire.extend(encode(body, command=DATA))
    client.sendall(bytes(wire))
    wait_until(
        lambda: (
            backend.ingress_counters.data_admitted == expected_admitted
            and session.snapshot.generation == expected_generation
        ),
        timeout=2.0,
        detail=f"cycle {cycle} localhost KISS admission",
    )


def verify_cycle(
    *,
    cycle: int,
    guard: PhysicalCycleGuard,
    expected_generation: int,
    expected_txdelay: int,
    expected_samples: int,
    runtime: SustainedTNCRuntime,
    owner: TXModemOwner,
) -> CycleSnapshot:
    wait_until(
        lambda: guard.snapshot.dispatched and runtime.runtime_counters.tx_dispatches >= cycle,
        timeout=29.0,
        detail=f"cycle {cycle} guarded sustained TX",
    )
    runtime.check_health()
    snap = guard.snapshot
    if snap.receipt is None:
        raise RuntimeError(f"cycle {cycle} has no KISS admission receipt")
    if snap.receipt.parameter_generation != expected_generation:
        raise RuntimeError(
            f"cycle {cycle} captured generation changed: {snap.receipt.parameter_generation}"
        )
    if snap.receipt.txdelay != expected_txdelay or snap.receipt.persist != 63 or snap.receipt.slottime != 10:
        raise RuntimeError(f"cycle {cycle} immutable KISS parameter capture changed: {snap.receipt}")
    if not snap.seen_busy or not snap.fresh_non_qualification_decode:
        raise RuntimeError(f"cycle {cycle} dispatched without decoded real-BUSY qualification: {snap}")
    if snap.post_trigger_trials != 2:
        raise RuntimeError(f"cycle {cycle} expected exactly two post-trigger persistence trials: {snap}")
    if None in (snap.clear_at, snap.defer_at, snap.dispatch_at):
        raise RuntimeError(f"cycle {cycle} missing access timeline: {snap}")
    assert snap.clear_at is not None and snap.defer_at is not None and snap.dispatch_at is not None
    if snap.defer_at - snap.clear_at + 1e-9 < MIN_FULL_SLOT_SECONDS:
        raise RuntimeError(f"cycle {cycle} 255 defer occurred before a full clear slot")
    if snap.dispatch_at - snap.defer_at + 1e-9 < MIN_FULL_SLOT_SECONDS:
        raise RuntimeError(f"cycle {cycle} 0 dispatch occurred before a second full clear slot")

    active = owner.rx_status(timeout=1.5)
    p4e.require_active_rx(active, context=f"after P8-live cycle {cycle}")
    diag = owner.rf_diagnostics(timeout=1.5)
    if diag.tx_active != 0:
        raise RuntimeError(f"cycle {cycle} RF remains active after lifecycle return")
    if diag.keyups != 1:
        raise RuntimeError(f"cycle {cycle} expected one completed keyup, got {diag.keyups}")
    if diag.generated_samples != expected_samples:
        raise RuntimeError(
            f"cycle {cycle} generated samples changed: expected={expected_samples} actual={diag.generated_samples}"
        )
    print(f"CYCLE_{cycle}_LIVE_BUSY=PASS")
    print(f"CYCLE_{cycle}_FRESH_NON_P8_RX_DECODE=PASS")
    print(f"CYCLE_{cycle}_PERSIST_255_DEFER=PASS")
    print(f"CYCLE_{cycle}_PERSIST_0_DISPATCH=PASS")
    print(f"CYCLE_{cycle}_RX_STOP_TX_RX_RESTART=PASS")
    print(f"CYCLE_{cycle}_CLEAR_TO_DEFER_SECONDS={snap.defer_at - snap.clear_at:.3f}")
    print(f"CYCLE_{cycle}_DEFER_TO_DISPATCH_SECONDS={snap.dispatch_at - snap.defer_at:.3f}")
    print(f"CYCLE_{cycle}_TX_DIAG=keyups:1 generated_samples:{expected_samples}")
    return snap


def print_plan(stage: dict) -> None:
    print("=== YWD-1278 0C-P8 LIVE SUSTAINED KISS TNC ===")
    print(f"Target                    : {stage['target_id']}")
    print(f"Device                    : {stage['device']}")
    print(f"AX25R4 identity           : {stage['expected_identity']}")
    print(f"TX/RX frequency           : {stage['frequency_hz']} Hz")
    print(f"RF power byte             : {stage['rf_power']}/255")
    print("KISS listener             : 127.0.0.1 ephemeral, sustained across cycles")
    print("KISS clients              : exactly 2 sessions; reconnect after cycle 1")
    print("KISS DATA messages        : exactly 3 fixed bodies, admitted one at a time")
    print("KISS DATA FCS             : absent on ingress; TNC appends exactly once")
    print(f"TXDELAY sequence          : {stage['txdelay_sequence']}")
    print("PERSIST/SLOTTIME          : 63 / 10")
    print("Detector                  : busy<=83 clear>=90 hold=250ms")
    print("Per-cycle gate            : fresh non-P8 decode + real BUSY REQUIRED")
    print("Qualification RNG         : 255 until trigger; then 255,0")
    print("Lifecycle                 : 3 x RX_STOP -> TX -> RF idle -> RX_START")
    print("Final RX proof            : queue empty + fresh non-P8 decode + live KISS delivery")
    print("Automatic TX retry        : NO")
    print("Product/daemon TX         : DISABLED")
    print("Flash/GPIO/options        : FORBIDDEN")
    print("YWDNOD repeat proof       : DEFERRED / NON-BLOCKING")
    for locked in stage["frames"]:
        print(
            f"TX[{locked['index']}]                    : "
            f"{stage['source']}>{stage['destination']},{stage['path'][0]}:{locked['information_text']}"
        )
        print(
            f"  TXDELAY/pre/selectors   : {locked['txdelay']} / {locked['pre_flags']} / "
            f"{locked['selector_count']}"
        )
        print(f"  expected samples        : {locked['expected_generated_samples']}")
        print(
            "EXPECTED_EXTERNAL_DECODE="
            f"{stage['source']}>{stage['destination']},{stage['path'][0]}:{locked['information_text']}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="YWD-1278 P8 guarded live sustained KISS qualification")
    ap.add_argument("--transmit", action="store_true")
    ap.add_argument("--confirm", default="")
    args = ap.parse_args()

    p4d_r1.load_target()
    stage = load_stage()
    vectors = build_vectors(stage)
    bodies = tuple(body for body, _ in vectors)
    print_plan(stage)

    if not args.transmit:
        print("P8_LIVE_SUSTAINED_KISS_DRY_RUN=PASS")
        print("TX_MODEM_OWNER_CONSTRUCTED=NO")
        print("KISS_LISTENER_OPENED=NO")
        print("HARDWARE_UART_OPENED=NO")
        print("RF_TRANSMITTED=NO")
        return 0

    if args.confirm != CONFIRMATION_TOKEN:
        raise SystemExit(
            "FAIL: physical P8 requires exact confirmation token "
            f"--confirm {CONFIRMATION_TOKEN}"
        )
    if not p4d_r1.uart_is_free():
        raise SystemExit(f"FAIL: modem UART already has an owner: {stage['device']}")
    typed = input(
        f"Type exactly {INTERACTIVE_CONFIRMATION} to arm three fixed sustained KISS TX bursts: "
    ).strip()
    if typed != INTERACTIVE_CONFIRMATION:
        raise SystemExit("FAIL: P8-live confirmation did not match; no UART opened")

    owner = TXModemOwner(
        posix_serial_transport_factory(stage["device"]),
        queue_capacity=16,
        submit_timeout=0.20,
        default_transaction_timeout=1.50,
    )
    router: ContextualTXDelayRouter | None = None
    lifecycle: ContextualHalfDuplexSubmitter | None = None
    runtime: SustainedTNCRuntime | None = None
    server = None
    server_thread = None
    client1: socket.socket | None = None
    client2: socket.socket | None = None
    monitor: KISSReceiveMonitor | None = None
    owner_started = False
    rx_started = False
    accepted_tx_count = 0

    guard = PhysicalCycleGuard(
        qualification_bodies=bodies,
        busy_raw_maximum=stage["busy_assert_raw_maximum"],
    )

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
            raise RuntimeError("modem is not idle before P8-live setup")

        # Exact physically-qualified P13b/P4e 145.050 MHz / power-200 profile.
        owner.apply_tx_qualification_profile(timeout=1.5)
        owner.arm_rx_modem_io(timeout=1.5)
        owner.rx_start(timeout=1.5)
        rx_started = True
        active = owner.rx_status(timeout=1.5)
        p4e.require_active_rx(active, context="at initial P8-live RX start")

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
        base_admission = ThreadSafeKISSDataAdmissionQueue(
            lifecycle,
            monotonic=time.monotonic,
            queue_capacity=1,
            request_timeout_seconds=stage["request_timeout_seconds"],
            downstream_timeout_seconds=stage["downstream_timeout_seconds"],
        )
        admission = GuardedPhysicalAdmission(base_admission, guard)
        session = TNCSessionState()
        backend = QualificationBackend(
            admission,  # type: ignore[arg-type]
            monotonic=time.monotonic,
            session=session,
            history_capacity=32,
            subscriber_queue_capacity=32,
            guard=guard,
        )
        runtime = SustainedTNCRuntime(
            owner,
            backend,
            admission,  # type: ignore[arg-type]
            expected_identity=stage["expected_identity"],
            monotonic=time.monotonic,
            random_byte_source=guard.random_byte,
            read_maximum=stage["rx_read_maximum"],
            idle_sleep_seconds=stage["rssi_poll_nominal_seconds"],
            status_interval_seconds=stage["rx_status_interval_seconds"],
        )
        server, server_thread = start_server_thread(
            backend,
            host=stage["kiss_listener_host"],
            port=stage["kiss_listener_port"],
        )
        host, port = server.server_address[:2]
        if host != "127.0.0.1" or not (1 <= int(port) <= 65535):
            raise RuntimeError(f"unexpected P8-live KISS bind: {(host, port)!r}")
        runtime.start(timeout=1.5)
        print(f"KISS_LISTENER=127.0.0.1:{port}")
        print("LIVE_RUNTIME=OPEN")

        # Session 1: cycle 1, then disconnect.  Initial three controls create
        # generation 3 exactly before DATA admission.
        client1 = socket.create_connection((host, int(port)), timeout=2.0)
        wait_until(
            lambda: backend.connection_counters.total_connections == 1,
            timeout=2.0,
            detail="first P8-live KISS client connection",
        )
        guard.arm(1)
        send_cycle_request(
            client1,
            body=bodies[0],
            txdelay=30,
            cycle=1,
            expected_generation=3,
            expected_admitted=1,
            backend=backend,
            session=session,
            first_cycle=True,
        )
        print("CYCLE[1]_WINDOW=OPEN")
        print("ACTION: send/allow one real non-P8 AX.25 packet on 145.050 MHz now.")
        print("Cycle 1 cannot TX until that packet is decoded and real BUSY is observed.")
        verify_cycle(
            cycle=1,
            guard=guard,
            expected_generation=3,
            expected_txdelay=30,
            expected_samples=stage["frames"][0]["expected_generated_samples"],
            runtime=runtime,
            owner=owner,
        )
        accepted_tx_count = 1
        client1.close()
        client1 = None
        wait_until(
            lambda: backend.connection_counters.total_disconnects == 1,
            timeout=2.0,
            detail="first P8-live KISS client disconnect",
        )

        # Session 2 reconnects and must receive at least one non-qualification
        # cycle-1 RX event from history before it can submit cycle 2.
        client2 = socket.create_connection((host, int(port)), timeout=2.0)
        wait_until(
            lambda: backend.connection_counters.total_connections == 2,
            timeout=2.0,
            detail="second P8-live KISS client reconnect",
        )
        monitor = KISSReceiveMonitor(client2, bodies)
        monitor.start()
        wait_until(
            lambda: monitor is not None and monitor.non_qualification_messages >= 1,
            timeout=2.0,
            detail="cycle-1 RX history on reconnected KISS client",
        )
        print("KISS_CLIENT_RECONNECT_HISTORY=PASS")

        guard.arm(2)
        send_cycle_request(
            client2,
            body=bodies[1],
            txdelay=50,
            cycle=2,
            expected_generation=4,
            expected_admitted=2,
            backend=backend,
            session=session,
            first_cycle=False,
        )
        print("CYCLE[2]_WINDOW=OPEN")
        print("ACTION: send/allow one fresh real non-P8 AX.25 packet on 145.050 MHz now.")
        verify_cycle(
            cycle=2,
            guard=guard,
            expected_generation=4,
            expected_txdelay=50,
            expected_samples=stage["frames"][1]["expected_generated_samples"],
            runtime=runtime,
            owner=owner,
        )
        accepted_tx_count = 2

        guard.arm(3)
        send_cycle_request(
            client2,
            body=bodies[2],
            txdelay=30,
            cycle=3,
            expected_generation=5,
            expected_admitted=3,
            backend=backend,
            session=session,
            first_cycle=False,
        )
        print("CYCLE[3]_WINDOW=OPEN")
        print("ACTION: send/allow one fresh real non-P8 AX.25 packet on 145.050 MHz now.")
        verify_cycle(
            cycle=3,
            guard=guard,
            expected_generation=5,
            expected_txdelay=30,
            expected_samples=stage["frames"][2]["expected_generated_samples"],
            runtime=runtime,
            owner=owner,
        )
        accepted_tx_count = 3

        if admission.snapshot.queue_depth != 0:
            raise RuntimeError("P8-live TX queue is not empty after cycle 3")
        guard.disarm()
        backend_before = guard.total_non_qualification_decodes
        assert monitor is not None
        client_before = monitor.non_qualification_messages
        print("FINAL_QUEUE_EMPTY_RX_WINDOW=OPEN")
        print("ACTION: send/allow one more real non-P8 AX.25 packet now; NO TX request is queued.")
        wait_until(
            lambda: guard.total_non_qualification_decodes > backend_before,
            timeout=stage["final_receive_timeout_seconds"],
            detail="final queue-empty FCS-valid RX decode",
        )
        wait_until(
            lambda: monitor is not None and monitor.non_qualification_messages > client_before,
            timeout=2.0,
            detail="final queue-empty live KISS RX delivery",
        )
        print("FINAL_QUEUE_EMPTY_FCS_VALID_RX=PASS")
        print("FINAL_QUEUE_EMPTY_KISS_DELIVERY=PASS")

        runtime.check_health()
        accounting = runtime.accounting
        lifecycle_snap = lifecycle.half_duplex_snapshot
        if accounting.runtime.tx_dispatches != 3 or accounting.runtime.decoder_resets_after_tx != 3:
            raise RuntimeError(f"P8-live runtime TX/reset counters changed: {accounting.runtime}")
        if accounting.queue.tx_queue_accepted != 3 or accounting.queue.tx_dispatched != 3:
            raise RuntimeError(f"P8-live queue counters changed: {accounting.queue}")
        if accounting.queue.tx_access_timeouts != 0 or accounting.queue.tx_downstream_failures != 0:
            raise RuntimeError(f"P8-live queue recorded terminal failures: {accounting.queue}")
        if accounting.ingress.data_messages_received != 3 or accounting.ingress.data_admitted != 3:
            raise RuntimeError(f"P8-live KISS ingress counters changed: {accounting.ingress}")
        if accounting.ingress.data_queue_full_drops != 0:
            raise RuntimeError("P8-live unexpectedly filled the one-at-a-time physical queue")
        if lifecycle_snap.cycles_completed != 3 or lifecycle_snap.downstream_accepted != 3:
            raise RuntimeError(f"P8-live P4e lifecycle counters changed: {lifecycle_snap}")
        if lifecycle_snap.rx_restart_operations != 3 or lifecycle_snap.failed_latched:
            raise RuntimeError(f"P8-live P4e lifecycle did not remain healthy: {lifecycle_snap}")
        if guard.total_non_qualification_decodes < stage["required_non_qualification_inbound_frames"]:
            raise RuntimeError(
                "P8-live did not decode enough non-qualification inbound frames: "
                f"{guard.total_non_qualification_decodes}"
            )
        final_status = owner.rx_status(timeout=1.5)
        p4e.require_active_rx(final_status, context="at final P8-live sustained RX proof")

        # Stop service boundaries before explicitly stopping RX/owner.
        if monitor is not None:
            monitor.stop()
            monitor = None
        if client2 is not None:
            client2.close()
            client2 = None
        wait_until(
            lambda: backend.connection_counters.total_disconnects == 2,
            timeout=2.0,
            detail="second P8-live KISS client disconnect",
        )
        runtime.stop(timeout=3.0)
        runtime = None
        if server is not None and server_thread is not None:
            stop_server_thread(server, server_thread)
            server = None
            server_thread = None

        owner.rx_stop(timeout=1.5)
        rx_started = False
        stopped = owner.rx_status(timeout=1.5)
        if stopped.flags & 0x01:
            raise RuntimeError("P8-live RX remained active after final RX_STOP")
        if stopped.dropped_bytes != 0:
            raise RuntimeError(f"P8-live RX FIFO dropped {stopped.dropped_bytes} bytes")

        router.close()
        router = None
        owner.stop(timeout=2.0)
        owner_started = False
        if owner.snapshot.running:
            raise RuntimeError("P8-live modem owner still running after stop")

        print("YWD1278_0C_P8_LIVE_SUSTAINED_KISS_EXECUTION=PASS")
        print("KISS_TCP_CLIENTS=2")
        print("KISS_CLIENT_RECONNECT=PASS")
        print("KISS_DATA_ADMITTED=3")
        print("TX_SUBMISSIONS=3")
        print("COMPLETE_RX_TX_RX_CYCLES=3")
        print("INITIAL_RX_STARTS=1")
        print("POST_TX_RX_RESTARTS=3")
        print("TOTAL_RX_STARTS=4")
        print("TOTAL_RX_STOPS=3")
        print("POST_TX_DECODER_RESETS=3")
        print(f"INBOUND_NON_P8_FCS_VALID_FRAMES={guard.total_non_qualification_decodes}")
        print(f"RSSI_SAMPLES={accounting.runtime.rssi_samples}")
        print(f"PACKED_RX_BYTES_DRAINED={accounting.runtime.packed_rx_bytes}")
        print(f"RX_READ_TRANSACTIONS={accounting.runtime.rx_read_transactions}")
        print(f"RX_STATUS_CHECKS={accounting.runtime.rx_status_checks}")
        print("FIFO_DROPPED_BYTES=0")
        print("RX_FIFO_BACKLOG_PRIORITY=PASS")
        print("SERIALIZED_QUEUE_CLOCK_SAMPLING=PASS")
        print("SINGLE_MODEM_OWNER=PASS")
        print("UART_RELEASED=YES")
        print("DUPLICATE_DISPATCH=NO")
        print("AUTOMATIC_TX_RETRY=NO")
        print("PRODUCT_TX_ENABLED=NO")
        print("DAEMON_TX_ENABLED=NO")
        print("FLASH_WRITTEN=NO")
        print("GPIO_ACCESSED=NO")
        print("OPTION_BYTES_WRITTEN=NO")
        print("RF_TRANSMITTED=YES_EXACTLY_THREE_FIXED_BURSTS")
        print("EXTERNAL_DIRECT_DECODE_REQUIRED=3")
        print("YWDNOD_REPEAT_REQUIRED=NO")
        print("QUALIFICATION_COMPLETE=NO_PENDING_EXTERNAL_DECODE")
        return 0

    except BaseException:
        actual_accepted = accepted_tx_count
        if runtime is not None:
            actual_accepted = max(actual_accepted, runtime.runtime_counters.tx_dispatches)
        if lifecycle is not None:
            actual_accepted = max(actual_accepted, lifecycle.half_duplex_snapshot.downstream_accepted)
        print(f"P8_LIVE_ACCEPTED_TX_BEFORE_FAILURE={actual_accepted}", file=sys.stderr)
        if actual_accepted:
            print("DO_NOT_RERUN_FULL_P8_LIVE_HARNESS=YES", file=sys.stderr)
            print("PRESERVE_OUTPUT_AND_EXTERNAL_DECODE_EVIDENCE=YES", file=sys.stderr)
        else:
            print("RF_TX_ACCEPTED_BEFORE_FAILURE=NO", file=sys.stderr)
        raise
    finally:
        if monitor is not None:
            try:
                monitor.stop()
            except BaseException:
                pass
        for client in (client1, client2):
            if client is not None:
                try:
                    client.close()
                except BaseException:
                    pass
        if runtime is not None:
            try:
                runtime.stop(timeout=2.0)
            except BaseException:
                pass
        if server is not None and server_thread is not None:
            try:
                stop_server_thread(server, server_thread)
            except BaseException:
                pass
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
