#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from ywd1278.install.firmware_trust import (
    FirmwareTrustError,
    load_product_firmware_profile,
    verify_artifact,
    verify_programmed_readback,
    verify_service_eligibility,
    verify_stock_backup,
    write_service_eligibility,
)
from ywd1278.service.appliance import PRODUCT_TARGET


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_PROFILE = ROOT / "firmware/product-ax25r4.json"
EXPECTED_AX25R4_SHA = "b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616"
EXPECTED_STOCK_SHA = "4981b35b2d50ada0b09322d9de19dd58a0cbd49eb005693499d1acae92f9d684"
EXPECTED_IDENTITY = (
    "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 "
    "14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed"
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ready_config() -> str:
    return f'''[station]
callsign = "KJ6YWD"
ssid = 0

[hardware]
target = "{PRODUCT_TARGET}"

[radio]
device = "/dev/ttyAMA0"
frequency_mhz = 145.050
tx_power = 64
tx_enabled = false

[packet]
baud = 1200
txdelay_ms = 300
persist = 63
slottime_ms = 100
paclen = 128
maxframe = 4
retry = 10

[kiss]
enabled = true
listen = "127.0.0.1"
port = 8001

[console]
enabled = true
listen = "127.0.0.1"
port = 8010
pty_enabled = true
pty_link = "/run/ywd-1278/tnc"

[monitor]
enabled = true
log_frames = true

[storage]
database = "/var/lib/ywd-1278/ywd-1278.sqlite3"

[beacon]
enabled = false

[firmware]
required_product = "YWD-1278"
allow_automatic_flash = false
'''


class FirmwareTrustStageFTests(unittest.TestCase):
    def test_production_profile_is_exact_ax25r4_anchor(self) -> None:
        profile = load_product_firmware_profile(PRODUCT_PROFILE)
        self.assertEqual(profile.target_id, PRODUCT_TARGET)
        self.assertEqual(profile.expected_identity, EXPECTED_IDENTITY)
        self.assertEqual(profile.artifact_size_bytes, 59892)
        self.assertEqual(profile.artifact_sha256, EXPECTED_AX25R4_SHA)
        self.assertEqual(profile.programmed_readback_bytes, 59892)
        self.assertEqual(profile.programmed_readback_sha256, EXPECTED_AX25R4_SHA)
        self.assertEqual(profile.stock_flash_size_bytes, 131072)
        self.assertEqual(profile.stock_flash_sha256, EXPECTED_STOCK_SHA)
        self.assertEqual(profile.expected_bootloader_version, "0x22")
        self.assertEqual(profile.expected_device_id, "0x0410")
        self.assertEqual(profile.flash_authorization_token, "FLASH-QUALIFIED-AX25R4")
        self.assertEqual(profile.service_eligibility_record, "/var/lib/ywd-1278/firmware-ready.json")

    def _synthetic_profile(self, td: str, artifact: bytes, stock: bytes) -> Path:
        p = Path(td) / "profile.json"
        obj = json.loads(PRODUCT_PROFILE.read_text(encoding="utf-8"))
        obj["artifact_size_bytes"] = len(artifact)
        obj["artifact_sha256"] = sha(artifact)
        obj["programmed_readback_bytes"] = len(artifact)
        obj["programmed_readback_sha256"] = sha(artifact)
        obj["stock_flash_size_bytes"] = len(stock)
        obj["stock_flash_sha256"] = sha(stock)
        obj["service_eligibility_record"] = str(Path(td) / "firmware-ready.json")
        p.write_text(json.dumps(obj), encoding="utf-8")
        return p

    def _stock_backup(self, td: str, profile, stock: bytes) -> Path:  # type: ignore[no-untyped-def]
        directory = Path(td) / "stock-backup"
        directory.mkdir()
        image = directory / "original-flash.bin"
        image.write_bytes(stock)
        manifest = {
            "schema": 2,
            "target_id": profile.target_id,
            "captured_identity": "synthetic-stock",
            "flash_base": "0x08000000",
            "flash_size_bytes": len(stock),
            "sha256": sha(stock),
            "read_passes": 2,
            "two_pass_byte_identical": True,
            "stock_sha256_match": True,
            "option_bytes_read_or_written": False,
            "flash_written": False,
        }
        (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return directory

    def test_artifact_backup_readback_and_eligibility_chain(self) -> None:
        artifact = b"qualified-ax25r4-test-artifact"
        stock = b"verified-stock-full-flash"
        with tempfile.TemporaryDirectory() as td:
            profile_path = self._synthetic_profile(td, artifact, stock)
            profile = load_product_firmware_profile(profile_path)
            artifact_path = Path(td) / "ax25r4.bin"
            artifact_path.write_bytes(artifact)
            readback = Path(td) / "readback.bin"
            readback.write_bytes(artifact)
            backup = self._stock_backup(td, profile, stock)
            config = Path(td) / "config.toml"
            config.write_text(ready_config(), encoding="utf-8")
            record = Path(td) / "firmware-ready.json"

            self.assertEqual(verify_artifact(profile, artifact_path), sha(artifact))
            self.assertEqual(verify_stock_backup(profile, backup), sha(stock))
            self.assertEqual(verify_programmed_readback(profile, readback), sha(artifact))

            written = write_service_eligibility(
                profile=profile,
                config=config,
                firmware=artifact_path,
                readback_sha256=sha(artifact),
                runtime_identity=profile.expected_identity,
                stock_backup_dir=backup,
                output=record,
            )
            self.assertEqual(written["status"], "SERVICE-ELIGIBLE")
            self.assertFalse(written["tx_enabled"])
            self.assertFalse(written["automatic_flash_enabled"])
            self.assertFalse(written["option_bytes_written"])
            self.assertFalse(written["service_enabled_by_stage_f"])
            checked = verify_service_eligibility(
                profile=profile,
                config=config,
                firmware=artifact_path,
                record_path=record,
            )
            self.assertEqual(checked["programmed_readback_sha256"], sha(artifact))

    def test_tampered_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            profile_path = self._synthetic_profile(td, b"good", b"stock")
            profile = load_product_firmware_profile(profile_path)
            artifact = Path(td) / "artifact.bin"
            artifact.write_bytes(b"evil")
            with self.assertRaises(FirmwareTrustError):
                verify_artifact(profile, artifact)

    def test_one_pass_or_tampered_stock_backup_is_rejected(self) -> None:
        stock = b"stock"
        with tempfile.TemporaryDirectory() as td:
            profile_path = self._synthetic_profile(td, b"fw", stock)
            profile = load_product_firmware_profile(profile_path)
            backup = self._stock_backup(td, profile, stock)
            meta_path = backup / "manifest.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["read_passes"] = 1
            meta_path.write_text(json.dumps(meta), encoding="utf-8")
            with self.assertRaises(FirmwareTrustError):
                verify_stock_backup(profile, backup)

    def test_wrong_readback_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            profile_path = self._synthetic_profile(td, b"firmware", b"stock")
            profile = load_product_firmware_profile(profile_path)
            readback = Path(td) / "readback.bin"
            readback.write_bytes(b"firmwarX")
            with self.assertRaises(FirmwareTrustError):
                verify_programmed_readback(profile, readback)

    def test_eligibility_requires_ready_no_tx_config_and_exact_identity(self) -> None:
        artifact = b"fw"
        stock = b"stock"
        with tempfile.TemporaryDirectory() as td:
            profile_path = self._synthetic_profile(td, artifact, stock)
            profile = load_product_firmware_profile(profile_path)
            artifact_path = Path(td) / "artifact.bin"
            artifact_path.write_bytes(artifact)
            backup = self._stock_backup(td, profile, stock)
            config = Path(td) / "config.toml"
            config.write_text(ready_config().replace("tx_enabled = false", "tx_enabled = true"), encoding="utf-8")
            with self.assertRaises(FirmwareTrustError):
                write_service_eligibility(
                    profile=profile,
                    config=config,
                    firmware=artifact_path,
                    readback_sha256=sha(artifact),
                    runtime_identity=profile.expected_identity,
                    stock_backup_dir=backup,
                    output=Path(td) / "record.json",
                )

            config.write_text(ready_config(), encoding="utf-8")
            with self.assertRaises(FirmwareTrustError):
                write_service_eligibility(
                    profile=profile,
                    config=config,
                    firmware=artifact_path,
                    readback_sha256=sha(artifact),
                    runtime_identity="wrong identity",
                    stock_backup_dir=backup,
                    output=Path(td) / "record.json",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
