#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0f-p9-persistent-product-converse-target-pi.json"

FROZEN_P9_BLOBS = {
    "src/ywd1278/install/tx_control.py": "1595643c4b5bd2f94ffdd70e5a85c2e57b7fa3ab",
    "installer/product-tx-control.sh": "b162b62ce1b4fc605f3c66a3b61b9459e115069a",
    "installer/update-installed-software.sh": "bd64057c41a37decc558bc303026f6d60f2e1136",
    "docs/qualifications/0f-p9-persistent-product-converse-live-staging.md": "724fe4c0a5f4f0a6f4ff3ae01fa46dc5c4bb0e96",
}


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def main() -> int:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert evidence["schema"] == 1
    assert evidence["stage"] == "0F-P9"
    assert evidence["status"] == "target-pi-persistent-product-converse-qualified"
    assert evidence["qualified_on"] == "2026-09-06"
    assert evidence["tested_source"] == {
        "branch": "dev-0f-p9-persistent-product-converse",
        "commit": "130f76ffbdf4e77b398e33d63814be3c965dce6e",
    }

    install = evidence["installation_boundary"]
    assert install["normal_installed_source"] is True
    assert install["normal_systemd_service"] == "ywd-1278.service"
    assert install["persistent_tx_authority_used"] is True
    assert install["temporary_qualification_daemon_used"] is False
    assert install["operator_reported_full_staging_sequence_success"] is True

    rf = evidence["rf_profile"]
    assert rf == {
        "frequency_hz": 145050000,
        "tx_power": 200,
        "source": "KJ6YWD-10",
    }

    paths = evidence["qualified_unproto_paths"]
    assert len(paths) == 2
    assert paths[0]["destination"] == "JIM"
    assert paths[0]["path"] == ["YWDNOD"]
    assert paths[0]["operator_result"] == "PASS"
    assert "KJ6YWD-10>JIM,YWDNOD:hello test 123" in paths[0]["observed_source_frames"]

    assert paths[1]["destination"] == "JIM"
    assert paths[1]["path"] == ["YWDNOD", "KRDG"]
    assert paths[1]["operator_result"] == "PASS"
    assert "KJ6YWD-10>JIM,YWDNOD,KRDG:hello test" in paths[1]["observed_source_frames"]
    assert "KJ6YWD-10>JIM,YWDNOD*,KRDG*:hello test" in paths[1]["observed_repeated_frames"]

    behavior = evidence["qualified_behavior"]
    assert behavior["normal_service_product_converse_tx"] is True
    assert behavior["unproto_destination_applied"] is True
    assert behavior["single_digipeater_path_applied"] is True
    assert behavior["two_digipeater_path_applied"] is True
    assert behavior["independent_over_air_decode"] is True
    assert behavior["returned_digipeated_copy_observed"] is True
    assert behavior["operator_reported_expected_behavior"] is True

    safety = evidence["safety_and_architecture"]
    assert safety["existing_p8_product_converse_backend_used"] is True
    assert safety["new_modem_path_introduced"] is False
    assert safety["new_scheduler_introduced"] is False
    assert safety["new_automatic_tx_retry_introduced"] is False
    assert safety["firmware_write_required_for_p9"] is False
    assert safety["option_byte_write_required_for_p9"] is False
    assert safety["persistent_tx_disable_cleanup_required_by_staging"] is True
    assert safety["operator_reported_full_cleanup_sequence_success"] is True

    for relative, expected in FROZEN_P9_BLOBS.items():
        actual = git_blob_sha(ROOT / relative)
        assert actual == expected, f"P9 blob changed: {relative} actual={actual} expected={expected}"

    print("YWD1278_0F_P9_PERSISTENT_PRODUCT_CONVERSE_PHYSICAL_EVIDENCE=PASS")
    print("TESTED_SOURCE_COMMIT=130f76ffbdf4e77b398e33d63814be3c965dce6e")
    print("NORMAL_SYSTEMD_SERVICE=PASS")
    print("PERSISTENT_TX_AUTHORITY=PASS")
    print("UNPROTO_JIM_VIA_YWDNOD=PASS")
    print("UNPROTO_JIM_VIA_YWDNOD_KRDG=PASS")
    print("RETURNED_YWDNOD_KRDG_DIGI_COPY=PASS")
    print("AUTOMATIC_TX_RETRY_INTRODUCED=NO")
    print("FIRMWARE_WRITE_REQUIRED=NO")
    print("OPTION_BYTE_WRITE_REQUIRED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
