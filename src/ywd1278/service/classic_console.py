"""Production composition of the frozen 0E classic TNC console stack.

Stage D owns lifecycle and product policy only.  It does not duplicate or edit
any qualified 0E parser/transport implementation.  Each logical console
session receives a fresh frozen P5 ``ClassicTNCCommandShell`` backed by the
running Stage-C diagnostics/MHEARD sources and an independent
``MonitorPolicyState``.

Product policy:

* literal IPv4 loopback Telnet without an auth file uses frozen P2;
* RFC1918 Telnet is permitted only with a protected frozen-P3 credential file;
* supplying an auth file on loopback deliberately selects frozen P3 as well;
* wildcard/public/CGNAT/link-local/hostname/IPv6 binds are rejected;
* the local pseudo-serial surface uses frozen P4 ``VirtualPTYTNC``;
* no console surface gains modem, KISS DATA, TX, beacon, UNPROTO, converse, or
  connected-mode authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from pathlib import Path
import threading
from typing import Any, Callable

from ywd1278.console.auth import load_credential_file
from ywd1278.console.classic import make_classic_shell
from ywd1278.console.lan_telnet import AuthenticatedLanTNCServer
from ywd1278.console.pty_serial import VirtualPTYTNC
from ywd1278.console.telnet import TelnetTNCServer
from ywd1278.monitor.mheard import MHeardDatabase
from ywd1278.monitor.policy import MonitorPolicyState


DiagnosticsSnapshotter = Callable[[], Any]


_RFC1918_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)


class ProductClassicConsoleError(RuntimeError):
    pass


def _allowed_console_address(address: str) -> tuple[str, bool]:
    if not isinstance(address, str) or not address:
        raise ValueError("console.listen must be a non-empty literal IPv4 address")
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError as exc:
        raise ValueError("console.listen must be a literal IPv4 address") from exc
    if parsed.version != 4:
        raise ValueError("console listener supports IPv4 only")
    normalized = str(parsed)
    if parsed.is_loopback:
        return normalized, True
    if any(parsed in network for network in _RFC1918_NETWORKS):
        return normalized, False
    raise ValueError("console listener is restricted to loopback or RFC1918 IPv4")


@dataclass(frozen=True)
class ProductClassicConsoleConfig:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8010
    auth_file: Path | None = None
    pty_enabled: bool = False
    pty_link: Path | None = None

    def __post_init__(self) -> None:
        host, loopback = _allowed_console_address(self.host)
        object.__setattr__(self, "host", host)
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("console.port must be 1..65535")
        if self.auth_file is not None and not self.auth_file.is_absolute():
            raise ValueError("console.auth_file must be an absolute path")
        if self.enabled and not loopback and self.auth_file is None:
            raise ValueError("RFC1918 console listener requires console.auth_file")
        if self.pty_link is not None and not self.pty_link.is_absolute():
            raise ValueError("console.pty_link must be an absolute path")
        if self.pty_link is not None and not self.pty_enabled:
            raise ValueError("console.pty_link requires console.pty_enabled=true")


@dataclass(frozen=True)
class ProductClassicConsoleSnapshot:
    enabled: bool
    running: bool
    telnet_listener: tuple[str, int] | None
    telnet_authenticated: bool
    pty_enabled: bool
    pty_slave: str | None
    pty_link: str | None


class _LiveDiagnostics:
    """Tiny adapter giving frozen P1/P5 the ``snapshot()`` API it expects."""

    def __init__(self, snapshotter: DiagnosticsSnapshotter) -> None:
        if not callable(snapshotter):
            raise TypeError("diagnostics snapshotter must be callable")
        self._snapshotter = snapshotter

    def snapshot(self) -> Any:
        return self._snapshotter()


class ProductClassicConsole:
    """Lifecycle owner for qualified P2/P3/P4 transports plus P5 personality."""

    def __init__(
        self,
        config: ProductClassicConsoleConfig,
        *,
        diagnostics_snapshot: DiagnosticsSnapshotter,
        mheard_db: MHeardDatabase | None,
    ) -> None:
        if not isinstance(config, ProductClassicConsoleConfig):
            raise TypeError("config must be ProductClassicConsoleConfig")
        self.config = config
        self._diagnostics = _LiveDiagnostics(diagnostics_snapshot)
        self._mheard_db = mheard_db

        self.telnet_server: TelnetTNCServer | AuthenticatedLanTNCServer | None = None
        self.telnet_thread: threading.Thread | None = None
        self.pty_server: VirtualPTYTNC | None = None
        self.pty_thread: threading.Thread | None = None
        self._pty_stop = threading.Event()
        self._started = False
        self._stopped = False

    def _shell_factory(self):  # type: ignore[no-untyped-def]
        return make_classic_shell(
            diagnostics=self._diagnostics,
            monitor_policy=MonitorPolicyState(),
            mheard_db=self._mheard_db,
        )

    @property
    def snapshot(self) -> ProductClassicConsoleSnapshot:
        if not self.config.enabled:
            return ProductClassicConsoleSnapshot(
                enabled=False,
                running=True,
                telnet_listener=None,
                telnet_authenticated=False,
                pty_enabled=False,
                pty_slave=None,
                pty_link=None,
            )

        listener = None
        if self.telnet_server is not None:
            host, port = self.telnet_server.server_address[:2]
            listener = (str(host), int(port))
        telnet_running = bool(self.telnet_thread and self.telnet_thread.is_alive())
        pty_running = True
        pty_slave = None
        pty_link = None
        if self.config.pty_enabled:
            pty_running = bool(self.pty_thread and self.pty_thread.is_alive())
            if self.pty_server is not None:
                pty_slave = self.pty_server.slave_path
                if self.pty_server.link_path is not None:
                    pty_link = self.pty_server.link_path
        return ProductClassicConsoleSnapshot(
            enabled=True,
            running=telnet_running and pty_running,
            telnet_listener=listener,
            telnet_authenticated=self.config.auth_file is not None,
            pty_enabled=self.config.pty_enabled,
            pty_slave=pty_slave,
            pty_link=pty_link,
        )

    def start(self) -> None:
        if self._started:
            raise ProductClassicConsoleError("product classic console is single-start")
        self._started = True
        if not self.config.enabled:
            return

        try:
            if self.config.auth_file is None:
                server: TelnetTNCServer | AuthenticatedLanTNCServer = TelnetTNCServer(
                    (self.config.host, self.config.port),
                    shell_factory=self._shell_factory,
                )
            else:
                credential = load_credential_file(self.config.auth_file)
                server = AuthenticatedLanTNCServer(
                    (self.config.host, self.config.port),
                    credential=credential,
                    shell_factory=self._shell_factory,
                )
            self.telnet_server = server

            if self.config.pty_enabled:
                pty = VirtualPTYTNC(
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

    def check_health(self) -> None:
        if not self.config.enabled:
            return
        if self.telnet_server is None or self.telnet_thread is None:
            raise ProductClassicConsoleError("configured Telnet console is absent")
        if not self.telnet_thread.is_alive():
            raise ProductClassicConsoleError("Telnet console thread is not running")
        if self.config.pty_enabled:
            if self.pty_server is None or self.pty_thread is None:
                raise ProductClassicConsoleError("configured PTY console is absent")
            if not self.pty_thread.is_alive():
                raise ProductClassicConsoleError("PTY console thread is not running")

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._cleanup()

    def _cleanup(self) -> None:
        # Stop accepting/serving command sessions before Stage-C sources are
        # torn down by the product engine.
        if self.telnet_server is not None:
            try:
                self.telnet_server.shutdown()
            except BaseException:
                pass
            try:
                self.telnet_server.server_close()
            except BaseException:
                pass
        if self.telnet_thread is not None:
            self.telnet_thread.join(timeout=2.0)
        self.telnet_thread = None
        self.telnet_server = None

        self._pty_stop.set()
        if self.pty_thread is not None:
            self.pty_thread.join(timeout=2.0)
        if self.pty_server is not None:
            self.pty_server.close()
        self.pty_thread = None
        self.pty_server = None


__all__ = [
    "ProductClassicConsole",
    "ProductClassicConsoleConfig",
    "ProductClassicConsoleError",
    "ProductClassicConsoleSnapshot",
]
