"""0I-P4c2 local MBOX personality over the frozen persistent BBS store.

This layer adds a terminal mode switch to the current product converse shell.
It deliberately reuses the frozen 0I-P2 ``ClassicBBSSession`` and the same
0I-P1 ``PersistentMailboxStore`` owned by the persistent BBS service.  It does
not create a second mailbox database, connected-mode link, packet queue, modem,
UART path, CSMA policy, scheduler, retry loop, or RF path.

A local terminal has no remote AX.25 peer.  MBOX therefore uses the configured
station identity as both the local BBS address and the mailbox user identity.
The P1 store reduces that peer identity to the base callsign, preserving the
same cross-SSID mailbox semantics used over RF without inventing a privileged
or synthetic caller.
"""
from __future__ import annotations

from typing import Callable

from ywd1278.console.local import CommandResult
from ywd1278.monitor.policy import MonitorPolicyState
from ywd1278.node.classic_bbs import ClassicBBSAction, ClassicBBSSession
from ywd1278.node.persistent_mailbox import PersistentMailboxStore
from ywd1278.service.node_mailbox_config import ProductNodeMailboxConfig
from ywd1278.service.product_converse_console import (
    ProductClassicConverseConsole,
    ProductConverseCommandShell,
)


MailboxStoreGetter = Callable[[], PersistentMailboxStore | None]


def _terminal_lines(actions: tuple[ClassicBBSAction, ...]) -> tuple[str, ...]:
    """Reassemble PACLEN chunks and convert classic CR records to terminal lines."""
    if not actions:
        return ()
    payload = b"".join(action.data for action in actions)
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError as exc:
        return (f"ERROR MBOX OUTPUT UnicodeDecodeError: {exc}",)
    # P2 emits CR records and may include CR/LF message bodies.  Normalize all
    # record separators only after joining PACLEN chunks so a logical line is
    # never split merely because the BBS output was packet-sized.
    text = text.replace("\r\n", "\r").replace("\n", "\r")
    lines = text.split("\r")
    if lines and lines[-1] == "":
        lines.pop()
    return tuple(lines)


class ProductMailboxCommandShell(ProductConverseCommandShell):
    """Current product shell plus one local persistent mailbox personality."""

    def __init__(
        self,
        *,
        mailbox_config: ProductNodeMailboxConfig,
        mailbox_store_getter: MailboxStoreGetter,
        **kwargs,  # type: ignore[no-untyped-def]
    ) -> None:
        if not isinstance(mailbox_config, ProductNodeMailboxConfig):
            raise TypeError("mailbox_config must be ProductNodeMailboxConfig")
        if not callable(mailbox_store_getter):
            raise TypeError("mailbox_store_getter must be callable")
        super().__init__(**kwargs)
        self._mailbox_config = mailbox_config
        self._mailbox_store_getter = mailbox_store_getter
        self._mailbox_session: ClassicBBSSession | None = None

    @property
    def mailbox_mode(self) -> bool:
        return self._mailbox_session is not None

    @property
    def session_prompt_enabled(self) -> bool:
        return super().session_prompt_enabled and not self.mailbox_mode

    def execute(self, line: str) -> CommandResult:
        if not isinstance(line, str):
            raise TypeError("line must be str")

        if self.mailbox_mode:
            return self._execute_mailbox_line(line)

        normalized = line.strip(" \t\r\n")
        if not self.tx_snapshot.converse_mode:
            parts = normalized.split()
            command = parts[0].upper() if parts else ""
            args = parts[1:]
            if command == "MBOX":
                if args:
                    return CommandResult(("ERROR MBOX takes no arguments",))
                return self._enter_mailbox()
            if command in ("HELP", "?") and not args:
                base = super().execute(line)
                return CommandResult(
                    base.lines
                    + (
                        "MBOX                      enter local persistent mailbox mode",
                        "NOTE                      /CMD, COMMAND, CTRL-C, or BYE returns to cmd:",
                    ),
                    base.close,
                )
        return super().execute(line)

    def session_control_etx(self) -> CommandResult | None:
        """Ctrl-C exits local MBOX first; otherwise preserve converse behavior."""
        if self.mailbox_mode:
            self._mailbox_session = None
            return CommandResult(("COMMAND MODE",))
        return super().session_control_etx()

    def session_close(self) -> None:
        self._mailbox_session = None
        super().session_close()

    def _enter_mailbox(self) -> CommandResult:
        config = self._mailbox_config
        if not config.node_enabled or not config.mailbox_enabled or config.local is None:
            return CommandResult(("ERROR MBOX DISABLED; node/mailbox service is not enabled",))
        try:
            store = self._mailbox_store_getter()
        except Exception as exc:
            return CommandResult(
                (f"ERROR MBOX UNAVAILABLE {type(exc).__name__}: {str(exc)[:120]}",)
            )
        if store is None:
            return CommandResult(("ERROR MBOX UNAVAILABLE; persistent mailbox store is not running",))
        if not isinstance(store, PersistentMailboxStore):
            return CommandResult(("ERROR MBOX UNAVAILABLE; invalid persistent mailbox store",))

        session = ClassicBBSSession(
            local=config.local,
            peer=config.local,
            store=store,
            paclen=config.mailbox_paclen,
            now_ns=__import__("time").time_ns,
            info=config.mailbox_info,
        )
        self._mailbox_session = session
        return CommandResult(
            (
                "MBOX MODE; /CMD, COMMAND, CTRL-C, OR BYE RETURNS TO COMMAND MODE",
            )
            + _terminal_lines(session.banner())
        )

    def _execute_mailbox_line(self, line: str) -> CommandResult:
        normalized = line.strip(" \t\r\n")
        if normalized.upper() in ("/CMD", "COMMAND"):
            self._mailbox_session = None
            return CommandResult(("COMMAND MODE",))

        session = self._mailbox_session
        assert session is not None
        try:
            information = line.rstrip("\r\n").encode("ascii") + b"\r"
        except UnicodeEncodeError:
            return CommandResult(("? BBS line must be ASCII",))
        result = session.feed(information)
        lines = _terminal_lines(result.actions)
        if result.close_requested:
            # BYE is a BBS-link close over RF.  In a local MBOX personality it
            # only leaves MBOX; the enclosing Telnet/PTTY session remains open.
            self._mailbox_session = None
        return CommandResult(lines)


class ProductClassicMailboxConsole(ProductClassicConverseConsole):
    """Current product console selecting the MBOX-aware shell per terminal."""

    def __init__(
        self,
        *args,  # type: ignore[no-untyped-def]
        mailbox_config: ProductNodeMailboxConfig,
        mailbox_store_getter: MailboxStoreGetter,
        **kwargs,  # type: ignore[no-untyped-def]
    ) -> None:
        if not isinstance(mailbox_config, ProductNodeMailboxConfig):
            raise TypeError("mailbox_config must be ProductNodeMailboxConfig")
        if not callable(mailbox_store_getter):
            raise TypeError("mailbox_store_getter must be callable")
        self._mailbox_config = mailbox_config
        self._mailbox_store_getter = mailbox_store_getter
        super().__init__(*args, **kwargs)

    def _shell_factory(self):  # type: ignore[no-untyped-def]
        source = self.tx_config.source
        if source is None:
            return super()._shell_factory()
        return ProductMailboxCommandShell(
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
            mailbox_config=self._mailbox_config,
            mailbox_store_getter=self._mailbox_store_getter,
        )


__all__ = [
    "MailboxStoreGetter",
    "ProductClassicMailboxConsole",
    "ProductMailboxCommandShell",
]
