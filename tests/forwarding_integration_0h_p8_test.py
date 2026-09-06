#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import tempfile,unittest
from ywd1278.ax25 import Address
from ywd1278.node.forwarding import ForwardDisposition,ForwardEnvelope,ForwardRoute,StaticForwardingPolicy
from ywd1278.node.forwarding_integration import MailboxForwardingPlanner
from ywd1278.node.mailbox import MailboxStore
NODE=Address.parse("KJ6YWD-10"); LOCAL=Address.parse("KJ6YWD-15"); DEST=Address.parse("KJ6YWD-1"); HOP=Address.parse("KJ6YWD-5"); SENDER=Address.parse("N0CALL")
class ForwardingIntegrationP8Tests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(); self.store=MailboxStore(Path(self.temp.name)/"mail.sqlite3")
  self.policy=StaticForwardingPolicy(node=NODE,local_destinations=(NODE,LOCAL),routes=(ForwardRoute(DEST,HOP),))
  self.planner=MailboxForwardingPlanner(store=self.store,policy=self.policy)
 def tearDown(self): self.temp.cleanup()
 def deposit(self,recipient=DEST,body=b"body"):
  return self.store.deposit(sender=SENDER,recipient=recipient,subject="Subject",body=body,created_at_ns=1)
 def test_exact_route_prepares_immutable_chunked_work(self):
  msg=self.deposit(body=b"X"*300); result=self.planner.prepare(ForwardEnvelope(msg.message_id,DEST))
  self.assertEqual(result.decision.disposition,ForwardDisposition.FORWARD); self.assertIsNotNone(result.message)
  work=result.message; assert work is not None
  self.assertEqual((work.sender,work.destination,work.next_hop),(SENDER,DEST,HOP))
  self.assertEqual(work.subject,"Subject"); self.assertEqual([len(x) for x in work.body_chunks],[128,128,44])
  self.assertEqual(b"".join(work.body_chunks),b"X"*300); self.assertEqual(work.trace,(NODE,))
 def test_local_hold_reject_and_missing_prepare_no_work(self):
  local=self.deposit(recipient=LOCAL)
  cases=(ForwardEnvelope(local.message_id,LOCAL),ForwardEnvelope(99,Address.parse("W6ABC")),ForwardEnvelope(99,DEST,(NODE,)))
  expected=(ForwardDisposition.DELIVER_LOCAL,ForwardDisposition.HOLD,ForwardDisposition.REJECT)
  for envelope,want in zip(cases,expected):
   result=self.planner.prepare(envelope); self.assertEqual(result.decision.disposition,want); self.assertIsNone(result.message)
  missing=self.planner.prepare(ForwardEnvelope(999,DEST)); self.assertEqual(missing.decision.disposition,ForwardDisposition.HOLD); self.assertIsNone(missing.message)
 def test_destination_ownership_prevents_id_confusion(self):
  msg=self.deposit(recipient=LOCAL)
  result=self.planner.prepare(ForwardEnvelope(msg.message_id,DEST))
  self.assertEqual(result.decision.disposition,ForwardDisposition.HOLD); self.assertIsNone(result.message)
 def test_batch_is_bounded_unique_and_preserves_order(self):
  first=self.deposit(); second=self.deposit()
  batch=self.planner.prepare_batch((ForwardEnvelope(first.message_id,DEST),ForwardEnvelope(second.message_id,DEST)))
  self.assertTrue(batch.accepted); self.assertEqual([x.envelope.message_id for x in batch.preparations],[first.message_id,second.message_id])
  self.assertFalse(self.planner.prepare_batch(()).accepted)
  self.assertFalse(self.planner.prepare_batch(tuple(ForwardEnvelope(i,DEST) for i in range(1,10))).accepted)
  self.assertFalse(self.planner.prepare_batch((ForwardEnvelope(1,DEST),ForwardEnvelope(1,DEST))).accepted)
 def test_types_fail_closed(self):
  with self.assertRaises(TypeError): MailboxForwardingPlanner(store="bad",policy=self.policy)
  with self.assertRaises(TypeError): self.planner.prepare_batch([])
  with self.assertRaises(TypeError): self.planner.prepare_batch(("bad",))
if __name__=="__main__": unittest.main(verbosity=2)
