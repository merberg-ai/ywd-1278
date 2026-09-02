from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.kiss.framing import (  # noqa: E402
    DATA,
    FEND,
    FESC,
    TFEND,
    TFESC,
    KISSStreamDecoder,
    decode,
    encode,
)


class KISSFramingTests(unittest.TestCase):
    def test_standard_escape_round_trip(self) -> None:
        frame = bytes((0x01, FEND, 0x02, FESC, 0x03))
        packet = encode(frame, port=3, command=DATA)
        self.assertEqual(
            packet,
            bytes((FEND, 0x30, 0x01, FESC, TFEND, 0x02, FESC, TFESC, 0x03, FEND)),
        )
        message = decode(packet)
        self.assertEqual((message.port, message.command, message.frame), (3, DATA, frame))

    def test_stream_decoder_preserves_chunk_boundaries_and_separators(self) -> None:
        first = encode(b"abc")
        second = encode(bytes((FEND, FESC)), port=1)
        stream = bytes((FEND, FEND)) + first + bytes((FEND,)) + second + bytes((FEND,))

        decoder = KISSStreamDecoder()
        messages = []
        for index in range(0, len(stream), 2):
            messages.extend(decoder.feed(stream[index : index + 2]))

        self.assertEqual(len(messages), 2)
        self.assertEqual((messages[0].port, messages[0].command, messages[0].frame), (0, DATA, b"abc"))
        self.assertEqual((messages[1].port, messages[1].command, messages[1].frame), (1, DATA, bytes((FEND, FESC))))

    def test_invalid_escape_discards_only_current_frame_and_resynchronizes(self) -> None:
        decoder = KISSStreamDecoder()
        bad_then_good = bytes((FEND, 0x00, FESC, 0x00, 0x11, FEND)) + encode(b"good")
        messages = decoder.feed(bad_then_good)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].frame, b"good")
        self.assertEqual(decoder.discarded_frames, 1)

    def test_oversize_unterminated_peer_is_bounded_and_recovers(self) -> None:
        decoder = KISSStreamDecoder(max_body_bytes=4)
        self.assertEqual(decoder.feed(bytes((FEND, 0x00)) + b"123456789"), [])
        self.assertEqual(decoder.discarded_frames, 1)
        messages = decoder.feed(bytes((FEND,)) + encode(b"ok"))
        self.assertEqual([message.frame for message in messages], [b"ok"])

    def test_malformed_packets_fail_closed(self) -> None:
        malformed = (
            b"",
            bytes((FEND, FEND)),
            bytes((0x00, 0x00, FEND)),
            bytes((FEND, 0x00, FESC, 0x00, FEND)),
            bytes((FEND, 0x00, FESC, FEND)),
        )
        for packet in malformed:
            with self.subTest(packet=packet.hex()):
                with self.assertRaises(ValueError):
                    decode(packet)

        with self.assertRaises(ValueError):
            encode(b"x", port=16)
        with self.assertRaises(ValueError):
            encode(b"x", command=16)
        with self.assertRaises(ValueError):
            KISSStreamDecoder(max_body_bytes=0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
