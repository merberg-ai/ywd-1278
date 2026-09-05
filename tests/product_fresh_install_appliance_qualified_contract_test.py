#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "firmware/qualification/product-fresh-install-appliance-qualified.json"
LOCAL = ROOT / "firmware/qualification/0e-product-local-console-target-pi.json"
STAGE_I = ROOT / "firmware/qualification/0b-product-fresh-os-stage-i-tx-target-pi.json"
STAGE_H = ROOT / "firmware/qualification/0b-product-fresh-os-stage-h-reboot-target-pi.json"


def main() -> int:
    f = json.loads(FINAL.read_text(encoding="utf-8"))
    assert f["schema"] == 1
    assert f["status"] == "physically-qualified"
    assert f["qualified"] is True
    assert f["final_stage_h_checkpoint"]["sha"] == "e7e203ba6ef76a0465ff6c25ef9671a46a4ab582"
    assert f["final_stage_i_checkpoint"]["sha"] == "1f87baa05284fe6268e5c8a2b58b66eb93e82c54"
    assert f["final_local_console_gate"]["installed_commit"] == "2f5299e65add072fea6ee55a54dc421faf00c276"
    assert f["final_local_console_gate"]["local_console_blob"] == "9fed5416ca9123811413f4ef284abff0006a48dd"
    assert all(f["appliance_claims"].values())

    local = json.loads(LOCAL.read_text(encoding="utf-8"))
    assert local["qualified_claims"]["local_console_is_physically_qualified"] is True
    assert local["safety"]["rf_transmitted"] is False

    stage_i = json.loads(STAGE_I.read_text(encoding="utf-8"))
    assert stage_i["stage_i_complete"] is True
    assert stage_i["physical_tx"]["tx_dispatches"] == 1
    assert stage_i["physical_tx"]["independent_external_decode_count"] == 1
    assert stage_i["post_tx_rx"]["resumed"] is True

    stage_h = json.loads(STAGE_H.read_text(encoding="utf-8"))
    assert stage_h["qualification_result"] == "pass"

    print("PRODUCT_FRESH_INSTALL_APPLIANCE_QUALIFICATION=PASS")
    print("STAGE_H=PASS")
    print("STAGE_I=PASS")
    print("LOCAL_CONSOLE=PASS")
    print("QUALIFIED=YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
