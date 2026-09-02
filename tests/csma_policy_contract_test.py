#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.tx.csma import (  # noqa: E402
    DEFAULT_MAX_WAIT_SECONDS,
    DEFAULT_PERSIST,
    DEFAULT_SLOT_TIME_10MS,
    CSMAParameters,
    PersistentCSMA,
)

CSMA = ROOT / "src" / "ywd1278" / "tx" / "csma.py"
BROKER = ROOT / "src" / "ywd1278" / "tx" / "broker.py"
KISS = ROOT / "src" / "ywd1278" / "kiss" / "server.py"
DAEMON = ROOT / "src" / "ywd1278" / "daemon.py"
TARGETS = ROOT / "firmware" / "targets.json"

csma_text = CSMA.read_text(encoding="utf-8")
broker_text = BROKER.read_text(encoding="utf-8")
kiss_text = KISS.read_text(encoding="utf-8")
daemon_text = DAEMON.read_text(encoding="utf-8")
targets_text = TARGETS.read_text(encoding="utf-8")

# Frozen first policy profile. Parameter transport/configuration is a later gate.
assert DEFAULT_PERSIST == 63
assert DEFAULT_SLOT_TIME_10MS == 10
assert DEFAULT_MAX_WAIT_SECONDS == 30.0
params = CSMAParameters()
assert params.persistence_probability == 0.25
assert params.slot_seconds == 0.1

# The policy is explicitly driven by caller-supplied observations/time/randomness.
policy = PersistentCSMA(started_at=0.0)
assert policy.decision.next_slot_at == 0.1
assert "def observe(" in csma_text
assert "now: float" in csma_text
assert "channel_busy: bool" in csma_text
assert "random_byte: int | None = None" in csma_text
assert "random_byte <= self._parameters.persist" in csma_text
assert "self._next_slot_at = now + self._parameters.slot_seconds" in csma_text
assert "now >= self._deadline_at" in csma_text

# 0C-P1 has no hidden clock, sleeps, RNG, hardware, or network dependency.
for forbidden in (
    "time.monotonic",
    "time.sleep",
    "random.",
    "secrets.",
    "/dev/tty",
    "serial",
    "socket",
    "stm32flash",
    "pinctrl",
    "TXModemOwner",
    "ModemOwner",
    "TXBroker",
    "transmit_selector_burst",
    "rf_tx_tones",
    "YWD_RF",
    "YWD_RX",
):
    assert forbidden not in csma_text, forbidden

# Existing physically qualified broker remains unchanged in role: modem-pending
# overlap protection only, not carrier sensing or CSMA.
assert "This is *not* CSMA/channel-busy" in broker_text
assert "remaining_selectors != 0" in broker_text
assert "PersistentCSMA" not in broker_text
assert "CSMAParameters" not in broker_text

# Most important boundary: policy existence does not connect product/KISS TX.
for forbidden in (
    "PersistentCSMA",
    "CSMAParameters",
    "TXBroker",
    "TXModemOwner",
    "transmit_selector_burst",
    "RF_TX_TONES",
):
    assert forbidden not in kiss_text, forbidden
    assert forbidden not in daemon_text, forbidden

# Current target remains the P13b physical boundary; 0C-P1 is host-only and must
# not alter RF/firmware qualification evidence.
assert '"status": "0b-p13b-known-packet-tx-qualified"' in targets_text
assert '"packet_known_tx_qualification"' in targets_text
assert '"external_decodes": 3' in targets_text

print("CSMA_POLICY_CONTRACT=PASS")
print("PHASE=0C-P1")
print("DEFAULT_PERSIST=63")
print("DEFAULT_PERSIST_PROBABILITY=0.25")
print("DEFAULT_SLOTTIME_10MS=10")
print("DEFAULT_SLOT_SECONDS=0.1")
print("DEFAULT_MAX_WAIT_SECONDS=30.0")
print("CALLER_SUPPLIED_TIME=YES")
print("CALLER_SUPPLIED_RANDOMNESS=YES")
print("LIVE_CHANNEL_SENSOR_CONNECTED=NO")
print("KISS_TX_CONNECTED=NO")
print("PRODUCT_TX_ENABLED=NO")
print("MODEM_ACCESS=NO")
print("RF_TRANSMITTED=NO")
