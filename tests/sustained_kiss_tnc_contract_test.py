#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def git_blob(path: str) -> str:
    return subprocess.check_output(
        ["git", "hash-object", path],
        cwd=ROOT,
        text=True,
    ).strip()


# P8 remains additive around the physically-qualified P7 graph. These blobs
# remain byte-for-byte unchanged through the R1 scheduler repair.
FROZEN = {
    "src/ywd1278/kiss/tx_path.py": "44f4b6c0bddd6ac0977646ac417e448c9a1398ea",
    "src/ywd1278/kiss/tx_backend.py": "e06c1a619a02ecb4cf2073a3f270be1b2d54ea0e",
    "src/ywd1278/kiss/control.py": "b6c23879027c15ef944a9e411429694a312d606e",
    "src/ywd1278/tx/contextual.py": "c9de1ed7e751d6d96eadc4f6ac7b027cfe859012",
    "src/ywd1278/tx/half_duplex.py": "d826fd4a53d52ba359eb0b45642370db0f0cb7cc",
    "src/ywd1278/tx/txdelay.py": "b8035a58c4b48765c580dab06bcdb054a9801c8c",
    "src/ywd1278/tx/broker.py": "1e3307dccea4f2805d32cb9be5b34f3537e29c4f",
    "src/ywd1278/phy/bell202_tx.py": "39677faa3302a74da9fbae6fa858899e54f1874f",
}
for path, expected in FROZEN.items():
    actual = git_blob(path)
    assert actual == expected, f"frozen P7 dependency changed: {path} {actual} != {expected}"

assert git_blob("src/ywd1278/daemon.py") == "0571c4a88a5d498b48cf6a6cc19b511655f8fb07"
assert git_blob("systemd/ywd-1278.service") == "ab7dc6aa6af8237d20e41a1357083f0321fd7062"

sustained = text("src/ywd1278/kiss/sustained.py")
runtime = text("src/ywd1278/service/tnc_runtime.py")

# Concurrency is additive composition. The wrapper samples its explicitly
# injected monotonic clock only after acquiring the same lock that serializes
# frozen P7 queue mutation, preventing pre-lock timestamp reordering.
assert "class ThreadSafeKISSDataAdmissionQueue" in sustained
assert "self._queue = KISSDataAdmissionQueue(" in sustained
assert "monotonic: MonotonicClock" in sustained
assert "self._monotonic = monotonic" in sustained
assert "threading.RLock()" in sustained
assert "serialized_now = float(self._monotonic())" in sustained
assert sustained.count("serialized_now = float(self._monotonic())") == 2
assert "now=serialized_now" in sustained
assert "class SustainedTNCBackend" in sustained
assert "total_connections" in sustained
assert "total_disconnects" in sustained

# Sustained scheduler retains caller-supplied timing/randomness and advances
# RSSI access only while a bounded request exists.
assert "monotonic: MonotonicClock" in runtime
assert "random_byte_source: RandomByteSource" in runtime
assert "if self._admission.snapshot.queue_depth:" in runtime
assert "self._owner.rx_rssi()" in runtime
assert "random_byte_source=self._random_byte_source" in runtime

# Already-captured packed RX bytes still outrank queued TX access, but R1 must
# never wait for an exact zero-length read from the continuously-producing
# AX25R4 sampler. Four maximum-size reads consume more than one complete 512 B
# firmware FIFO snapshot and then guarantee RSSI/CSMA a scheduling opportunity.
assert "RX_FIFO_DRAIN_READ_LIMIT = 4" in runtime
assert "def _drain_rx_fifo" in runtime
run_body = runtime[runtime.index("def _run"):runtime.index("def _drain_rx_fifo")]
assert run_body.index("self._drain_rx_fifo()") < run_body.index("if self._admission.snapshot.queue_depth:")
drain_body = runtime[runtime.index("def _drain_rx_fifo"):runtime.index("def _consume")]
assert "for _ in range(RX_FIFO_DRAIN_READ_LIMIT):" in drain_body
assert "chunk = self._owner.rx_read(self._read_maximum)" in drain_body
assert "if len(chunk) < self._read_maximum:" in drain_body
assert "self._consume(chunk)" in drain_body
assert "while not self._stop.is_set():" not in drain_body
assert "if not chunk:" not in drain_body
assert "zero-length RX_READ" in drain_body

# P4e discontinuity still requires a fresh Bell-202 decoder after every
# completed TX/RX restart cycle.
assert "self._decoder = StreamingBell202Decoder()" in runtime
assert "decoder_resets_after_tx" in runtime
assert "KISSDataRequestState.DISPATCHED" in runtime
assert "KISSDataRequestState.DOWNSTREAM_FAILED" in runtime
assert "service is fail-latched" in runtime

