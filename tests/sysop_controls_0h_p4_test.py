#!/usr/bin/env python3
from __future__ import annotations
import unittest
from ywd1278.console.auth import CredentialRecord,hash_password
from ywd1278.node.sysop import SysopActionType,SysopCommandGate

def gate(): return SysopCommandGate(CredentialRecord("sysop",hash_password("correct horse",salt=b"0"*16,iterations=200000)))
class SysopControlsP4Tests(unittest.TestCase):
    def test_auth_required_and_valid_password_opens_gate(self):
        g=gate(); self.assertFalse(g.prepare("STATUS").accepted); self.assertTrue(g.authenticate("sysop","correct horse").accepted); self.assertTrue(g.snapshot.authenticated)
    def test_three_failures_lock_even_after_correct_password(self):
        g=gate()
        for _ in range(3): self.assertFalse(g.authenticate("sysop","wrong passphrase").accepted)
        self.assertTrue(g.snapshot.locked); self.assertFalse(g.authenticate("sysop","correct horse").accepted)
    def test_callsign_or_wrong_username_grants_nothing(self):
        g=gate(); self.assertFalse(g.authenticate("KJ6YWD-5","correct horse").accepted); self.assertFalse(g.snapshot.authenticated)
    def test_actions_are_typed_inert_and_bounded(self):
        g=gate(); g.authenticate("sysop","correct horse")
        cases=(("STATUS",SysopActionType.STATUS),("MESSAGE DELETE 42",SysopActionType.DELETE_MESSAGE),("ROUTE ENABLE N0CALL",SysopActionType.ENABLE_ROUTE),("ROUTE DISABLE N0CALL-1",SysopActionType.DISABLE_ROUTE))
        for line,kind in cases: self.assertEqual(g.prepare(line).action.action,kind)
        self.assertEqual(g.snapshot.actions_prepared,4)
        for bad in ("MESSAGE DELETE 0","MESSAGE READ 1","ROUTE ADD N0CALL","SHELL","SHUTDOWN","x"*129): self.assertFalse(g.prepare(bad).accepted)
    def test_logout_revokes_authority(self):
        g=gate(); g.authenticate("sysop","correct horse"); g.logout(); self.assertFalse(g.prepare("STATUS").accepted)
if __name__=="__main__": unittest.main(verbosity=2)
