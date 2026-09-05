"""0F product composition for classic UNPROTO/converse UI transmission.

The frozen Stage-D console lifecycle remains untouched.  This module subclasses
that lifecycle only to swap in the 0F session shell when station identity is
present.  Console-generated AX.25 frame bodies are admitted through the same
``ProductTNCBackend.reject_client_message(KISS DATA)`` boundary used by normal
KISS clients and physically qualified in Stage I.

There is no second queue, CSMA implementation, modem owner, UART path, retry
loop, firmware path, beacon scheduler, or connected-mode engine here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any, Callable

from ywd1278.ax25 import Address
from ywd1278.console.classic_tx import (
    ClassicTXSubmitResult,
    ClassicTXSubmitter,
    DEFAULT_PACLEN,
    MAX_PACLEN,
    make_classic_tx_shell,
)
from ywd1278.kiss.framing import DATA, KISSMessage
from ywd1278.kiss.tx_backend import KISSDataIngressResult
from ywd1278.monitor.policy import MonitorPolicyState
from ywd1278.service.classic_console import (
    ProductClassicConsole,
    ProductClassicConsoleConfig,
)


class ProductClassicTXConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ProductClassicTXConfig:
    source: Address | None
    paclen: int = DEFAULT_PACLEN

    @property
    def configured(self) -> bool:
        return self.source is not None


def load_product_classic_tx_config(path: str | Path) -> ProductClassicTXConfig:
    """Load 0F station/PACLEN state without changing Stage-B config semantics.

    Historical product host fixtures predate ``[station]``.  An absent station
    table therefore leaves the frozen P5 console personality in place.  Real
    appliance configs contain station identity and activate the 0F shell.
    """

    config_path = Path(path)
    try:
        with config_path.open("rb") as handle:
            root = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ProductClassicTXConfigurationError(
            f"cannot load 0F configuration {config_path}: {exc}"
        ) from exc

    station = root.get("station")
    if station is None:
        return ProductClassicTXConfig(source=None, paclen=DEFAULT_PACLEN)
    if not isinstance(station, dict):
        raise ProductClassicTXConfigurationError("invalid [station] table")

    callsign = station.get("callsign")
    ssid = station.get("ssid", 0)
    if not isinstance(callsign, str) or not callsign.strip():
        raise ProductClassicTXConfigurationError("station.callsign must be a non-empty string")
    if isinstance(ssid, bool) or not isinstance(ssid, int) or not 0 <= ssid <= 15:
        raise ProductClassicTXConfigurationError("station.ssid must be an integer 0..15")
    source_text = callsign.strip() if ssid == 0 else f"{callsign.strip()}-{ssid}"
    try:
        source = Address.parse(source_text)
    except ValueError as exc:
        raise ProductClassicTXConfigurationError(f"invalid station identity: {exc}") from exc

    paclen = DEFAULT_PACLEN
    packet = root.get("packet")
    if packet is not None:
        if not isinstance(packet, dict):
            raise ProductClassicTXConfigurationError("invalid [packet] table")
        value = packet.get("paclen", DEFAULT_PACLEN)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ProductClassicTXConfigurationError("packet.paclen must be an integer")
        paclen = int(value)
    if not 1 <= paclen <= MAX_PACLEN:
        raise ProductClassicTXConfigurationError(f"packet.paclen must be 1..{MAX_PACLEN}")

    return ProductClassicTXConfig(source=source, paclen=paclen)


def make_product_backend_submitter(
    backend_getter: Callable[[], Any],
) -> ClassicTXSubmitter:
    """Adapt one live product backend to the 0F shell's narrow submit contract."""

    if not callable(backend_getter):
        raise TypeError("backend_getter must be callable")

    def submit(frame_no_fcs: bytes) -> ClassicTXSubmitResult:
        backend = backend_getter()
        if backend is None:
            return ClassicTXSubmitResult(False, None, "product TX backend unavailable")
        handler = getattr(backend, "reject_client_message", None)
        if not callable(handler):
            return ClassicTXSubmitResult(False, None, "product TX backend has no DATA admission method")
        result = handler(KISSMessage(port=0, command=DATA, frame=bytes(frame_no_fcs)))
        if not isinstance(result, KISSDataIngressResult):
            reason = str(getattr(result, "reason", "product DATA admission rejected"))
            return ClassicTXSubmitResult(False, None, reason)
        request_id = None if result.receipt is None else int(result.receipt.request_id)
        return ClassicTXSubmitResult(bool(result.admitted), request_id, str(result.reason))

    return submit


class ProductClassicTXConsole(ProductClassicConsole):
    """Stage-D lifecycle with per-session 0F UI transmit personality."""

    def __init__(
        self,
        config: ProductClassicConsoleConfig,
        *,
        tx_config: ProductClassicTXConfig,
        tx_enabled: bool,
        tx_submitter: ClassicTXSubmitter,
        diagnostics_snapshot,  # type: ignore[no-untyped-def]
        mheard_db,
    ) -> None:  # type: ignore[no-untyped-def]
        if not isinstance(tx_config, ProductClassicTXConfig):
            raise TypeError("tx_config must be ProductClassicTXConfig")
        if tx_enabled and tx_config.source is None:
            raise ProductClassicTXConfigurationError(
                "radio.tx_enabled=true requires configured [station] identity for classic TX"
            )
        if not callable(tx_submitter):
            raise TypeError("tx_submitter must be callable")
        super().__init__(
            config,
            diagnostics_snapshot=diagnostics_snapshot,
            mheard_db=mheard_db,
        )
        self.tx_config = tx_config
        self.tx_enabled = bool(tx_enabled)
        self.tx_submitter = tx_submitter

    def _shell_factory(self):  # type: ignore[no-untyped-def]
        source = self.tx_config.source
        if source is None:
            # Preserve historical host fixtures and exact P5 behavior when
            # station identity was not part of the old configuration.
            return super()._shell_factory()
        return make_classic_tx_shell(
            source=source,
            paclen=self.tx_config.paclen,
            tx_enabled=self.tx_enabled,
            tx_submitter=self.tx_submitter,
            diagnostics=self._diagnostics,
            monitor_policy=MonitorPolicyState(),
            mheard_db=self._mheard_db,
        )


__all__ = [
    "ProductClassicTXConfig",
    "ProductClassicTXConfigurationError",
    "ProductClassicTXConsole",
    "load_product_classic_tx_config",
    "make_product_backend_submitter",
]
