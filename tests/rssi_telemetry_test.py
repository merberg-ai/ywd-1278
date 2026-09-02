#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.modem import protocol  # noqa: E402
from ywd1278.modem.owner import ModemOwner  # noqa: E402


# Exact additive 0C-P2 wire primitive.
assert protocol.RX_RSSI == 0x05
assert protocol.rx_rssi_request() == bytes.fromhex("e0 04 59 05")
reading = protocol.parse_rx_rssi(bytes.fromhex("e0 06 59 05 6d 00"))
assert reading.raw_magnitude == 109

for malformed in (
    bytes.fromhex("e0 05 59 05 6d"),
    bytes.fromhex("e0 06 59 04 6d 00"),
    bytes.fromhex("e0 07 59 05 6d 00 00"),
):
    try:
        protocol.parse_rx_rssi(malformed)
    except ValueError:
        pass
    else:
        raise AssertionError(f"malformed RSSI response accepted: {malformed.hex()}")


class RSSIFakeTransport:
    def __init__(self) -> None:
        self.owner_thread = threading.get_ident()
        self.requests: list[bytes] = []
        self.closed_thread: int | None = None

    def transact(self, request: bytes, *, timeout: float) -> bytes:
        assert threading.get_ident() == self.owner_thread
        self.requests.append(request)
        assert request == protocol.rx_rssi_request()
        return bytes.fromhex("e0 06 59 05 6d 00")

    def close(self) -> None:
        assert threading.get_ident() == self.owner_thread
        self.closed_thread = threading.get_ident()


created: list[RSSIFakeTransport] = []


def factory() -> RSSIFakeTransport:
    transport = RSSIFakeTransport()
    created.append(transport)
    return transport


owner = ModemOwner(factory)
owner.start()
try:
    value = owner.rx_rssi()
    assert value.raw_magnitude == 109
    assert len(created) == 1
    assert created[0].requests == [bytes.fromhex("e0 04 59 05")]
    assert owner.snapshot.transactions == 1
    assert owner.snapshot.owner_thread_id == created[0].owner_thread
    assert owner.snapshot.owner_thread_id != threading.get_ident()
    assert not hasattr(owner, "transmit_selector_burst")
    assert not hasattr(owner, "rf_tx_tones")
    assert not hasattr(owner, "transact")
finally:
    owner.stop()

assert created[0].closed_thread == created[0].owner_thread

print("RSSI_TELEMETRY_HOST_REGRESSION=PASS")
print("YWD_RX_RSSI_SUBCOMMAND=0x05")
print("RSSI_REQUEST_HEX=e0045905")
print("RSSI_RESPONSE_LAYOUT=UINT16_LE_RAW_MAGNITUDE")
print("RSSI_THRESHOLD_SELECTED=NO")
print("SINGLE_MODEM_OWNER=PASS")
print("TX_API_ADDED_TO_BASE_OWNER=NO")
print("RF_TRANSMITTED=NO")
