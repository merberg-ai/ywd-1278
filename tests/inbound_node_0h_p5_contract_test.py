#!/usr/bin/env python3
from __future__ import annotations
import hashlib
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
FROZEN={"src/ywd1278/node/commands.py":"85c02074e403f208af9fc9bd56e3f70f29af4c07","src/ywd1278/link/timed_link.py":"229b93ccc9ae2745ca1aae48685ced8712f5d433"}
def blob(p):
 d=p.read_bytes(); return hashlib.sha1(f"blob {len(d)}\0".encode()+d).hexdigest()
class InboundNodeP5ContractTests(unittest.TestCase):
 def test_frozen_dependencies(self):
  for p,e in FROZEN.items(): self.assertEqual(blob(ROOT/p),e,p)
 def test_coordinator_is_bounded_and_inert(self):
  t=(ROOT/"src/ywd1278/node/inbound.py").read_text()
  for marker in ("MAX_PENDING_RESPONSES = 16","MAX_PENDING_RESPONSE_BYTES = 2048","InboundNodeSession","orderly_release_started"):
   self.assertIn(marker,t)
  for forbidden in ("socket","subprocess","threading","systemctl","TXModemOwner","sendall","sqlite"):
   self.assertNotIn(forbidden,t)
 def test_guarded_harness_contract(self):
  t=(ROOT/"tools/qualify_0h_p5_inbound_node.py").read_text()
  for marker in ("0H-P5-INBOUND-NODE-145050-KJ6YWD5-ONE","TRANSMIT-0H-P5-INBOUND-NODE-KJ6YWD-5-ONE","KJ6YWD-10","KJ6YWD-5","BYE_ACK_BEFORE_DISC=PASS","_restore_service"):
   self.assertIn(marker,t)
 def test_no_default_runtime_wiring(self):
  for p in ("src/ywd1278/daemon.py","src/ywd1278/service/appliance.py"):
   self.assertNotIn("node.inbound",(ROOT/p).read_text())
if __name__=="__main__": unittest.main(verbosity=2)
