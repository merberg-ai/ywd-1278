#!/usr/bin/env python3
from __future__ import annotations
import hashlib
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
FROZEN={"src/ywd1278/node/forwarding_integration.py":"263b5583d473a5673e6dfa60978804055197f676","src/ywd1278/node/forwarding.py":"e853bf82b841ede234490d4dc509981b5747081e","firmware/qualification/0h-p7-mailbox-target-pi.json":"365fabbaa6a6dd2bce703cd35c83e96d4dbad3c8"}
def blob(path):
 data=path.read_bytes(); return hashlib.sha1(f"blob {len(data)}\0".encode()+data).hexdigest()
class LinBPQDialogueP9ContractTests(unittest.TestCase):
 def test_frozen_forwarding_and_physical_lineage(self):
  for path,expected in FROZEN.items(): self.assertEqual(blob(ROOT/path),expected,path)
 def test_bounded_inert_classic_bbs_dialogue(self):
  text=(ROOT/"src/ywd1278/node/linbpq_dialogue.py").read_text()
  for marker in ("MAX_REMOTE_BUFFER_BYTES=512","MAX_REMOTE_LINES=64","SP {self._work.destination}","/EX\\r","WAIT_TITLE_PROMPT","WAIT_BODY_PROMPT","WAIT_ACCEPT"):
   self.assertIn(marker,text)
  for forbidden in ("socket","subprocess","threading","systemctl","TXModemOwner","sendall","MailboxStore"):
   self.assertNotIn(forbidden,text)
 def test_no_runtime_wiring(self):
  for path in ("src/ywd1278/daemon.py","src/ywd1278/service/appliance.py"):
   self.assertNotIn("linbpq_dialogue",(ROOT/path).read_text())
if __name__=="__main__": unittest.main(verbosity=2)
