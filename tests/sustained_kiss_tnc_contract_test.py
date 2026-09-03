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


# P8 is additive around the physically-qualified P7 graph.  These blobs must
# remain byte-for-byte unchanged.
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

# Product daemon/systemd stay fail-closed; P8 host qualification does not turn
# on persistent hardware TX.
assert git_blob("src/ywd1278/daemon.py") == "0571c4a88a5d498b48cf6a6cc19b511655f8fb07"
assert git_blob("systemd/ywd-1278.service") == "ab7dc6aa6af8237d20e41a1357083f0321fd7062"

sustained = text("src/ywd1278/kiss/sustained.py")
runtime = text("src/ywd1278/service/tnc_runtime.py")

# Concurrency is added by composition, never by editing the frozen P7 deque.
assert "class ThreadSafeKISSDataAdmissionQueue" in sustained
assert "self._queue = KISSDataAdmissionQueue(" in sustained
assert "threading.RLock()" in sustained
assert "with self._lock:" in sustained
assert "class SustainedTNCBackend" in sustained
assert "total_connections" in sustained
assert "total_disconnects" in sustained

# Sustained scheduler keeps explicit timing/randomness dependencies and only
# advances RSSI access while a bounded request exists.
assert "monotonic: MonotonicClock" in runtime
assert "random_byte_source: RandomByteSource" in runtime
assert "if self._admission.snapshot.queue_depth:" in runtime
assert "self._owner.rx_rssi()" in runtime
assert "random_byte_source=self._random_byte_source" in runtime

# The physically-qualified P4e discontinuity requires a new Bell-202 decoder
# after every completed TX/RX restart cycle.
assert "self._decoder = StreamingBell202Decoder()" in runtime
assert "decoder_resets_after_tx" in runtime
assert "KISSDataRequestState.DISPATCHED" in runtime
assert "KISSDataRequestState.DOWNSTREAM_FAILED" in runtime
assert "service is fail-latched" in runtime

# Operator-facing accounting must aggregate every bounded service boundary.
for token in (
    "parameters=self._backend.control_snapshot",
    "control=self._backend.control_counters",
    "ingress=self._backend.ingress_counters",
    "TNCQueueAccounting.from_access_snapshot",
    "connections=self._backend.connection_counters",
    "subscriber_drops=base.subscriber_drops",
):
    assert token in runtime

# P8 runtime cannot configure hardware or bypass the qualified graph.
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

manifest = json.loads(text("firmware/qualification/0c-p8-sustained-kiss-tnc-host.json"))
assert manifest["phase"] == "0C-P8-host"
assert manifest["status"] == "host-qualified"
assert manifest["base_checkpoint_sha"] == "80249ab34da4c64d40d23d98d639db78d1691f5d"
assert manifest["architecture"]["preserve_p7_queue_source"] is True
assert manifest["architecture"]["thread_safe_queue_by_composition"] is True
assert manifest["qualification"]["sustained_tx_cycles"] == 4
assert manifest["qualification"]["captured_txdelay_profiles"] == [20, 30, 40, 50]
assert manifest["qualification"]["automatic_retry"] is False
assert manifest["qualification_evidence"]["full_framework_pr_run"] == 439
assert manifest["qualification_evidence"]["all_green_before_promotion"] is True
assert manifest["safety"]["host_fake_modem_only"] is True
assert manifest["safety"]["posix_serial"] is False
assert manifest["safety"]["uart_access"] is False
assert manifest["safety"]["rf_transmitted"] is False
assert manifest["safety"]["daemon_product_tx_enabled"] is False
assert manifest["physical_follow_on"]["authorized"] is False
assert manifest["physical_follow_on"]["frequency_hz"] == 145050000
assert manifest["physical_follow_on"]["rf_power"] == 200
assert manifest["physical_follow_on"]["require_path"] == ["YWDNOD"]
assert manifest["physical_follow_on"]["require_ywdnod_repeated_decode"] is False

print("P8_SUSTAINED_KISS_TNC_ARCHITECTURE_CONTRACT=PASS")
print("P7_ADMISSION_FROZEN=PASS")
print("P6_CONTROL_FROZEN=PASS")
print("P4E_HALF_DUPLEX_FROZEN=PASS")
print("P5_TXDELAY_FROZEN=PASS")
print("TX_BROKER_FROZEN=PASS")
print("THREAD_SAFE_QUEUE=COMPOSITION")
print("CALLER_SUPPLIED_TIME_AND_RANDOMNESS=PASS")
print("POST_TX_DECODER_RESET=REQUIRED")
print("AUTOMATIC_RETRY=NO")
print("PHYSICAL_P8_AUTHORIZED=NO")
print("DAEMON_PRODUCT_TX_ENABLED=NO")
print("POSIX_SERIAL_TRANSPORT=NO")
print("RF_TRANSMITTED=NO")
