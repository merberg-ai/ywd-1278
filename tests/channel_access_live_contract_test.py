#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.tx.channel_busy import (  # noqa: E402
    BUSY_ASSERT_RAW_MAX,
    CLEAR_RELEASE_RAW_MIN,
    PHYSICAL_RSSI_POLL_SECONDS,
    RECENT_RX_HOLD_SECONDS,
)
from ywd1278.tx.csma import (  # noqa: E402
    DEFAULT_MAX_WAIT_SECONDS,
    DEFAULT_PERSIST,
    DEFAULT_SLOT_TIME_10MS,
)

BRIDGE = ROOT / "src" / "ywd1278" / "tx" / "channel_access.py"
LIVE = ROOT / "src" / "ywd1278" / "service" / "live_channel_access.py"
RX_RUNTIME = ROOT / "src" / "ywd1278" / "service" / "rx_runtime.py"
KISS = ROOT / "src" / "ywd1278" / "kiss" / "server.py"
DAEMON = ROOT / "src" / "ywd1278" / "daemon.py"
TARGETS = ROOT / "firmware" / "targets.json"

bridge = BRIDGE.read_text(encoding="utf-8")
live = LIVE.read_text(encoding="utf-8")
rx_runtime = RX_RUNTIME.read_text(encoding="utf-8")
kiss = KISS.read_text(encoding="utf-8")
daemon = DAEMON.read_text(encoding="utf-8")
target = json.loads(TARGETS.read_text(encoding="utf-8"))["targets"][0]

# P2 physical/policy anchors and P1 parameters are inherited unchanged.
assert BUSY_ASSERT_RAW_MAX == 83
assert CLEAR_RELEASE_RAW_MIN == 90
assert RECENT_RX_HOLD_SECONDS == 0.250
assert PHYSICAL_RSSI_POLL_SECONDS == 0.050
assert DEFAULT_PERSIST == 63
assert DEFAULT_SLOT_TIME_10MS == 10
assert DEFAULT_MAX_WAIT_SECONDS == 30.0

# Current physical boundary is the frozen 0C-P2 checkpoint. AX25R4 remains the
# accepted live firmware and unrestricted product TX remains closed.
assert target["status"] == "0c-p2-channel-busy-detector-qualified"
assert target["flash_enabled"] is False
assert target["option_bytes_permitted"] is False
assert (
    "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz "
    "ADF7021 FW based on CA6JAU GitID #7ff74ed"
) in target["accepted_running_identities"]
channel = target["channel_busy_qualification"]
assert channel["busy_assert_raw_max"] == 83
assert channel["clear_release_raw_min"] == 90
assert channel["recent_rx_hold_seconds"] == 0.25
assert channel["modem_integration"] is False
assert channel["csma_integration"] is False
assert channel["tx_broker_integration"] is False
assert channel["kiss_tx_connected"] is False
assert channel["product_tx_enabled"] is False

# Pure bridge: explicit time + caller randomness, no I/O and no TX capability.
for required in (
    "RSSIChannelBusyDetector",
    "PersistentCSMA",
    "random_byte_source",
    "ChannelAccessRandomnessRequired",
    "not detector.channel_busy",
    "prior.state is CSMAState.WAIT_SLOT",
    "now >= prior.next_slot_at",
    "channel_busy=detector.channel_busy",
):
    assert required in bridge, required
for forbidden in (
    "ywd1278.modem",
    "ywd1278.kiss",
    "TXBroker",
    "TXModemOwner",
    "transmit_selector_burst",
    "serial",
    "socket",
    "subprocess",
    "threading",
    "time.monotonic",
    "time.sleep",
    "random.",
    "secrets.",
    "stm32flash",
    "pinctrl",
):
    assert forbidden not in bridge, forbidden

# Live sidecar uses only the already-running base ModemOwner's typed RX calls.
for required in (
    "ModemOwner",
    "owner.rx_status",
    "owner.rx_rssi",
    "ShadowChannelAccessAttempt",
    "random_byte_source",
):
    assert required in live, required
for forbidden in (
    "TXBroker",
    "TXModemOwner",
    "transmit_selector_burst",
    "rf_tx_tones",
    "set_rx_frequency",
    "arm_rx_modem_io",
    "owner.rx_start",
    "owner.rx_stop",
    "owner.stop",
    "threading",
    "time.monotonic",
    "time.sleep",
    "random.",
    "secrets.",
    "socket",
    "subprocess",
    "stm32flash",
    "pinctrl",
):
    assert forbidden not in live, forbidden

# Existing RX product runtime remains RX-only and ordinary KISS/daemon TX stays
# disconnected. 0C-P3 is a sidecar, not a rewrite of the P12 runtime.
assert "RXOnlyPacketRuntime" in rx_runtime
assert "TXModemOwner" not in rx_runtime
assert "TXBroker" not in rx_runtime
for forbidden in (
    "ShadowChannelAccessAttempt",
    "LiveChannelAccessSampler",
    "TXBroker",
    "TXModemOwner",
    "transmit_selector_burst",
    "RF_TX_TONES",
):
    assert forbidden not in kiss, forbidden
    assert forbidden not in daemon, forbidden

print("CHANNEL_ACCESS_LIVE_CONTRACT=PASS")
print("PHASE=0C-P3")
print("P2_BUSY_ASSERT_RAW_MAX=83")
print("P2_CLEAR_RELEASE_RAW_MIN=90")
print("P2_RECENT_RX_HOLD_SECONDS=0.250")
print("P1_PERSIST=63")
print("P1_SLOTTIME_10MS=10")
print("LIVE_RSSI_TYPED_OWNER_ONLY=YES")
print("RX_RUNTIME_REWRITTEN=NO")
print("KISS_TX_CONNECTED=NO")
print("PRODUCT_TX_ENABLED=NO")
print("RF_TRANSMITTED_BY_CI=NO")
