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
    load_product_classic_tx_config,
    make_product_backend_submitter,
)
from .service.beacon_scheduler import ProductBeaconScheduler
from .service.beacon_access_policy import JitteredThreadSafeProductBeaconCoordinator
from .service.forwarding_config import (
    ProductForwardingConfigurationError,
    load_product_forwarding_config,
)
from .service.node_mailbox_config import (
    ProductNodeMailboxConfigurationError,
    load_product_node_mailbox_config,
)
from .service.persistent_bbs_service import ProductPersistentBBSService
from .service.product_converse_console import open_live_only_monitor
from .service.product_mailbox_console import ProductClassicMailboxConsole


def run_daemon(
    config_path: str | Path,
    *,
    stop_event: threading.Event,
    transport_factory=None,  # type: ignore[no-untyped-def]
    random_byte_source=None,  # type: ignore[no-untyped-def]
    beacon_clock=None,  # type: ignore[no-untyped-def]
    beacon_jitter_byte_source=None,  # type: ignore[no-untyped-def]
    beacon_poll_interval_seconds: float = 0.1,
) -> int:
    """Run the product packet engine, terminal stack, and optional persistent BBS.

    The injectable transport/randomness arguments are host-qualification seams.
    Normal CLI/systemd execution supplies neither and therefore uses the private
    POSIX serial transport plus runtime randomness owned by the appliance layer.

    0F console UNPROTO/converse traffic and 0I persistent connected-BBS traffic
    both reuse the exact live ``ProductTNCBackend`` KISS DATA admission boundary.
    The BBS subscribes to one existing bounded PacketEvent stream, discards its
    history snapshot, and submits connected-mode responses through that same
    product backend.  No second decoder, CSMA engine, TX queue, modem owner, UART
    path, or RF implementation is introduced by 0I.

    The terminal ``MBOX`` personality reuses the exact P1 store owned by the BBS
    service and the frozen P2 BBS command personality.  It performs no packet
    submission; local /CMD, COMMAND, Ctrl-C, or BYE returns to ``cmd:``.

    0H-P11 forwarding remains physically unqualified and therefore disabled.
    Historical fixtures with node/mailbox disabled retain their prior packet and
    console behavior, with MBOX present only as a fail-closed local command.
    """

    packet_config = load_product_packet_engine_config(config_path)
    console_config = load_product_classic_console_config(config_path)
    classic_tx_config = load_product_classic_tx_config(config_path)
    forwarding_config = load_product_forwarding_config(config_path)
    node_mailbox_config = load_product_node_mailbox_config(config_path)
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
    bbs_service: ProductPersistentBBSService | None = None
    if node_mailbox_config.node_enabled:
        bbs_service = ProductPersistentBBSService(
            node_mailbox_config,
            backend_getter=lambda: engine.backend,
            tx_enabled=packet_config.tx_enabled,
        )

    engine.start()
    beacon_scheduler: ProductBeaconScheduler | None = None

    if console_config.enabled and classic_tx_config.configured:
        submitter = make_product_backend_submitter(lambda: engine.backend)
        assert classic_tx_config.source is not None
        jitter_source = beacon_jitter_byte_source
        if jitter_source is None and random_byte_source is not None:
            jitter_source = random_byte_source
        beacon_kwargs = {} if jitter_source is None else {"jitter_byte_source": jitter_source}
        beacon = JitteredThreadSafeProductBeaconCoordinator(
            source=classic_tx_config.source,
            paclen=classic_tx_config.paclen,
            tx_enabled=packet_config.tx_enabled,
            tx_submitter=submitter,
            **beacon_kwargs,
        )
        beacon_scheduler = ProductBeaconScheduler(
            beacon,
            poll_interval_seconds=beacon_poll_interval_seconds,
            clock=shared_beacon_clock,
        )
        console: ProductClassicConsole = ProductClassicMailboxConsole(
            console_config,
            tx_config=classic_tx_config,
            tx_enabled=packet_config.tx_enabled,
            tx_submitter=submitter,
            beacon=beacon,
            clock=shared_beacon_clock,
            diagnostics_snapshot=engine.diagnostics_snapshot,
            mheard_db=engine.mheard_db,
            live_monitor_factory=lambda: open_live_only_monitor(engine.backend),
            mailbox_config=node_mailbox_config,
            mailbox_store_getter=(
                lambda: None if bbs_service is None else bbs_service.store
            ),
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
        if bbs_service is not None:
            bbs_service.start()
        console.start()
        if beacon_scheduler is not None:
            beacon_scheduler.start()

        snapshot = engine.snapshot
        console_snapshot = console.snapshot
        print("YWD1278_PRODUCT_PACKET_ENGINE=RUNNING", flush=True)
        print(f"FIRMWARE_IDENTITY={snapshot.firmware_identity}", flush=True)
        print(f"PRODUCT_TX={'ENABLED' if snapshot.tx_enabled else 'DISABLED'}", flush=True)
        print(f"CLASSIC_0F={classic_0f}", flush=True)
        if bbs_service is None:
            print("PERSISTENT_BBS=DISABLED", flush=True)
            print("MBOX=DISABLED", flush=True)
        else:
            print("PERSISTENT_BBS=ENABLED", flush=True)
            print(f"PERSISTENT_BBS_DATABASE={node_mailbox_config.mailbox_database}", flush=True)
            print("MBOX=ENABLED", flush=True)
        print("PERSISTENT_BBS_PHYSICAL_QUALIFICATION=DEFERRED", flush=True)
        print("FORWARDING=DISABLED", flush=True)
        print(
            f"FORWARDING_CONFIG=interval:{forwarding_config.interval_seconds},batch:{forwarding_config.max_batch}",
            flush=True,
        )
        print("FORWARDING_PHYSICAL_QUALIFICATION=DEFERRED", flush=True)
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
            if bbs_service is not None:
                bbs_service.check_health()
    finally:
        # Revoke terminal observers and the BBS PacketEvent subscriber before
        # the packet engine tears down their shared backend and diagnostics.
        try:
            console.stop()
        finally:
            try:
                if beacon_scheduler is not None:
                    beacon_scheduler.stop()
            finally:
                try:
                    if bbs_service is not None:
                        bbs_service.stop()
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
        ProductForwardingConfigurationError,
        ProductNodeMailboxConfigurationError,
        RuntimeError,
        OSError,
    ) as exc:
        print(
            f"YWD-1278 {__version__}: packet-engine/console/BBS startup/runtime failure: {exc}",
            file=sys.stderr,
        )
        return 78
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)


if __name__ == "__main__":
    raise SystemExit(main())
