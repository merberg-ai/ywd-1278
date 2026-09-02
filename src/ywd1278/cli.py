from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__


def main() -> int:
    parser = argparse.ArgumentParser(prog="ywd1278", description="YWD-1278 packet TNC utilities")
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--config", default="/etc/ywd-1278/config.toml")
    args = parser.parse_args()

    if args.version:
        print(f"YWD-1278 {__version__}")
        return 0

    config = Path(args.config)
    print(f"YWD-1278 {__version__}")
    print(f"config: {config}")
    print(f"config_exists: {'yes' if config.is_file() else 'no'}")
    print("engine_status: framework-only")
    print("note: qualified packet engine port has not been enabled in this scaffold yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
