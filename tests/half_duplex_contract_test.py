#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "src" / "ywd1278" / "tx" / "half_duplex.py"
TEST = ROOT / "tests" / "half_duplex_tx_owner_integration_test.py"

source = MODULE.read_text(encoding="utf-8")
integration = TEST.read_text(encoding="utf-8")

# The lifecycle is typed orchestration only. It must not open hardware, create a
# concrete owner/broker, or expose an external TX ingress surface.
for forbidden in (
    "posix_serial_transport_factory",
    "/dev/ttyAMA0",
    "socket",
    "KISS",
    "kiss",
    "TXModemOwner(",
    "TXBroker(",
    "random.",
    "secrets.",
    "os.urandom",
    "time.monotonic",
    "time.sleep",
    "rf_tx_tones_request",
    "transmit_selector_burst",
):
    assert forbidden not in source, forbidden

assert "class PersistentHalfDuplexSubmitter" in source
assert "monotonic: MonotonicClock" in source
assert "sleep: Sleeper" in source
assert "self._modem.rx_stop" in source
assert "self._submitter.submit_frame" in source
assert "self._wait_for_tx_idle" in source
assert "self._modem.rx_start" in source
assert source.index("self._modem.rx_stop") < source.index("self._submitter.submit_frame")

# Exactly one downstream call site exists. Recovery must never call the
# submitter again, so post-TX/recovery failures cannot duplicate a frame.
assert source.count("self._submitter.submit_frame(") == 1
assert "downstream TX failed; RX recovered and frame is terminal without retry" in source
assert "TX was accepted but RF-idle/RX restoration failed; do not retry the frame" in source
assert "self._failed_latched = True" in source

# RF idle is stronger than selector-empty alone: both remaining selectors and
# firmware TX-active diagnostics must be clear before RX_START.
assert "status.remaining_selectors == 0 and diag.tx_active == 0" in source
assert source.index("self._wait_for_tx_idle") < source.rindex("self._restart_and_verify_rx")

# The integration gate must use the real qualified software graph but a fake
# wire endpoint only.
assert "BoundedChannelAccessQueue" in integration
assert "TXBroker" in integration
assert "TXModemOwner" in integration
assert "ThreadBoundHalfDuplexTransport" in integration
assert "posix_serial_transport_factory" not in integration
assert "/dev/ttyAMA0" not in integration
assert "transport.tx_accept_count == 3" in integration
assert "transport.rx_stop_count == 3" in integration
assert "transport.rx_start_count == 4" in integration

print("P4E_HALF_DUPLEX_ARCHITECTURE_CONTRACT=PASS")
print("DOWNSTREAM_SUBMIT_CALL_SITES=1")
print("HIDDEN_CLOCK=NO")
print("HIDDEN_RNG=NO")
print("POSIX_SERIAL_TRANSPORT=NO")
print("KISS_TX_CONNECTED=NO")
print("AUTOMATIC_FRAME_RETRY=NO")
