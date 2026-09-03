#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "firmware" / "qualification" / "0c-p4c-real-owner-fake-transport.json"
INTEGRATION = ROOT / "tests" / "access_queue_tx_owner_integration_test.py"
ACCESS = ROOT / "src" / "ywd1278" / "tx" / "access_queue.py"
BROKER = ROOT / "src" / "ywd1278" / "tx" / "broker.py"
TX_OWNER = ROOT / "src" / "ywd1278" / "modem" / "tx_owner.py"
KISS = ROOT / "src" / "ywd1278" / "kiss" / "server.py"
DAEMON = ROOT / "src" / "ywd1278" / "daemon.py"

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
integration = INTEGRATION.read_text(encoding="utf-8")
access = ACCESS.read_text(encoding="utf-8")
broker = BROKER.read_text(encoding="utf-8")
tx_owner = TX_OWNER.read_text(encoding="utf-8")
kiss = KISS.read_text(encoding="utf-8")
daemon = DAEMON.read_text(encoding="utf-8")

assert manifest["schema"] == 1
assert manifest["phase"] == "0C-P4c"
assert manifest["status"] == "staged-host-only"
assert manifest["base_checkpoint"] == "checkpoint/0c-p4b-real-broker-fake-modem-qualified"
assert manifest["base_checkpoint_sha"] == "3b22251582f532f5b7c388bde8d5eef50b01f22d"
assert manifest["software_graph"] == {
    "bounded_channel_access_queue": "real",
    "tx_broker": "real",
    "tx_modem_owner": "real",
    "modem_transport": "fake-thread-bound",
}
assert manifest["access"] == {
    "persist": 63,
    "slot_time_10ms": 10,
    "maximum_wait_seconds": 30.0,
    "busy_assert_raw_max": 83,
    "clear_release_raw_min": 90,
    "recent_rx_hold_seconds": 0.25,
    "downstream_called_before_ready": False,
    "ready_dispatch_exactly_once": True,
    "duplicate_dispatch": False,
}
assert manifest["broker"]["transmit_enabled_for_fake_transport_test"] is True
assert manifest["broker"]["transaction_timeout_seconds"] == 1.5
assert manifest["broker"]["rf_status_preflight_required"] is True
assert manifest["wire"]["transactions"] == 2
assert manifest["wire"]["request_1"] == "YWD_RF_GET_STATUS"
assert manifest["wire"]["request_2"] == "YWD_RF_TX_TONES"
assert manifest["wire"]["p5_frame_bytes"] == 38
assert manifest["wire"]["p5_selector_count"] == 691
assert manifest["wire"]["p5_packed_selector_bytes"] == 87
assert manifest["wire"]["p5_packed_selector_sha256"] == "30718ba5a4368e82bab69e6343f95c7e226cd08426844ed328ad8c52fbfd750e"
assert manifest["wire"]["all_transactions_on_single_owner_thread"] is True
assert manifest["wire"]["transport_close_on_owner_thread"] is True
for key in (
    "posix_serial_transport_used",
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

# P4c must exercise the real queue, real broker, and real single-owner TX class,
# but the bottom of the graph must remain a deterministic in-memory transport.
for required in (
    "TXModemOwner(factory, queue_capacity=4)",
    "TXBroker(owner, transmit_enabled=True, queue_capacity=2)",
    "BoundedChannelAccessQueue(broker)",
    "class ThreadBoundTransport",
    "transport.requests[0] == protocol.rf_status_request()",
    "protocol.RF_TX_TONES",
    "owner.snapshot.transactions == 2",
    "transport.close_thread_id == transport.owner_thread_id",
    "P4C_FULL_SOFTWARE_GRAPH_FAKE_TRANSPORT=PASS",
    "P5_SELECTOR_COUNT=691",
    "POSIX_SERIAL_TRANSPORT=NO",
    "UART_OPENED=NO",
    "RF_TRANSMITTED=NO",
):
    assert required in integration, required

# The integration harness itself must not import/use the POSIX serial transport,
# sockets, subprocesses, GPIO, or flash helpers. The transport factory is local.
tree = ast.parse(integration)
for node in ast.walk(tree):
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        assert module not in {
            "ywd1278.modem._serial",
            "ywd1278.firmware",
        }, module
    elif isinstance(node, ast.Import):
        for alias in node.names:
            assert alias.name not in {
                "serial",
                "socket",
                "subprocess",
                "gpiod",
                "RPi.GPIO",
            }, alias.name

# Existing production boundaries stay narrow. P4a remains generic, the broker
# remains network-unaware, and TXModemOwner still exposes only typed operations
# rather than a raw public transact method.
assert "from .broker import" not in access
assert "ywd1278.kiss" not in broker
assert "socket" not in broker
assert "def transact(" not in tx_owner
assert "def transmit_selector_burst(" in tx_owner
assert "def apply_tx_qualification_profile(" in tx_owner

# Ordinary KISS/product runtime remains unable to reach the TX graph in P4c.
for forbidden in (
    "BoundedChannelAccessQueue",
    "TXBroker",
    "TXModemOwner",
    "transmit_selector_burst",
):
    assert forbidden not in kiss, forbidden
    assert forbidden not in daemon, forbidden

print("P4C_REAL_OWNER_FAKE_TRANSPORT_CONTRACT=PASS")
print("BASE_CHECKPOINT=0C-P4B_QUALIFIED")
print("ACCESS_QUEUE=REAL")
print("TX_BROKER=REAL")
print("TX_MODEM_OWNER=REAL")
print("MODEM_TRANSPORT=FAKE_THREAD_BOUND")
print("MODEM_TRANSACTIONS=2")
print("SINGLE_MODEM_OWNER_THREAD=REQUIRED")
print("POSIX_SERIAL_TRANSPORT=NO")
print("UART_OPENED=NO")
print("KISS_TX_CONNECTED=NO")
print("PRODUCT_TX_ENABLED=NO")
print("HARDWARE_ACCESS=NO")
print("RF_TRANSMITTED=NO")
