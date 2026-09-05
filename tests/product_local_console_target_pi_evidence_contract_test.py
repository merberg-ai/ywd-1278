#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0e-product-local-console-target-pi.json"


def blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def main() -> int:
    d = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert d["schema"] == 1
    assert d["status"] == "target-pi-qualified"

    p = d["product_under_test"]
    assert p["installed_commit"] == "2f5299e65add072fea6ee55a54dc421faf00c276"
    assert p["local_console_blob"] == "9fed5416ca9123811413f4ef284abff0006a48dd"
    assert p["entrypoint"] == "/opt/ywd-1278/venv/bin/ywd1278-console"
    assert p["database"] == "/var/lib/ywd-1278/ywd-1278.sqlite3"

    pre = d["precheck"]
    assert pre["tty_stdin"] is True
    assert pre["tty_stdout_probe"] is False
    assert pre["service_enabled"] is True
    assert pre["service_active"] is True
    assert pre["mheard_database_readable"] is True
    assert pre["putty_session_survived"] is True

    s = d["interactive_session"]
    assert s["prompt_present"] is True
    assert s["commands_entered_manually"] == ["VERSION", "HEALTH", "MHEARD 5", "HELP", "QUIT"]
    assert s["version_output"] == "YWD-1278 0.1.0-alpha0"
    assert s["health"] == {"status": "OK", "problems": "NONE", "sources": "1/10"}
    assert s["mheard"]["result_count"] == 2
    assert s["mheard"]["entries"][0]["source"] == "KJ6YWD-5"
    assert s["mheard"]["entries"][1]["source"] == "KJ6YWD"
    assert s["help_surface_present"] is True
    assert s["quit_result"] == "BYE"
    assert s["returned_to_shell"] is True

    safety = d["safety"]
    for key in (
        "service_stopped",
        "service_restarted",
        "persistent_config_mutated",
        "modem_uart_opened_by_console",
        "kiss_session_opened_by_console",
        "network_listener_opened_by_console",
        "tx_path_opened_by_console",
        "rf_transmitted",
        "flash_written",
        "option_bytes_written",
    ):
        assert safety[key] is False, key
    assert safety["database_access_mode"] == "read-only MHEARD view"

    q = d["qualified_claims"]
    assert all(q.values())

    # The installed appliance uses the same frozen local console implementation
    # that was qualified at 0E-P1.
    assert blob(ROOT / "src/ywd1278/console/local.py") == "9fed5416ca9123811413f4ef284abff0006a48dd"

    print("PRODUCT_LOCAL_CONSOLE_TARGET_PI_EVIDENCE=PASS")
    print("INTERACTIVE_PROMPT=PASS")
    print("HEALTH=OK")
    print("MHEARD_READ_ONLY=PASS")
    print("RF_TRANSMITTED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
