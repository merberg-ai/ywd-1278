"""Host-side TXDELAY policy for Bell-202/AX.25 transmission.

KISS represents TXDELAY as one unsigned byte in 10 ms units.  YWD-1278 emits
an HDLC flag preamble rather than an unstructured key-up tone, so requested
TXDELAY is rounded *up* to a whole number of 8-bit flags.  Rounding upward
ensures the effective preamble is never shorter than requested.

This module is pure policy/math.  It has no modem, UART, RF, KISS-server,
clock, randomness, or runtime configuration side effects.
"""

from __future__ import annotations

from dataclasses import dataclass

KISS_TXDELAY_MIN = 0
KISS_TXDELAY_MAX = 255
KISS_TXDELAY_DEFAULT = 30
KISS_TXDELAY_UNIT_SECONDS = 0.010
BELL202_BAUD = 1200
HDLC_FLAG_BITS = 8
HDLC_FLAG_SECONDS = HDLC_FLAG_BITS / BELL202_BAUD


@dataclass(frozen=True)
class TXDelayProfile:
    """Resolved whole-flag Bell-202 preamble for one KISS TXDELAY value."""

    units: int
    requested_seconds: float
    pre_flags: int
    effective_seconds: float
    rounding_overrun_seconds: float


def resolve_txdelay(units: int = KISS_TXDELAY_DEFAULT) -> TXDelayProfile:
    """Validate one KISS TXDELAY byte and resolve its HDLC flag preamble.

    A zero requested delay still requires one opening HDLC flag so the frame
    has a legal delimiter.  All positive delays are rounded upward to the next
    whole flag when they are not already exactly representable.
    """

    if isinstance(units, bool) or not isinstance(units, int):
        raise TypeError("TXDELAY must be an integer KISS parameter byte")
    if not (KISS_TXDELAY_MIN <= units <= KISS_TXDELAY_MAX):
        raise ValueError(
            f"TXDELAY must be {KISS_TXDELAY_MIN}..{KISS_TXDELAY_MAX} "
            "in 10 ms units"
        )

    # 10 ms at 1200 baud is exactly 12 selectors/bits.  Integer arithmetic
    # keeps the flag rounding deterministic and avoids float boundary issues.
    requested_selectors = units * 12
    pre_flags = max(1, (requested_selectors + HDLC_FLAG_BITS - 1) // HDLC_FLAG_BITS)
    effective_selectors = pre_flags * HDLC_FLAG_BITS

    requested_seconds = units * KISS_TXDELAY_UNIT_SECONDS
    effective_seconds = effective_selectors / BELL202_BAUD
    return TXDelayProfile(
        units=units,
        requested_seconds=requested_seconds,
        pre_flags=pre_flags,
        effective_seconds=effective_seconds,
        rounding_overrun_seconds=effective_seconds - requested_seconds,
    )
