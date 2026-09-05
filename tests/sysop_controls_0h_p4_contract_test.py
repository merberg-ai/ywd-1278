#!/usr/bin/env python3
from __future__ import annotations
import hashlib
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
FROZEN={"src/ywd1278/node/forwarding.py":"e853bf82b841ede234490d4dc509981b5747081e","tests/forwarding_policy_0h_p3_test.py":"2a50e4bd030adc85a75a3caf6317a74443cc55d4","tests/forwarding_policy_0h_p3_contract_test.py":"e2d7b13f2d88684aabd897f9df548f751fcc0e4c","src/ywd1278/node/mailbox.py":"4e8843887c1c5d242014f4301cc47a93b7b84421"}
def blob(p): d=p.read_bytes(); return hashlib.sha1(f"blob {len(d)}\0".encode()+d).hexdigest()
class SysopControlsP4ContractTests(unittest.TestCase):
 def test_lineage_frozen(self):
  for p,e in FROZEN.items(): self.assertEqual(blob(ROOT/p),e)
 def test_auth_and_intents_explicit(self):
  t=(ROOT/"src/ywd1278/node/sysop.py").read_text()
  for m in ("MAX_SYSOP_ATTEMPTS=3","verify_password","DELETE_MESSAGE","ENABLE_ROUTE","DISABLE_ROUTE","inert sysop action prepared"): self.assertIn(m,t)
  for bad in ("MailboxStore","StaticForwardingPolicy","sqlite","socket","threading","subprocess","systemctl","TXModemOwner","os.remove","unlink("): self.assertNotIn(bad,t)
 def test_no_runtime_import(self):
  for p in ("src/ywd1278/daemon.py","src/ywd1278/service/appliance.py","src/ywd1278/node/commands.py"): self.assertNotIn("node.sysop",(ROOT/p).read_text())
if __name__=="__main__": unittest.main(verbosity=2)
