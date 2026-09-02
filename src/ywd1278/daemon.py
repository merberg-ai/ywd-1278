from __future__ import annotations

import argparse
from pathlib import Path
import sys

from . import __version__


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

    # Fail closed until the physically qualified ywd-mmdvm packet engine has
    # been ported and re-qualified under YWD-1278 branding.
    print(
        "YWD-1278 packet engine is not enabled in this initial framework. "
        "The service will remain disabled until the porting/qualification gate is complete.",
        file=sys.stderr,
    )
    return 78


if __name__ == "__main__":
    raise SystemExit(main())
