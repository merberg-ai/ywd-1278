#!/usr/bin/env python3
from __future__ import annotations

import struct
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.modem import protocol, tx_config  # noqa: E402
from ywd1278.modem.owner import ModemOwner  # noqa: E402
from ywd1278.modem.tx_owner import TXModemOwner  # noqa: E402

assert tx_config.P13B_TX_FREQUENCY_HZ == 145050000
assert tx_config.P13B_TX_POWER == 200
request = tx_config.p13b_tx_frequency_request()
frame = protocol.parse_frame(request, expected_command=protocol.SET_FREQ)
expected_payload = (
    b"\x00"
    + struct.pack("<I", 145050000)
    + struct.pack("<I", 145050000)
    + bytes((200,))
)
assert frame.payload == expected_payload

# Qualification-only setup lives only on the TX subclass.  The physically
# qualified RX-only owner remains unchanged.
assert not hasattr(ModemOwner, "apply_tx_qualification_profile")
assert hasattr(TXModemOwner, "apply_tx_qualification_profile")

main_tid = threading.get_ident()
constructed_tid = None
transact_tid = None
seen = []


class FakeTransport:
    def __init__(self) -> None:
        global constructed_tid
        constructed_tid = threading.get_ident()

    def transact(self, request_bytes: bytes, *, timeout: float) -> bytes:
        global transact_tid
        assert timeout > 0
        transact_tid = threading.get_ident()
        seen.append(bytes(request_bytes))
        parsed = protocol.parse_frame(request_bytes)
        assert parsed.command == protocol.SET_FREQ
        return protocol.ack_for(protocol.SET_FREQ)

    def close(self) -> None:
        assert threading.get_ident() == constructed_tid


owner = TXModemOwner(lambda: FakeTransport())
owner.start()
owner.apply_tx_qualification_profile(timeout=1.0)
owner.stop()

assert seen == [request]
assert constructed_tid is not None and constructed_tid != main_tid
assert transact_tid == constructed_tid

print("P13B_TX_QUALIFICATION_PROFILE=PASS")
print("P13B_TX_FREQUENCY_HZ=145050000")
print("P13B_TX_POWER=200")
print("BASE_MODEM_OWNER_UNCHANGED=PASS")
print("SINGLE_OWNER_PROFILE_WRITE=PASS")
print("HARDWARE_UART_OPENED=NO")
print("RF_TRANSMITTED=NO")
