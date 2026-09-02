#!/usr/bin/env python3
"""0B-P7b-2 guarded live single-owner GET_VERSION qualification.

This tool opens the modem UART only through `ModemOwner` and the private
thread-bound POSIX transport.  It sends exactly one GET_VERSION request and
performs no GPIO, RF configuration, RX start, or TX operation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.modem._serial import posix_serial_transport_factory  # noqa: E402
from ywd1278.modem.owner import ModemOwner  # noqa: E402

DEFAULT_TARGET = "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"


def load_target(target_id: str) -> dict:
    manifest = json.loads((ROOT / "firmware" / "targets.json").read_text(encoding="utf-8"))
    for target in manifest.get("targets", []):
        if target.get("id") == target_id:
            return target
    raise SystemExit(f"FAIL: unknown target {target_id!r}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Guarded live GET_VERSION proof through the YWD-1278 single UART owner"
    )
    ap.add_argument("--target", default=DEFAULT_TARGET)
    ap.add_argument("--device")
    args = ap.parse_args()

    target = load_target(args.target)
    device = args.device or target.get("uart_default") or "/dev/ttyAMA0"
    accepted = tuple(target.get("accepted_running_identities", []))
    if not accepted:
        raise SystemExit("FAIL: target has no accepted running identities")

    print("=== YWD-1278 0B-P7b-2 LIVE OWNER IDENTITY PROBE ===")
    print(f"Target           : {args.target}")
    print(f"Device           : {device}")
    print("Owner threads    : exactly one")
    print("Operation        : GET_VERSION only")
    print("GPIO accessed    : NO")
    print("RF configured    : NO")
    print("RX started       : NO")
    print("TX API reachable : NO")
    print("Flash operations : NO")

    owner = ModemOwner(
        posix_serial_transport_factory(device),
        queue_capacity=2,
        submit_timeout=0.25,
        default_transaction_timeout=1.5,
    )
    try:
        owner.start(timeout=2.0)
        version = owner.get_version(timeout=1.5)
        snapshot = owner.snapshot
    finally:
        owner.stop(timeout=2.0)

    print(f"Protocol version : {version.protocol_version}")
    print(f"Identity         : {version.identity}")
    print(f"Transactions     : {snapshot.transactions}")
    print(f"Owner thread ID  : {snapshot.owner_thread_id}")

    if version.identity not in accepted:
        print("YWD1278_MODEM_OWNER_IDENTITY=FAIL reason=identity_not_allowlisted")
        return 2
    if snapshot.transactions != 1:
        print("YWD1278_MODEM_OWNER_IDENTITY=FAIL reason=unexpected_transaction_count")
        return 3

    print("YWD1278_MODEM_OWNER_IDENTITY=PASS")
    print("MODEM_UART_OPENED=YES")
    print("MODEM_TRANSACTIONS=1")
    print("MODEM_SINGLE_OWNER=YES")
    print("MODEM_COMMANDS_SENT=GET_VERSION_ONLY")
    print("RF_CONFIGURED=NO")
    print("RX_STARTED=NO")
    print("RF_TRANSMITTED=NO")
    print("FLASH_WRITTEN=NO")
    print("OPTION_BYTES_WRITTEN=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
