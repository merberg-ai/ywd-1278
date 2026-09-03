#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "firmware" / "qualification" / "0c-p4b-real-broker-fake-modem.json"
INTEGRATION = ROOT / "tests" / "access_queue_broker_integration_test.py"
ACCESS = ROOT / "src" / "ywd1278" / "tx" / "access_queue.py"
BROKER = ROOT / "src" / "ywd1278" / "tx" / "broker.py"
KISS = ROOT / "src" / "ywd1278" / "kiss" / "server.py"
DAEMON = ROOT / "src" / "ywd1278" / "daemon.py"

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
integration = INTEGRATION.read_text(encoding="utf-8")
access = ACCESS.read_text(encoding="utf-8")
broker = BROKER.read_text(encoding="utf-8")
kiss = KISS.read_text(encoding="utf-8")
daemon = DAEMON.read_text(encoding="utf-8")

assert manifest["schema"] == 1
assert manifest["phase"] == "0C-P4b"
assert manifest["status"] == "host-qualified"
assert manifest["base_checkpoint"] == "checkpoint/0c-p4a-bounded-access-queue-qualified"
assert manifest["base_checkpoint_sha"] == "384f408af286aca34e16b0480267b890cdcbdba9"
assert manifest["broker"]["class"] == "TXBroker"
assert manifest["broker"]["concrete_broker_used"] is True
assert manifest["broker"]["p5_selector_count"] == 691
assert manifest["broker"]["p5_packed_selector_bytes"] == 87
assert manifest["broker"]["p5_packed_selector_sha256"] == "30718ba5a4368e82bab69e6343f95c7e226cd08426844ed328ad8c52fbfd750e"
assert manifest["qualification_ci"] == {
    "workflow": "framework-ci",
    "run_number": 352,
    "run_id": 33706006503,
    "head_sha": "6476faa3fc297f03883bdaf9bb72280a0cd420b3",
    "conclusion": "success",
}
assert manifest["fake_modem_port_only"] is True
for key in (
    "tx_modem_owner_used",
    "modem_transport_used",
    "uart_opened",
    "kiss_tx_connected",
    "daemon_tx_connected",
    "product_tx_enabled",
    "hardware_access",
    "rf_transmitted",
    "flash_written",
    "gpio_accessed",
    "option_bytes_written",
):
    assert manifest[key] is False, key

# P4b composes the two existing qualified layers directly. It adds no production
# adapter capable of bypassing P4a or P13a boundaries.
assert "BoundedChannelAccessQueue(broker)" in integration
assert "TXBroker(owner, transmit_enabled=True" in integration
assert "class FakeTXModemPort" in integration
assert "P5_SELECTOR_COUNT=691" in integration
assert "BROKER_BUSY_FAIL_CLOSED=PASS" in integration
assert "BROKER_DISABLED_FAIL_CLOSED=PASS" in integration
assert "BROKER_SELECTOR_LIMIT_AUTHORITATIVE=PASS" in integration
assert "REAL_TX_MODEM_OWNER_USED=NO" in integration

# The integration qualification itself must not import the real TXModemOwner or
# any serial transport. Using the concrete broker class is the only new concrete
# TX layer in this phase.
integration_tree = ast.parse(integration)
for node in ast.walk(integration_tree):
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        assert module != "ywd1278.modem.tx_owner", module
        assert module != "ywd1278.modem._serial", module
    elif isinstance(node, ast.Import):
        for alias in node.names:
            assert alias.name not in {"serial", "socket", "subprocess"}, alias.name

# P4a remains generic and does not gain a concrete broker import as a side
# effect of P4b. P13a broker remains unaware of KISS/network and retains its
# existing qualified isolation.
access_tree = ast.parse(access)
for node in ast.walk(access_tree):
    if isinstance(node, ast.ImportFrom):
        assert not (node.level == 1 and (node.module or "") == "broker")
assert "ywd1278.kiss" not in broker
assert "socket" not in broker
assert "subprocess" not in broker

# Ordinary product inputs still cannot reach either P4a or the broker.
for forbidden in (
    "BoundedChannelAccessQueue",
    "TXBroker",
    "TXModemOwner",
    "transmit_selector_burst",
):
    assert forbidden not in kiss, forbidden
    assert forbidden not in daemon, forbidden

print("P4B_REAL_BROKER_FAKE_MODEM_CONTRACT=PASS")
print("STATUS=HOST_QUALIFIED")
print("BASE_CHECKPOINT=0C-P4A_QUALIFIED")
print("QUALIFICATION_CI=352_SUCCESS")
print("REAL_TX_BROKER_CLASS_USED=YES")
print("P4A_GENERIC_BOUNDARY_PRESERVED=YES")
print("TX_MODEM_OWNER_USED=NO")
print("MODEM_TRANSPORT_USED=NO")
print("KISS_TX_CONNECTED=NO")
print("PRODUCT_TX_ENABLED=NO")
print("HARDWARE_ACCESS=NO")
print("RF_TRANSMITTED=NO")
