from __future__ import annotations

import argparse
from pathlib import Path
import signal
import sys
import threading
import time

from . import __version__
from .service.appliance import (
    ProductConfigurationError,
    ProductPacketEngine,
    load_product_packet_engine_config,
)
from .service.classic_console import (
    ProductClassicConsole,
    ProductClassicConsoleConfigurationError,
    load_product_classic_console_config,
)
from .service.classic_tx_console import (
    ProductClassicTXConfigurationError,
    ProductClassicTXConsole,
    load_product_classic_tx_config,
    make_product_backend_submitter,
)
from .service.beacon_scheduler import ProductBeaconScheduler
from .service.product_beacon_console import (
    ThreadSafeProductBeaconCoordinator,
)
from .service.product_id_console import ProductClassicIDConsole


def run_daemon(
    config_path: str | Path,
    *,
    stop_event: threading.Event,
    transport_factory=None,  # type: ignore[no-untyped-def]
    random_byte_source=None,  # type: ignore[no-untyped-def]
    beacon_clock=None,  # type: ignore[no-untyped-def]
    beacon_poll_interval_seconds: float = 0.1,
) -> int:
    """Run one product packet engine plus the qualified classic console stack.

    The injectable transport/randomness arguments are host-qualification seams.
    Normal CLI/systemd execution supplies neither and therefore uses the private
    POSIX serial transport plus runtime randomness owned by the appliance layer.

    0F extends only the console personality.  When ``[station]`` identity is
    configured, per-session UNPROTO/converse UI frame bodies are handed to the
    exact live ``ProductTNCBackend`` KISS DATA admission boundary.  The console
    does not gain a second queue, CSMA engine, modem owner, UART path, or retry
    loop.  ``radio.tx_enabled=false`` remains the construction-time product TX
    gate and the 0F shell fails closed before invoking its submit callback.

    Historical host fixtures with no ``[station]`` table retain the exact
    frozen P5 personality so earlier qualification remains replayable.
    """

    packet_config = load_product_packet_engine_config(config_path)
    console_config = load_product_classic_console_config(config_path)
    classic_tx_config = load_product_classic_tx_config(config_path)
    shared_beacon_clock = time.monotonic if beacon_clock is None else beacon_clock
    if not callable(shared_beacon_clock):
        raise TypeError("beacon_clock must be callable or None")
    if isinstance(beacon_poll_interval_seconds, bool) or not isinstance(
        beacon_poll_interval_seconds, (int, float)
    ) or not 0.01 <= float(beacon_poll_interval_seconds) <= 1.0:
        raise ValueError("beacon_poll_interval_seconds must be 0.01..1.0")
    engine = ProductPacketEngine(
        packet_config,
        transport_factory=transport_factory,
        random_byte_source=random_byte_source,
    )
    engine.start()
    beacon_scheduler: ProductBeaconScheduler | None = None

    if console_config.enabled and classic_tx_config.configured:
        submitter = make_product_backend_submitter(lambda: engine.backend)
        assert classic_tx_config.source is not None
        beacon = ThreadSafeProductBeaconCoordinator(
            source=classic_tx_config.source,
            paclen=classic_tx_config.paclen,
            tx_enabled=packet_config.tx_enabled,
            tx_submitter=submitter,
        )
        beacon_scheduler = ProductBeaconScheduler(
            beacon,
            poll_interval_seconds=beacon_poll_interval_seconds,
            clock=shared_beacon_clock,
        )
        console: ProductClassicConsole = ProductClassicIDConsole(
            console_config,
            tx_config=classic_tx_config,
            tx_enabled=packet_config.tx_enabled,
            tx_submitter=submitter,
            beacon=beacon,
            clock=shared_beacon_clock,
            diagnostics_snapshot=engine.diagnostics_snapshot,
            mheard_db=engine.mheard_db,
        )
        classic_0f = "ENABLED" if packet_config.tx_enabled else "TX-DISABLED"
    else:
        console = ProductClassicConsole(
            console_config,
            diagnostics_snapshot=engine.diagnostics_snapshot,
            mheard_db=engine.mheard_db,
        )
        classic_0f = "UNCONFIGURED"

    try:
        console.start()
        if beacon_scheduler is not None:
            beacon_scheduler.start()

        snapshot = engine.snapshot
        console_snapshot = console.snapshot
        print("YWD1278_PRODUCT_PACKET_ENGINE=RUNNING", flush=True)
        print(f"FIRMWARE_IDENTITY={snapshot.firmware_identity}", flush=True)
        print(f"PRODUCT_TX={'ENABLED' if snapshot.tx_enabled else 'DISABLED'}", flush=True)
        print(f"CLASSIC_0F={classic_0f}", flush=True)
        if snapshot.kiss_listener is None:
            print("KISS_LISTENER=DISABLED", flush=True)
        else:
            print(
                f"KISS_LISTENER={snapshot.kiss_listener[0]}:{snapshot.kiss_listener[1]}",
                flush=True,
            )

        if console_snapshot.telnet_listener is None:
            print("CLASSIC_TELNET=DISABLED", flush=True)
        else:
            host, port = console_snapshot.telnet_listener
            auth = "AUTHENTICATED" if console_snapshot.telnet_authenticated else "LOOPBACK"
            print(f"CLASSIC_TELNET={host}:{port}:{auth}", flush=True)
        if not console_snapshot.pty_enabled:
            print("CLASSIC_PTY=DISABLED", flush=True)
        else:
            print(f"CLASSIC_PTY={console_snapshot.pty_slave}", flush=True)
            if console_snapshot.pty_link is not None:
                print(f"CLASSIC_PTY_LINK={console_snapshot.pty_link}", flush=True)

        while not stop_event.wait(0.25):
            engine.check_health()
            console.check_health()
    finally:
        # Command sessions consume Stage-C diagnostics/MHEARD.  Revoke those
        # observers before the packet engine tears their sources down.
        try:
            console.stop()
        finally:
            try:
                if beacon_scheduler is not None:
                    beacon_scheduler.stop()
            finally:
                engine.stop()
        print("YWD1278_PRODUCT_PACKET_ENGINE=STOPPED", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="ywd1278d")
    parser.add_argument("--config", default="/etc/ywd-1278/config.toml")
    parser.add_argument(
        "--framework-self-test",
        action="store_true",
        help="verify package/config plumbing without opening the modem or transmitting RF",
    )
    args = parser.parse_args()

    config = Path(args.config)
    if not config.is_file():
        print(f"YWD-1278 {__version__}: missing config: {config}", file=sys.stderr)
        return 2

    if args.framework_self_test:
        print("YWD1278_FRAMEWORK_SELF_TEST=PASS")
        print("MODEM_UART_OPENED=NO")
        print("RF_TRANSMITTED=NO")
        return 0

    stop_event = threading.Event()

    def request_stop(signum, frame) -> None:  # type: ignore[no-untyped-def]
        _ = signum, frame
        stop_event.set()

    previous_sigint = signal.getsignal(signal.SIGINT)
    previous_sigterm = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        return run_daemon(config, stop_event=stop_event)
    except (
        ProductConfigurationError,
        ProductClassicConsoleConfigurationError,
        ProductClassicTXConfigurationError,
        RuntimeError,
        OSError,
    ) as exc:
        print(
            f"YWD-1278 {__version__}: packet-engine/console startup/runtime failure: {exc}",
            file=sys.stderr,
        )
        return 78
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)


if __name__ == "__main__":
    raise SystemExit(main())
