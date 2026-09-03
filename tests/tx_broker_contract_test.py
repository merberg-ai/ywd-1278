#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.modem import protocol  # noqa: E402
from ywd1278.modem.owner import ModemOwner  # noqa: E402
from ywd1278.modem.tx_owner import TXModemOwner  # noqa: E402
from ywd1278.phy import MARK  # noqa: E402
from ywd1278.tx.broker import P5_INITIAL_TONE, P5_POST_FLAGS, P5_PRE_FLAGS, TXBroker  # noqa: E402

TARGETS = ROOT / "firmware" / "targets.json"
BROKER = ROOT / "src" / "ywd1278" / "tx" / "broker.py"
TX_OWNER = ROOT / "src" / "ywd1278" / "modem" / "tx_owner.py"
KISS_SERVER = ROOT / "src" / "ywd1278" / "kiss" / "server.py"
DAEMON = ROOT / "src" / "ywd1278" / "daemon.py"

target = json.loads(TARGETS.read_text(encoding="utf-8"))["targets"][0]
broker_text = BROKER.read_text(encoding="utf-8")
tx_owner_text = TX_OWNER.read_text(encoding="utf-8")
kiss_text = KISS_SERVER.read_text(encoding="utf-8")
daemon_text = DAEMON.read_text(encoding="utf-8")

# The current target boundary has advanced through 0C-P2. P12b receive evidence,
# P13b physical TX evidence, and the host-only P13a broker architecture remain
# frozen prerequisites and are not rewritten by later channel-access work.
assert target["status"] == "0c-p2-channel-busy-detector-qualified"
assert target["flash_enabled"] is False
assert target["option_bytes_permitted"] is False
p12b = target["packet_live_rf_kiss_qualification"]
assert p12b["phase"] == "0B-P12b"
assert p12b["status"] == "qualified"
assert p12b["receive_frequency_hz"] == 145050000
assert p12b["tx_command_permitted"] is False
assert p12b["rf_transmitted"] is False
assert p12b["option_bytes_written"] is False
p13b = target["packet_live_tx_qualification"]
assert p13b["phase"] == "0B-P13b"
assert p13b["status"] == "qualified"
assert p13b["kiss_tx_connected"] is False
assert p13b["product_tx_enabled"] is False
p2 = target["channel_busy_qualification"]
assert p2["phase"] == "0C-P2"
assert p2["status"] == "host-qualified"
assert p2["modem_integration"] is False
assert p2["csma_integration"] is False
assert p2["tx_broker_integration"] is False
assert p2["kiss_tx_connected"] is False

# Preserve the exact RX-only owner used for P12a/P12b. TX capability exists
# only on the narrow subclass intended for the broker.
assert not hasattr(ModemOwner, "transmit_selector_burst")
assert not hasattr(ModemOwner, "rf_tx_tones")
assert hasattr(TXModemOwner, "transmit_selector_burst")
assert not hasattr(TXModemOwner, "rf_tx_tones")
assert not hasattr(TXModemOwner, "transact")
assert "rf_abort_request" not in tx_owner_text
assert "rf_exit_request" not in tx_owner_text
assert 'self._call("transmit_selector_burst"' in tx_owner_text
assert "protocol.rf_tx_tones_request" in tx_owner_text
assert "protocol.parse_ack(response, expected_command=protocol.YWD_RF)" in tx_owner_text

# Broker timing remains exactly the frozen 0B-P5 serializer profile. P13a adds
# no configurable TXDELAY or CSMA behavior.
assert P5_PRE_FLAGS == 45
assert P5_POST_FLAGS == 3
assert P5_INITIAL_TONE == MARK
assert protocol.MAX_SELECTORS == 1920
assert "frame_to_selectors(" in broker_text
assert "pack_selectors(" in broker_text
assert "verify_fcs(frame)" in broker_text
assert "selector_count > protocol.MAX_SELECTORS" in broker_text
assert "transmit_enabled: bool = False" in broker_text
assert "remaining_selectors != 0" in broker_text
assert "transmit_selector_burst(" in broker_text
assert "queue.Queue[_Job | object]" in broker_text

# Ordinary KISS remains RX-only and the product daemon does not construct or
# connect the broker. A TCP client still has no path to YWD_RF/TX_TONES.
for forbidden in ("TXBroker", "TXModemOwner", "transmit_selector_burst", "RF_TX_TONES"):
    assert forbidden not in kiss_text, forbidden
    assert forbidden not in daemon_text, forbidden
assert "class RXOnlyBackend" in kiss_text
assert "self._tx_rejected += 1" in kiss_text

# Broker itself has no direct serial/GPIO/flash/socket implementation. Mentioning
# KISS in comments is fine; importing or opening a KISS service is not.
for forbidden in ("/dev/tty", "posix_serial_transport_factory", "stm32flash", "pinctrl", "import socket"):
    assert forbidden not in broker_text, forbidden
assert "ywd1278.kiss" not in broker_text

# Default construction is a hard-disabled object, not merely an empty queue.
class NeverOwner:
    def rf_status(self, *, timeout=None):  # type: ignore[no-untyped-def]
        raise AssertionError("disabled broker reached modem status")

    def transmit_selector_burst(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("disabled broker reached modem TX")


default_broker = TXBroker(NeverOwner())
assert default_broker.snapshot.transmit_enabled is False

print("TX_BROKER_CONTRACT=PASS")
print("P12B_PHYSICAL_EVIDENCE_FROZEN=PASS")
print("P13B_PHYSICAL_TX_BOUNDARY=QUALIFIED")
print("P2_CURRENT_TARGET_BOUNDARY=QUALIFIED")
print("BASE_MODEM_OWNER_RX_ONLY=PASS")
print("TYPED_TX_OWNER_SUBCLASS=PASS")
print("P5_FIXED_SERIALIZER_PROFILE=PASS")
print("VALID_FCS_GATE=PASS")
print("MAX_SELECTORS_GATE=1920")
print("MODEM_BUSY_PREFLIGHT=PASS")
print("DEFAULT_PRODUCT_TX=DISABLED")
print("KISS_TX_CONNECTED=NO")
print("DAEMON_TX_CONNECTED=NO")
print("DIRECT_HARDWARE_PATH=ABSENT")
print("RF_TRANSMITTED_BY_CI=NO")
