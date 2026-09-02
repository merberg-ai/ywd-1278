from __future__ import annotations

import os
import pathlib
import pty
import select
import sys
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.modem import protocol  # noqa: E402
from ywd1278.modem._serial import (  # noqa: E402
    _PosixSerialTransport,
    posix_serial_transport_factory,
)
from ywd1278.modem.owner import ModemOwner  # noqa: E402


IDENTITY = "MMDVM_HS_Hat-v1.6.1 TEST"


def read_exact(fd: int, count: int, timeout: float = 1.0) -> bytes:
    deadline = time.monotonic() + timeout
    data = bytearray()
    while len(data) < count and time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], 0.05)
        if fd not in ready:
            continue
        chunk = os.read(fd, count - len(data))
        if chunk:
            data.extend(chunk)
    if len(data) != count:
        raise TimeoutError(f"expected {count} PTY bytes, got {len(data)}")
    return bytes(data)


class PosixSerialTransportTests(unittest.TestCase):
    def test_owner_opens_transacts_and_closes_real_posix_tty_in_owner_thread(self) -> None:
        master_fd, anchor_slave_fd = pty.openpty()
        slave_name = os.ttyname(anchor_slave_fd)
        emulator_error: list[BaseException] = []

        def emulator() -> None:
            try:
                request = read_exact(master_fd, 3)
                self.assertEqual(request, protocol.get_version_request())
                response = protocol.build_frame(
                    protocol.GET_VERSION,
                    bytes((1,)) + IDENTITY.encode("ascii") + b"\0",
                )
                os.write(master_fd, response)
            except BaseException as exc:
                emulator_error.append(exc)

        owner = ModemOwner(posix_serial_transport_factory(slave_name))
        peer = threading.Thread(target=emulator, name="pty-modem-emulator")
        try:
            owner.start()
            # Keep the original slave FD open solely to anchor the PTY while
            # the owner opens its own independent slave handle.  This avoids
            # Linux returning EIO on the master during a no-slave-open gap.
            peer.start()
            version = owner.get_version(timeout=1.0)
            self.assertEqual(version.protocol_version, 1)
            self.assertEqual(version.identity, IDENTITY)
            self.assertEqual(owner.snapshot.transactions, 1)
            self.assertIsNotNone(owner.snapshot.owner_thread_id)
            self.assertNotEqual(owner.snapshot.owner_thread_id, threading.get_ident())
        finally:
            owner.stop()
            if peer.ident is not None:
                peer.join(2.0)
            os.close(anchor_slave_fd)
            os.close(master_fd)
        self.assertFalse(peer.is_alive())
        self.assertEqual(emulator_error, [])

    def test_transport_rejects_non_owner_thread_and_malformed_write(self) -> None:
        master_fd, slave_fd = pty.openpty()
        slave_name = os.ttyname(slave_fd)
        transport = _PosixSerialTransport(slave_name)
        try:
            errors: list[BaseException] = []

            def foreign_thread() -> None:
                try:
                    transport.transact(protocol.get_version_request(), timeout=0.1)
                except BaseException as exc:
                    errors.append(exc)

            thread = threading.Thread(target=foreign_thread)
            thread.start()
            thread.join(1.0)
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], RuntimeError)
            self.assertIn("outside its owner thread", str(errors[0]))

            with self.assertRaises(ValueError):
                transport.transact(b"\xE0\x04\x00", timeout=0.1)

            ready, _, _ = select.select([master_fd], [], [], 0.05)
            self.assertNotIn(master_fd, ready)
        finally:
            transport.close()
            os.close(slave_fd)
            os.close(master_fd)


if __name__ == "__main__":
    unittest.main(verbosity=2)
