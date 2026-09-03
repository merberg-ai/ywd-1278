from __future__ import annotations

import ast
import inspect
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.kiss.control import (  # noqa: E402
    ControlDisposition,
    TNCControlBackend,
    TNCSessionState,
)
from ywd1278.kiss.framing import DATA, KISSMessage  # noqa: E402
from ywd1278.kiss.server import RXOnlyBackend  # noqa: E402

CONTROL_PATH = ROOT / "src" / "ywd1278" / "kiss" / "control.py"
SERVER_PATH = ROOT / "src" / "ywd1278" / "kiss" / "server.py"


class KISSControlPlaneContractTests(unittest.TestCase):
    def test_control_module_has_no_physical_or_concrete_tx_imports(self) -> None:
        tree = ast.parse(CONTROL_PATH.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        forbidden_prefixes = (
            "serial",
            "ywd1278.modem",
            "ywd1278.phy",
            "ywd1278.tx.broker",
            "ywd1278.tx.half_duplex",
        )
        for module in imported:
            self.assertFalse(
                module.startswith(forbidden_prefixes),
                f"P6 control plane imported forbidden physical/TX module: {module}",
            )

    def test_control_plane_exposes_no_frame_submit_or_transmit_method(self) -> None:
        for cls in (TNCSessionState, TNCControlBackend):
            methods = {
                name
                for name, value in inspect.getmembers(cls)
                if inspect.isfunction(value) or inspect.ismethoddescriptor(value)
            }
            self.assertNotIn("submit_frame", methods)
            self.assertNotIn("transmit", methods)
            self.assertNotIn("transmit_selector_burst", methods)

    def test_data_is_rejected_and_cannot_mutate_parameter_generation(self) -> None:
        state = TNCSessionState()
        before = state.snapshot
        result = state.apply(KISSMessage(port=0, command=DATA, frame=b"frame"))
        self.assertEqual(result.disposition, ControlDisposition.DATA_REJECTED)
        self.assertEqual(state.snapshot, before)
        self.assertEqual(state.counters.kiss_data_tx_rejected, 1)
        self.assertEqual(state.counters.kiss_parameter_updates, 0)

    def test_control_backend_extends_historical_rx_backend_instead_of_replacing_it(self) -> None:
        self.assertTrue(issubclass(TNCControlBackend, RXOnlyBackend))
        backend = TNCControlBackend(history_capacity=0)
        history, queue = backend.open_stream()
        try:
            self.assertEqual(history, [])
        finally:
            backend.close_stream(queue)

    def test_server_change_is_only_optional_malformed_accounting_not_tx_ingress(self) -> None:
        source = SERVER_PATH.read_text(encoding="utf-8")
        self.assertIn('"note_malformed_stream_frames"', source)
        self.assertNotIn("submit_frame(", source)
        self.assertNotIn("TXModemOwner", source)
        self.assertNotIn("TXBroker", source)
        self.assertNotIn("transmit_selector_burst", source)

    def test_port_zero_and_data_disconnection_are_literal_policy_guards(self) -> None:
        source = CONTROL_PATH.read_text(encoding="utf-8")
        self.assertIn("KISS_PORT = 0", source)
        self.assertIn("message.port != KISS_PORT", source)
        self.assertIn("message.command == DATA", source)
        self.assertIn("KISS DATA transmit ingress remains disconnected in 0C-P6", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
