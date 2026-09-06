#!/usr/bin/env python3
from __future__ import annotations
import unittest
from ywd1278.ax25 import Address
from ywd1278.node.forwarding_integration import PreparedForwardMessage
from ywd1278.node.linbpq_dialogue import LinBPQPersonalDelivery,LinBPQState
SENDER=Address.parse("KJ6YWD-10"); DEST=Address.parse("KJ6YWD-15"); BBS=Address.parse("KJ6YWD-1"); NODE=Address.parse("KJ6YWD-10")
def work(body=(b"YWD-1278 FORWARD",)):
 return PreparedForwardMessage(1,SENDER,DEST,BBS,"P9 TEST",body,(NODE,))
class LinBPQDialogueP9Tests(unittest.TestCase):
 def test_observed_banner_prompt_and_classic_sp_dialogue(self):
  session=LinBPQPersonalDelivery(work=work(),bbs=BBS,prompt_callsign="KJ6YWD")
  banner=session.feed(b"YWDNOD:KJ6YWD-5} Connected to BBS\r[BPQ-6.0.25.30-IHJM$]\rYWDBBS:KJ6YWD-1}\rde KJ6YWD>")
  self.assertEqual([(x.kind,x.data) for x in banner.actions],[('SP',b'SP KJ6YWD-15\r')])
  title=session.feed(b"Enter Title (only):\r"); self.assertEqual(title.actions[0].data,b"P9 TEST\r")
  body=session.feed(b"Enter Message Text, end with /EX\r")
  self.assertEqual([(x.kind,x.data) for x in body.actions],[('BODY',b'YWD-1278 FORWARD'),('BODY_END',b'\r'),('END',b'/EX\r')])
  accepted=session.feed(b"Message 42 Saved\rde KJ6YWD>")
  self.assertTrue(accepted.accepted); self.assertEqual(session.snapshot.state,LinBPQState.COMPLETE)
  self.assertTrue(session.snapshot.sid_seen); self.assertEqual(session.snapshot.actions_prepared,5)
 def test_fragmented_prompt_and_128_byte_body_preserve_stream(self):
  body=(b"X"*128,b"Y"*4); session=LinBPQPersonalDelivery(work=work(body),bbs=BBS,prompt_callsign="KJ6YWD")
  self.assertEqual(session.feed(b"[BPQ-6.0").actions,())
  self.assertEqual(session.feed(b"]\rde KJ6").actions,())
  self.assertEqual(session.feed(b"YWD>").actions[0].kind,"SP")
  session.feed(b"Subject:\r"); result=session.feed(b"Message /EX:\r")
  stream=b"".join(x.data for x in result.actions)
  self.assertEqual(stream,b"X"*128+b"Y"*4+b"\r/EX\r")
  self.assertTrue(all(len(x.data)<=128 for x in result.actions))
 def test_rejection_nonascii_overflow_line_limit_and_terminal_are_closed(self):
  session=LinBPQPersonalDelivery(work=work(),bbs=BBS,prompt_callsign="KJ6YWD")
  self.assertFalse(session.feed(b"[BPQ-x]\rde KJ6YWD>\rInvalid recipient\r").accepted)
  self.assertEqual(session.snapshot.state,LinBPQState.FAILED); self.assertFalse(session.feed(b"more").accepted)
  for payload in (b"\xff\r",b"X"*513):
   item=LinBPQPersonalDelivery(work=work(),bbs=BBS,prompt_callsign="KJ6YWD")
   self.assertFalse(item.feed(payload).accepted); self.assertEqual(item.snapshot.state,LinBPQState.FAILED)
 def test_prompt_without_sid_and_configuration_fail_closed(self):
  session=LinBPQPersonalDelivery(work=work(),bbs=BBS,prompt_callsign="KJ6YWD")
  self.assertFalse(session.feed(b"de KJ6YWD>").accepted)
  with self.assertRaises(ValueError): LinBPQPersonalDelivery(work=work(),bbs=Address.parse("N0CALL"),prompt_callsign="KJ6YWD")
  with self.assertRaises(ValueError): LinBPQPersonalDelivery(work=work(),bbs=BBS,prompt_callsign="bad prompt")
if __name__=="__main__": unittest.main(verbosity=2)
