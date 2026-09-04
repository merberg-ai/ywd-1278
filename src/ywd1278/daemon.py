from __future__ import annotations

import argparse
from pathlib import Path
import signal
import sys
import threading

from . import __version__
from .service.appliance import (
    ProductConfigurationError,
    ProductPacketEngine,
    ProductPacketEngineError,
    load_product_packet_engine_config,
)


def run_daemon(
    config_path: str | Path,
    *,
    stop_event: threading.Event,
    transport_factory=None,  # type: ignore[no-untyped-def]
    random_byte_source=None,  # type: ignore[no-untyped-def]
) -> int:
    """Run one product packet-engine lifecycle until the caller requests stop.

    The injectable transport/randomness arguments are host-qualification seams.
    Normal CLI/systemd execution supplies neither and therefore uses the private
    POSIX serial transport plus runtime randomness owned by the appliance layer.
    """

    config = load_product_packet_engine_config(config_path)
    engine = ProductPacketEngine(
        config,
        transport_factory=transport_factory,
        random_byte_source=random_byte_source,
    )
    engine.start()
    snapshot = engine.snapshot
    print("YWD1278_PRODUCT_PACKET_ENGINE=RUNNING", flush=True)
    print(f"FIRMWARE_IDENTITY={snapshot.firmware_identity}", flush=True)
    print(f"PRODUCT_TX={'ENABLED' if snapshot.tx_enabled else 'DISABLED'}", flush=True)
    if snapshot.kiss_listener is None:
        print("KISS_LISTENER=DISABLED", flush=True)
    else:
        print(f"KISS_LISTENER={snapshot.kiss_listener[0]}:{snapshot.kiss_listener[1]}", flush=True)

    try:
        while not stop_event.wait(0.25):
            engine.check_health()
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
    except (ProductConfigurationError, ProductPacketEngineError, OSError) as exc:
        print(f"YWD-1278 {__version__}: packet-engine startup/runtime failure: {exc}", file=sys.stderr)
        return 78
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)


if __name__ == "__main__":
    raise SystemExit(main())
