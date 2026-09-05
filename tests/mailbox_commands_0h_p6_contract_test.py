#!/usr/bin/env python3
from __future__ import annotations
import hashlib
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
FROZEN={"src/ywd1278/node/mailbox.py":"4e8843887c1c5d242014f4301cc47a93b7b84421","src/ywd1278/node/commands.py":"85c02074e403f208af9fc9bd56e3f70f29af4c07","tools/qualify_0h_p5_inbound_node.py":"6e0a331344493cb7255c83144b10d39ba1851993"}
def blob(path):
 data=path.read_bytes(); return hashlib.sha1(f"blob {len(data)}\0".encode()+data).hexdigest()
class MailboxCommandsP6ContractTests(unittest.TestCase):
 def test_frozen_capabilities_and_physical_harness(self):
  for path,expected in FROZEN.items(): self.assertEqual(blob(ROOT/path),expected,path)
 def test_bounded_peer_owned_command_surface(self):
  text=(ROOT/"src/ywd1278/node/mailbox_commands.py").read_text()
  for marker in ("READ_WINDOW_BYTES = 512","RESPONSE_CHUNK_BYTES = 96","MAX_LIST_RESULTS = 12","sender=self._peer","read_for(self._peer","list_for(self._peer","clock_ns"):
   self.assertIn(marker,text)
  for forbidden in ("socket","subprocess","threading","systemctl","TXModemOwner","time.time","time_ns"):
   self.assertNotIn(forbidden,text)
 def test_integration_remains_inert_and_not_runtime_wired(self):
  inbound=(ROOT/"src/ywd1278/node/inbound.py").read_text()
  self.assertIn("session_factory",inbound); self.assertIn("_fail_closed",inbound)
  for path in ("src/ywd1278/daemon.py","src/ywd1278/service/appliance.py"):
   self.assertNotIn("mailbox_commands",(ROOT/path).read_text())
if __name__=="__main__": unittest.main(verbosity=2)
