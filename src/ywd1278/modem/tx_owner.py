"""Narrow TX-capable extension of the frozen single-owner modem runtime.

The base :class:`ModemOwner` remains the RX-only owner physically qualified by
0B-P12a/P12b.  This subclass adds exactly one typed transmit primitive for the
bounded TX broker: one already-serialized Bell-202 selector burst.

There is still no raw transact API, RF abort API, RF exit API, KISS dependency,
or channel-access policy here.  All device I/O still occurs on the inherited
single owner thread.
"""

from __future__ import annotations

from typing import cast

from . import protocol
from .owner import ModemOwner, ModemTransport, _Call


class TXModemOwner(ModemOwner):
    """Single-UART owner with one broker-facing selector-burst TX operation."""

    def transmit_selector_burst(
        self,
        selector_count: int,
        packed_selectors: bytes,
        *,
        timeout: float | None = None,
    ) -> None:
        """Submit one qualified ``YWD_RF/TX_TONES`` request through the owner.

        The public shape is typed: callers supply only the selector count and
        packed selector bytes.  They cannot supply an arbitrary modem frame.
        The bounded TX broker is the intended product caller for this method.
        """

        request = protocol.rf_tx_tones_request(
            selector_count=int(selector_count),
            packed_selectors=bytes(packed_selectors),
        )
        # _call is the inherited single-owner queue boundary.  The base class
        # annotates its argument narrowly because all historical operations
        # used int/None; bytes are safe here because this subclass owns the
        # matching dispatch branch below.
        self._call("transmit_selector_burst", request, timeout)  # type: ignore[arg-type]

    def _dispatch(self, transport: ModemTransport, call: _Call) -> object | None:
        if call.operation == "transmit_selector_burst":
            request = cast(bytes, call.argument)
            response = self._transact(transport, request, call.timeout)
            protocol.parse_ack(response, expected_command=protocol.YWD_RF)
            return None
        return super()._dispatch(transport, call)