for token in (
    "parameters=self._backend.control_snapshot",
    "control=self._backend.control_counters",
    "ingress=self._backend.ingress_counters",
    "TNCQueueAccounting.from_access_snapshot",
    "connections=self._backend.connection_counters",
    "subscriber_drops=base.subscriber_drops",
):
    assert token in runtime

for source in (sustained, runtime):
    lower = source.lower()
    for forbidden in (
        "posixserial",
        "serialtransport",
        "stm32flash",
        "rpi.gpio",
        "gpiozero",
        "gpiod",
        "/dev/tty",
        "option byte",
        "transmit_selector_burst",
        ".transact(",
        "apply_tx_qualification_profile",
        "set_rx_frequency(",
        "set_freq",
        "frame_to_selectors",
    ):
        assert forbidden not in lower, f"forbidden P8 host mechanism {forbidden!r}"

# The original host checkpoint remains immutable historical evidence. R1 is an
# additive correction record discovered only when that scheduler first met the
# continuously-producing physical AX25R4 FIFO.
historical = json.loads(text("firmware/qualification/0c-p8-sustained-kiss-tnc-host.json"))
assert historical["phase"] == "0C-P8-host"
assert historical["status"] == "host-qualified"
assert historical["base_checkpoint_sha"] == "80249ab34da4c64d40d23d98d639db78d1691f5d"
assert historical["qualification_evidence"]["final_exact_head_ci"] == "success"
assert historical["safety"]["rf_transmitted"] is False

r1 = json.loads(text("firmware/qualification/0c-p8-sustained-kiss-tnc-host-r1.json"))
assert r1["phase"] == "0C-P8-host-R1"
assert r1["status"] in {"staged", "host-qualified"}
assert r1["base_checkpoint_sha"] == "a835d2500dbdb4a8eaf1ae3cae4ea662203a852a"
assert r1["historical_checkpoint_preserved"] is True
assert r1["regression"]["accepted_tx_before_failure"] == 0
assert r1["regression"]["failure_phase"] == "cycle-1 pre-dispatch"
assert r1["regression"]["rf_retry_safe_after_fix"] is True
assert r1["architecture"]["bounded_live_fifo_drain"] is True
assert r1["architecture"]["firmware_fifo_capacity_bytes"] == 512
assert r1["architecture"]["rx_read_maximum_bytes"] == 200
assert r1["architecture"]["drain_read_limit"] == 4
assert r1["architecture"]["maximum_bytes_per_drain_pass"] == 800
assert r1["architecture"]["partial_read_ends_drain_pass"] is True
assert r1["architecture"]["zero_length_read_required"] is False
assert r1["qualification"]["continuous_rx_source_never_empty_regression"] is True
assert r1["qualification"]["continuous_source_drain_returns"] is True
assert r1["qualification"]["continuous_source_expected_reads_per_pass"] == 4
assert r1["qualification"]["automatic_retry"] is False
assert r1["safety"]["host_only"] is True
assert r1["safety"]["posix_serial"] is False
assert r1["safety"]["uart_access"] is False
assert r1["safety"]["rf_transmitted"] is False
assert r1["physical_follow_on"]["authorized"] is False
assert r1["physical_follow_on"]["requires_new_checkpoint_after_r1_ci"] is True
assert r1["physical_follow_on"]["frequency_hz"] == 145050000
assert r1["physical_follow_on"]["rf_power"] == 200
assert r1["physical_follow_on"]["require_path"] == ["YWDNOD"]

print("P8_SUSTAINED_KISS_TNC_ARCHITECTURE_CONTRACT=PASS")
print("P7_ADMISSION_FROZEN=PASS")
print("P6_CONTROL_FROZEN=PASS")
print("P4E_HALF_DUPLEX_FROZEN=PASS")
print("P5_TXDELAY_FROZEN=PASS")
print("TX_BROKER_FROZEN=PASS")
print("THREAD_SAFE_QUEUE=COMPOSITION")
print("SERIALIZED_QUEUE_CLOCK_SAMPLING=PASS")
print("RX_FIFO_BACKLOG_PRIORITY=PASS_BOUNDED_LIVE_DRAIN")
print("RX_FIFO_ZERO_LENGTH_REQUIRED=NO")
print("CALLER_SUPPLIED_TIME_AND_RANDOMNESS=PASS")
print("POST_TX_DECODER_RESET=REQUIRED")
print("AUTOMATIC_RETRY=NO")
print("PHYSICAL_P8_AUTHORIZED=NO_PENDING_R1_CHECKPOINT")
print("DAEMON_PRODUCT_TX_ENABLED=NO")
print("POSIX_SERIAL_TRANSPORT=NO")
print("RF_TRANSMITTED=NO")
