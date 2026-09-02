#!/usr/bin/env python3

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.ax25.codec import Address, build_ui_frame  # noqa: E402
from ywd1278.modem.protocol import (  # noqa: E402
    ACK,
    CTRL_PING,
    GET_VERSION,
    RF_GET_DIAG,
    RF_GET_STATUS,
    RF_TX_TONES,
    RX_READ,
    RX_START,
    RX_STATUS,
    START,
    YWD_CONTROL,
    YWD_RF,
    YWD_RX,
    ack_for,
    control_request,
    get_version_request,
    parse_ack,
    parse_frame,
    parse_nak,
    parse_rf_diagnostics,
    parse_rf_status,
    parse_rx3_status,
    parse_rx_read,
    parse_version_response,
    rf_diag_request,
    rf_status_request,
    rf_tx_tones_request,
    rx_read_request,
    rx_start_request,
    rx_status_request,
)
from ywd1278.phy.bell202_tx import frame_to_selectors, pack_selectors  # noqa: E402


class ModemProtocolTests(unittest.TestCase):
    def test_qualified_request_opcodes_are_bit_exact(self):
        self.assertEqual(get_version_request(), bytes.fromhex("e0 03 00"))
        self.assertEqual(control_request(CTRL_PING), bytes.fromhex("e0 04 56 01"))
        self.assertEqual(rf_status_request(), bytes.fromhex("e0 04 58 01"))
        self.assertEqual(rf_diag_request(), bytes.fromhex("e0 04 58 05"))
        self.assertEqual(rx_start_request(), bytes.fromhex("e0 04 59 01"))
        self.assertEqual(rx_status_request(), bytes.fromhex("e0 04 59 04"))
        self.assertEqual(rx_read_request(200), bytes.fromhex("e0 05 59 02 c8"))

    def test_ack_and_nak_parsing(self):
        self.assertEqual(ack_for(YWD_RX), bytes.fromhex("e0 04 70 59"))
        parse_ack(bytes.fromhex("e0 04 70 59"), expected_command=YWD_RX)
        nak = parse_nak(bytes.fromhex("e0 05 7f 58 05"))
        self.assertEqual((nak.command, nak.error), (YWD_RF, 5))
        with self.assertRaises(ValueError):
            parse_ack(bytes.fromhex("e0 04 70 58"), expected_command=YWD_RX)

    def test_version_response(self):
        identity = (
            b"MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0 "
            b"14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed"
        )
        response = bytes((START, 4 + len(identity), GET_VERSION, 1)) + identity
        parsed = parse_version_response(response)
        self.assertEqual(parsed.protocol_version, 1)
        self.assertEqual(parsed.identity, identity.decode("ascii"))

    def test_rf_status_and_diag_match_qualified_layout(self):
        status = parse_rf_status(bytes.fromhex("e0 09 58 01 01 08 00 00 00"))
        self.assertEqual((status.flags, status.remaining_selectors, status.mode), (0x08, 0, 0))

        diag = parse_rf_diagnostics(bytes.fromhex("e0 0a 58 05 34 12 01 30 2b 00"))
        self.assertEqual(diag.interrupt_count, 0x1234)
        self.assertEqual(diag.keyups, 1)
        self.assertEqual(diag.generated_samples, 0x2B30)
        self.assertEqual(diag.tx_active, 0)

    def test_rx3_status_and_read_match_qualified_layout(self):
        # protocol revision 3, active+armed+AX25 flags 0x0d, 120 bytes ready,
        # 192061 generated slicer samples and zero dropped packed bytes.
        response = bytes.fromhex("e0 0e 59 04 03 0d 78 00 3d ee 02 00 00 00")
        status = parse_rx3_status(response)
        self.assertEqual(status.flags, 0x0D)
        self.assertEqual(status.available_bytes, 120)
        self.assertEqual(status.samples, 192061)
        self.assertEqual(status.dropped_bytes, 0)

        payload = bytes((0xA5, 0xC0, 0xDB, 0x5A))
        read_response = bytes((START, 5 + len(payload), YWD_RX, RX_READ, len(payload))) + payload
        self.assertEqual(parse_rx_read(read_response), payload)

    def test_rx3_wrong_revision_is_rejected(self):
        response = bytes.fromhex("e0 0e 59 04 02 0d 00 00 00 00 00 00 00 00")
        with self.assertRaises(ValueError):
            parse_rx3_status(response)

    def test_physical_ax25_5b_tx_request_representation(self):
        frame = build_ui_frame(
            source=Address.parse("KJ6YWD-10"),
            destination=Address.parse("APYWD1"),
            info=b"AX25-5B KISS TX TEST",
            include_fcs=True,
        )
        selectors = frame_to_selectors(frame, pre_flags=45, post_flags=3)
        self.assertEqual(len(selectors), 691)
        packed = pack_selectors(selectors)
        request = rf_tx_tones_request(
            selector_count=len(selectors),
            packed_selectors=packed,
        )
        parsed = parse_frame(request, expected_command=YWD_RF)
        self.assertEqual(request[0], START)
        self.assertEqual(request[1], len(request))
        self.assertEqual(len(request), 93)
        self.assertEqual(parsed.payload[0], RF_TX_TONES)
        self.assertEqual(parsed.payload[1] | (parsed.payload[2] << 8), 691)
        self.assertEqual(parsed.payload[3:], packed)

    def test_malformed_frames_fail_closed(self):
        for malformed in (
            b"",
            bytes.fromhex("e0 02"),
            bytes.fromhex("00 03 00"),
            bytes.fromhex("e0 04 00"),
            bytes.fromhex("e0 03 00 ff"),
        ):
            with self.subTest(malformed=malformed.hex()):
                with self.assertRaises(ValueError):
                    parse_frame(malformed)

        with self.assertRaises(ValueError):
            rx_read_request(0)
        with self.assertRaises(ValueError):
            rx_read_request(201)
        with self.assertRaises(ValueError):
            rf_tx_tones_request(selector_count=8, packed_selectors=b"")


if __name__ == "__main__":
    unittest.main(verbosity=2)
