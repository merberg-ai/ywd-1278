#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "firmware" / "qualification" / "0c-p3-live-shadow-channel-access.json"
TOOL = ROOT / "tools" / "qualify_live_shadow_channel_access.py"
TARGETS = ROOT / "firmware" / "targets.json"
KISS = ROOT / "src" / "ywd1278" / "kiss" / "server.py"
DAEMON = ROOT / "src" / "ywd1278" / "daemon.py"

stage = json.loads(STAGE.read_text(encoding="utf-8"))
tool = TOOL.read_text(encoding="utf-8")
target = json.loads(TARGETS.read_text(encoding="utf-8"))["targets"][0]
kiss = KISS.read_text(encoding="utf-8")
daemon = DAEMON.read_text(encoding="utf-8")

assert stage["schema"] == 1
assert stage["phase"] == "0C-P3"
assert stage["status"] == "staged"
assert stage["target_id"] == "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"
base = stage["physical_base"]
assert base["status"] == "0c-p2-channel-busy-detector-qualified"
assert base["checkpoint"] == "checkpoint/0c-p2-channel-busy-detector-qualified"
assert base["checkpoint_sha"] == "ddd881b868f851cf955703e1e7d277d1537b76d9"
assert base["firmware_artifact_size_bytes"] == 59892
assert base["firmware_sha256"] == "b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616"
assert base["firmware_left_installed"] is True

observation = stage["observation"]
assert observation["device"] == "/dev/ttyAMA0"
assert observation["receive_frequency_hz"] == 145050000
assert observation["maximum_duration_seconds"] == 20.0
assert observation["rssi_poll_interval_seconds"] == 0.05
assert observation["minimum_valid_ax25_frames"] == 1
assert observation["requires_live_busy_observation"] is True
assert observation["requires_zero_fifo_drops"] is True
assert observation["requires_zero_rf_keyup_delta"] is True
assert observation["requires_zero_rf_generated_sample_delta"] is True

assert stage["detector"] == {
    "busy_assert_raw_max": 83,
    "clear_release_raw_min": 90,
    "hysteresis_raw_min": 84,
    "hysteresis_raw_max": 89,
    "recent_rx_hold_seconds": 0.25,
    "only_clear_maps_channel_busy_false": True,
}
assert stage["csma"] == {
    "persist": 63,
    "persistence_probability": 0.25,
    "slot_time_10ms": 10,
    "slot_seconds": 0.1,
    "maximum_wait_seconds": 30.0,
    "initial_state": "wait-clear",
    "busy_cancels_clear_slot": True,
    "explicit_clear_starts_new_full_slot": True,
}
assert stage["qualification_randomness"]["hidden_rng"] is False
assert stage["qualification_randomness"]["before_first_live_busy"] == 255
assert stage["qualification_randomness"]["first_post_busy_trial"] == 255
assert stage["qualification_randomness"]["second_post_busy_trial"] == 0

safety = stage["safety"]
assert safety["normal_product_flash_enabled"] is False
assert safety["firmware_flash_permitted"] is False
assert safety["gpio_reset_permitted"] is False
assert safety["option_bytes_permitted"] is False
assert safety["base_modem_owner_only"] is True
assert safety["tx_modem_owner_permitted"] is False
assert safety["tx_broker_permitted"] is False
assert safety["kiss_tx_connected"] is False
assert safety["product_tx_enabled"] is False
assert safety["rf_transmit_permitted"] is False
assert safety["automatic_tx_retry"] is False

# The physical base is unchanged until this receive-only qualification runs.
assert target["status"] == "0c-p2-channel-busy-detector-qualified"
assert target["flash_enabled"] is False
assert target["option_bytes_permitted"] is False
assert target["channel_busy_qualification"]["csma_integration"] is False
assert target["channel_busy_qualification"]["tx_broker_integration"] is False
assert target["channel_busy_qualification"]["kiss_tx_connected"] is False
assert target["channel_busy_qualification"]["product_tx_enabled"] is False

# Exact one-purpose live observer. No CLI tuning can redirect device/frequency,
# timing, thresholds, persistence, firmware, or qualification bytes.
for required in (
    'TARGET_ID = "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"',
    'DEVICE = "/dev/ttyAMA0"',
    "FREQUENCY_HZ = 145_050_000",
    "MAXIMUM_DURATION_SECONDS = 20.0",
    "RSSI_POLL_SECONDS = 0.050",
    "RXOnlyPacketRuntime(",
    "LiveChannelAccessSampler(",
    "sampler.preflight",
    "sampler.sample",
    "owner.rf_diagnostics",
    "runtime.check_health()",
    "return 255",
    "return 0",
    "BUSY_FORCED_CSMA_WAIT_CLEAR=YES",
    "RECENT_RX_BUSY_FOR_ACCESS=YES",
    "POST_BUSY_FULL_100MS_SLOT=YES",
    "POST_BUSY_PERSIST_255_DEFER=YES",
    "POST_BUSY_PERSIST_0_READY=YES",
    "SHADOW_READY_ONLY=YES",
    "RF_TRANSMITTED=NO",
    "FLASH_WRITTEN=NO",
    "OPTION_BYTES_WRITTEN=NO",
):
    assert required in tool, required

for forbidden in (
    "import argparse",
    "--device",
    "--frequency",
    "--seconds",
    "--poll",
    "--persist",
    "--slot",
    "--threshold",
    "--power",
    "from ywd1278.modem.tx_owner import",
    "from ywd1278.tx.broker import",
    "transmit_selector_burst(",
    "rf_tx_tones_request(",
    "stm32flash",
    "pinctrl",
    "raspi-gpio",
    "0x1FFFF800",
    "0x1ffff800",
):
    assert forbidden not in tool, forbidden

# Ordinary product/KISS paths remain disconnected; this physical tool is not
# imported by either one.
for forbidden in (
    "LiveChannelAccessSampler",
    "ShadowChannelAccessAttempt",
    "TXBroker",
    "TXModemOwner",
    "transmit_selector_burst",
):
    assert forbidden not in kiss, forbidden
    assert forbidden not in daemon, forbidden

print("LIVE_SHADOW_CHANNEL_ACCESS_CONTRACT=PASS")
print("PHASE=0C-P3")
print("PHYSICAL_BASE=0C-P2")
print("RX_FREQUENCY_HZ=145050000")
print("RSSI_POLL_SECONDS=0.050")
print("MAXIMUM_DURATION_SECONDS=20.0")
print("MINIMUM_VALID_AX25_FRAMES=1")
print("DETERMINISTIC_PRE_BUSY_BYTE=255")
print("DETERMINISTIC_POST_BUSY_BYTES=255,0")
print("TX_MODEM_OWNER=ABSENT")
print("TX_BROKER_CONNECTED=NO")
print("KISS_TX_CONNECTED=NO")
print("PRODUCT_TX_ENABLED=NO")
print("RF_TRANSMITTED_BY_CI=NO")
