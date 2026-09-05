#!/usr/bin/env python3
from __future__ import annotations
import hashlib
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
FROZEN={"src/ywd1278/node/mailbox.py":"4e8843887c1c5d242014f4301cc47a93b7b84421","tests/mailbox_storage_0h_p2_test.py":"017e145130260dcc83eed216b2007277ac5087ab","tests/mailbox_storage_0h_p2_contract_test.py":"2da6883cc4c8bf9785dd19c50275ab5cec68aa37","firmware/qualification/0g-p6-connected-target-pi.json":"5050477cf15fbc8638adb3d793ebc9fc9ad63cbe"}
def blob(p):
    d=p.read_bytes(); return hashlib.sha1(f"blob {len(d)}\0".encode()+d).hexdigest()
class ForwardingPolicyP3ContractTests(unittest.TestCase):
    def test_lineage_frozen(self):
        for p,e in FROZEN.items(): self.assertEqual(blob(ROOT/p),e)
    def test_bounded_inert_vocabulary(self):
        t=(ROOT/"src/ywd1278/node/forwarding.py").read_text()
        for m in ("MAX_FORWARD_ROUTES = 32","MAX_FORWARD_HOPS = 8","DELIVER_LOCAL","FORWARD","HOLD","REJECT","exact enabled route selected"): self.assertIn(m,t)
        for bad in ("sqlite","MailboxStore","threading","socket","subprocess","TXModemOwner","sendall(","write("): self.assertNotIn(bad,t)
    def test_runtime_does_not_import_policy(self):
        for p in ("src/ywd1278/daemon.py","src/ywd1278/service/appliance.py","src/ywd1278/node/mailbox.py"): self.assertNotIn("node.forwarding",(ROOT/p).read_text())
if __name__=="__main__": unittest.main(verbosity=2)
