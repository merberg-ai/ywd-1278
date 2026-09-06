"""Product classic converse composition over the qualified packet backend.

This module adds only per-console-session observation around the existing 0F
UNPROTO/converse transmitter. It does not own a modem, UART, channel-access
engine, retry loop, scheduler, or RF path. Each converse session borrows one
already-bounded PacketEvent subscriber queue from the product backend and
deliberately discards the pre-subscription history snapshot so only traffic
observed after entering converse mode is displayed.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from ywd1278.console.auth import load_credential_file
from ywd1278.console.local import CommandResult
from ywd1278.console.product_session import (
    ProductAuthenticatedLanTNCServer,
    ProductTelnetTNCServer,
    ProductVirtualPTYTNC,
)
from ywd1278.monitor.policy import MonitorPolicyState
from ywd1278.monitor.stream import MonitorSubscription
from ywd1278.service.classic_console import ProductClassicConsoleError
from ywd1278.service.product_id_console import (
    ProductClassicIDConsole,
    ProductIDCommandShell,
)


LiveMonitorFactory = Callable[[], MonitorSubscription]


def open_live_only_monitor(
    backend: Any,
    *,
    clock_ns: Callable[[], int] = time.time_ns,
) -> MonitorSubscription:
    """Open one bounded backend subscriber while intentionally dropping history."""
    if not callable(clock_ns):
        raise TypeError("clock_ns must be callable")
    history, live_queue = backend.open_stream()
    del history
    try:
        return MonitorSubscription(
            backend,
            [],
            live_queue,
            clock_ns=clock_ns,
        )
    except BaseException:
        backend.close_stream(live_queue)
        raise


class ProductConverseCommandShell(ProductIDCommandShell):
    """Final product 0F shell with live-only RX while converse mode is active."""

    def __init__(
        self,
        *,
        live_monitor_factory: LiveMonitorFactory,
        **kwargs,  # type: ignore[no-untyped-def]
    ) -> None:
        if not callable(live_monitor_factory):
            raise TypeError("live_monitor_factory must be callable")
        super().__init__(**kwargs)
        self._live_monitor_factory = live_monitor_factory
        self._live_monitor: MonitorSubscription | None = None

    def execute(self, line: str) -> CommandResult:
        if not isinstance(line, str):
            raise TypeError("line must be str")

        before = self.tx_snapshot.converse_mode
        normalized = line.strip(" \t\r\n")
        if before and normalized.upper() == "/CMD":
            line = "COMMAND"

        result = super().execute(line)
        after = self.tx_snapshot.converse_mode

        if not before and after:
            try:
                self._live_monitor = self._live_monitor_factory()
            except Exception as exc:
                # CONVERSE has not submitted anything yet. If observation
                # cannot be attached, fail closed back to command mode rather
                # than creating a half-functional product session.
                super().execute("COMMAND")
                return CommandResult(
                    (
                        "ERROR CONVERSE RX UNAVAILABLE "
                        f"{type(exc).__name__}: {str(exc)[:120]}; COMMAND MODE",
                    )
                )
            result = CommandResult(
                result.lines
                + (
                    "TYPE /CMD, COMMAND, OR CTRL-C TO RETURN TO COMMAND MODE",
                    "LIVE RX DISPLAY ENABLED; PRE-CONVERSE HISTORY NOT REPLAYED",
                ),
                result.close,
            )
        elif before and not after:
            self._close_live_monitor()
        elif not before and normalized.upper() in ("HELP", "?"):
            result = CommandResult(
                result.lines
                + (
                    "/CMD                      printable converse-to-command escape",
                    "CTRL-C                    converse-to-command escape on product transports",
                ),
                result.close,
            )
        return result

    @property
    def session_prompt_enabled(self) -> bool:
        return not self.tx_snapshot.converse_mode

    def session_control_etx(self) -> CommandResult | None:
        """Translate Ctrl-C only while this product shell is in converse mode."""
        if not self.tx_snapshot.converse_mode:
            return None
        return self.execute("/CMD")

    def session_drain_output(self, *, maximum: int = 16) -> tuple[str, ...]:
        if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 1:
            raise ValueError("maximum must be a positive integer")
        subscription = self._live_monitor
        if subscription is None:
            return ()
        records = subscription.read_available(maximum=maximum)
        return tuple(f"RX {record.line}" for record in records)

    def session_close(self) -> None:
        self._close_live_monitor()

    def _close_live_monitor(self) -> None:
        subscription = self._live_monitor
        self._live_monitor = None
        if subscription is not None:
            subscription.close()


class ProductClassicConverseConsole(ProductClassicIDConsole):
    """Current product console selecting converse-aware transports and shell."""

    def __init__(
        self,
        *args,  # type: ignore[no-untyped-def]
        live_monitor_factory: LiveMonitorFactory,
        **kwargs,  # type: ignore[no-untyped-def]
    ) -> None:
        if not callable(live_monitor_factory):
            raise TypeError("live_monitor_factory must be callable")
        self._live_monitor_factory = live_monitor_factory
        super().__init__(*args, **kwargs)

    def _shell_factory(self):  # type: ignore[no-untyped-def]
        source = self.tx_config.source
        if source is None:
            return super()._shell_factory()
        return ProductConverseCommandShell(
            source=source,
            paclen=self.tx_config.paclen,
            tx_enabled=self.tx_enabled,
            tx_submitter=self.tx_submitter,
            beacon=self.beacon,
            clock=self._beacon_clock,
            diagnostics=self._diagnostics,
            monitor_policy=MonitorPolicyState(),
            mheard_db=self._mheard_db,
            live_monitor_factory=self._live_monitor_factory,
        )

    def start(self) -> None:
        """Start the same bounded surfaces, selecting product-session transports."""
        if self._started:
            raise ProductClassicConsoleError("product classic console is single-start")
        self._started = True
        if not self.config.enabled:
            return

        try:
            if self.config.auth_file is None:
                server = ProductTelnetTNCServer(
                    (self.config.host, self.config.port),
                    shell_factory=self._shell_factory,
                )
            else:
                credential = load_credential_file(self.config.auth_file)
                server = ProductAuthenticatedLanTNCServer(
                    (self.config.host, self.config.port),
                    credential=credential,
                    shell_factory=self._shell_factory,
                )
            self.telnet_server = server

            if self.config.pty_enabled:
                pty = ProductVirtualPTYTNC(
                    shell_factory=self._shell_factory,
                    link_path=str(self.config.pty_link) if self.config.pty_link else None,
                )
                self.pty_server = pty
                pty.open()

            telnet_thread = threading.Thread(
                target=server.serve_forever,
                kwargs={"poll_interval": 0.1},
                name="ywd1278-classic-telnet",
                daemon=True,
            )
            self.telnet_thread = telnet_thread
            telnet_thread.start()

            if self.pty_server is not None:
                self._pty_stop.clear()
                pty_thread = threading.Thread(
                    target=self.pty_server.serve,
                    args=(self._pty_stop,),
                    name="ywd1278-classic-pty",
                    daemon=True,
                )
                self.pty_thread = pty_thread
                pty_thread.start()

            self.check_health()
        except BaseException:
            self._cleanup()
            raise


__all__ = [
    "LiveMonitorFactory",
    "ProductClassicConverseConsole",
    "ProductConverseCommandShell",
    "open_live_only_monitor",
]
