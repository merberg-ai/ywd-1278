#!/usr/bin/env python3
from __future__ import annotations
import hashlib
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
FROZEN={"src/ywd1278/node/forwarding.py":"e853bf82b841ede234490d4dc509981b5747081e","src/ywd1278/node/mailbox.py":"4e8843887c1c5d242014f4301cc47a93b7b84421","tools/qualify_0h_p7_mailbox.py":"b9ba6c07a210a946e5988cb051b5a7c6f6ca9635","firmware/qualification/0h-p7-mailbox-target-pi.json":"365fabbaa6a6dd2bce703cd35c83e96d4dbad3c8"}
def blob(path):
 data=path.read_bytes(); return hashlib.sha1(f"blob {len(data)}\0".encode()+data).hexdigest()
class ForwardingIntegrationP8ContractTests(unittest.TestCase):
 def test_frozen_policy_storage_and_physical_evidence(self):
  for path,expected in FROZEN.items(): self.assertEqual(blob(ROOT/path),expected,path)
 def test_planner_is_bounded_inert_and_owner_checked(self):
  text=(ROOT/"src/ywd1278/node/forwarding_integration.py").read_text()
  for marker in ("MAX_FORWARD_BATCH = 8","FORWARD_BODY_CHUNK_BYTES = 128","read_for(destination,envelope.message_id)","PreparedForwardMessage","ForwardDisposition.HOLD"):
   self.assertIn(marker,text)
  for forbidden in ("socket","subprocess","threading","systemctl","TXModemOwner","sendall","delete","UPDATE ","DELETE "):
   self.assertNotIn(forbidden,text)
 def test_no_runtime_or_command_wiring(self):
  for path in ("src/ywd1278/daemon.py","src/ywd1278/service/appliance.py","src/ywd1278/node/mailbox_commands.py"):
   self.assertNotIn("forwarding_integration",(ROOT/path).read_text())
if __name__=="__main__": unittest.main(verbosity=2)
