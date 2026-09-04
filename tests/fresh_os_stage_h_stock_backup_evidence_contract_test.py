#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0b-product-fresh-os-stage-h-stock-backup-target-pi.json"


def main() -> int:
    d = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert d["schema"] == 1 and d["stage"] == "H"
    assert d["status"] == "target-pi-stock-backup-qualified"
    assert d["target"] == "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"
    assert d["pre_backup_identity"] == "MMDVM_HS_Hat-v1.6.1 20230526 14.7456MHz ADF7021 FW by CA6JAU GitID #7ff74ed"
    assert d["bootloader"] == {"version":"0x22","device_id":"0x0410","identity_verified":True}
    b = d["backup"]
    golden = "4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684"
    assert b["flash_base"] == "0x08000000"
    assert b["flash_size_bytes"] == 131072
    assert b["read_passes"] == 2
    assert b["read_a_sha256"] == golden == b["read_b_sha256"]
    assert b["two_pass_byte_identical"] is True
    assert b["stock_golden_sha256_match"] is True
    assert b["option_bytes_read"] is False
    p = d["post_backup"]
    assert p["application_identity_returned_exactly"] is True
    assert p["stock_backup_exit_code"] == 0
    assert p["putty_session_survived"] is True
    assert p["packet_service_enabled"] is False
    assert p["packet_service_active"] is False
    assert p["flash_written"] is False
    assert p["option_bytes_written"] is False
    assert p["rf_transmitted"] is False
    print("YWD1278_STAGE_H_STOCK_BACKUP_EVIDENCE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
