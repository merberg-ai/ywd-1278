#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.ax25 import Address, build_ui_frame, encode_address  # noqa: E402
from ywd1278.kiss.server import PacketEvent, RXOnlyBackend  # noqa: E402
from ywd1278.monitor import (  # noqa: E402
    DecodedMonitorStream,
    MonitorPolicyState,
    MonitorViewContext,
)


def record_for(body: bytes):
    backend = RXOnlyBackend([PacketEvent(body)])
    with DecodedMonitorStream(backend, clock_ns=lambda: 1).open() as monitor:
        return monitor.get(timeout=0.1)


def ui_record(*, path: bool = False):
    return record_for(
        build_ui_frame(
            source=Address.parse("KJ6YWD"),
            destination=Address.parse("JIM"),
            path=(
                [Address.parse("KRDG", flag=True), Address.parse("KBANN")]
                if path
                else []
            ),
            info=b"hello",
            include_fcs=False,
        )
    )


def rr_record():
    body = bytearray()
    body.extend(encode_address(Address.parse("NODE"), last=False))
    body.extend(encode_address(Address.parse("N0CALL-2"), last=True))
    body.append(0x61)  # modulo-8 RR, N(R)=3, P/F=0
    return record_for(bytes(body))


def i_record():
    # Previously captured physical AX25R3 I frame, FCS removed.
    return record_for(
        bytes.fromhex(
            "a4 88 8e 40 40 40 e0 "
            "96 94 6c b2 ae 88 63 "
            "20 f0 6e 0d"
        )
    )


class MonitorPolicyTests(unittest.TestCase):
    def test_classic_defaults(self) -> None:
        snap = MonitorPolicyState().snapshot
        self.assertEqual(snap.generation, 0)
        self.assertFalse(snap.mcom)
        self.assertFalse(snap.mcon)
        self.assertTrue(snap.mrpt)

    def test_mcom_off_hides_protocol_control_but_not_information(self) -> None:
        state = MonitorPolicyState()
        rr = state.apply(rr_record())
        ui = state.apply(ui_record())
        info = state.apply(i_record())
        self.assertFalse(rr.visible)
        self.assertEqual(rr.suppression_reason, "MCOM")
        self.assertTrue(ui.visible)
        self.assertTrue(info.visible)

        state.set_mcom(True)
        shown = state.apply(rr_record())
        self.assertTrue(shown.visible)
        self.assertEqual(shown.line, "N0CALL-2>NODE:[RR nr=3 pf=0]")

    def test_mcon_off_while_connected_keeps_only_local_addressed_eligible_frames(self) -> None:
        record = ui_record()
        state = MonitorPolicyState()

        third_party = state.apply(
            record,
            context=MonitorViewContext(local_connected=True, addressed_to_local=False),
        )
        self.assertFalse(third_party.visible)
        self.assertEqual(third_party.suppression_reason, "MCON")

        local = state.apply(
            record,
            context=MonitorViewContext(local_connected=True, addressed_to_local=True),
        )
        self.assertTrue(local.visible)

        state.set_mcon(True)
        all_eligible = state.apply(
            record,
            context=MonitorViewContext(local_connected=True, addressed_to_local=False),
        )
        self.assertTrue(all_eligible.visible)

    def test_mcon_has_no_effect_when_not_connected(self) -> None:
        state = MonitorPolicyState(mcon=False)
        self.assertTrue(state.apply(ui_record()).visible)

    def test_mrpt_changes_view_only_and_preserves_structured_path(self) -> None:
        record = ui_record(path=True)
        self.assertEqual(record.path, ("KRDG*", "KBANN"))
        self.assertEqual(record.line, "KJ6YWD>JIM,KRDG*,KBANN:hello")

        state = MonitorPolicyState(mrpt=False)
        hidden = state.apply(record)
        self.assertTrue(hidden.visible)
        self.assertEqual(hidden.line, "KJ6YWD>JIM:hello")
        self.assertEqual(record.path, ("KRDG*", "KBANN"))
        self.assertEqual(record.line, "KJ6YWD>JIM,KRDG*,KBANN:hello")

        state.set_mrpt(True)
        shown = state.apply(record)
        self.assertEqual(shown.line, "KJ6YWD>JIM,KRDG*,KBANN:hello")

    def test_atomic_generation_changes_once_per_effective_update(self) -> None:
        state = MonitorPolicyState()
        one = state.update(mcom=True, mcon=True, mrpt=False)
        self.assertEqual(one.generation, 1)
        self.assertEqual((one.mcom, one.mcon, one.mrpt), (True, True, False))
        same = state.update(mcom=True, mcon=True, mrpt=False)
        self.assertEqual(same.generation, 1)
        two = state.set_mrpt(True)
        self.assertEqual(two.generation, 2)

    def test_invalid_values_fail_closed(self) -> None:
        state = MonitorPolicyState()
        for method in (state.set_mcom, state.set_mcon, state.set_mrpt):
            with self.assertRaises(TypeError):
                method(1)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            MonitorPolicyState(mcom="ON")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            MonitorViewContext(local_connected=False, addressed_to_local=True)

    def test_policy_has_no_tx_surface(self) -> None:
        state = MonitorPolicyState()
        for name in ("publish", "transmit", "send", "connect", "disconnect"):
            self.assertFalse(hasattr(state, name), name)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(MonitorPolicyTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("YWD1278_0D_P2_MONITOR_POLICY=PASS")
    print("MCOM_DEFAULT=OFF")
    print("MCON_DEFAULT=OFF")
    print("MRPT_DEFAULT=ON")
    print("MCOM_CONTROL_FRAME_GATE=PASS")
    print("MCON_CONNECTED_CONTEXT_GATE=PASS")
    print("MRPT_PRESENTATION_ONLY=PASS")
    print("POLICY_GENERATION_ATOMIC=PASS")
    print("MONITOR_TX_CAPABILITY=ABSENT")
