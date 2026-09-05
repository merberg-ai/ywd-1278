#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import tempfile, unittest
from ywd1278.ax25 import Address, parse_frame
from ywd1278.link.data_link import build_i_frame, build_s_frame
from ywd1278.link.modulo8 import build_unnumbered_frame
from ywd1278.link.timed_link import LinkTimerConfig
from ywd1278.node.inbound import InboundNodeSession
from ywd1278.node.mailbox import MailboxStore
from ywd1278.node.mailbox_commands import MailboxNodeSession

LOCAL=Address.parse("KJ6YWD-10"); PEER=Address.parse("KJ6YWD-15"); OTHER=Address.parse("KJ6YWD-1")

class MailboxCommandsP6Tests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(); self.store=MailboxStore(Path(self.temp.name)/"mail.sqlite3")
  self.now=123456789; self.session=self.make_session()
 def tearDown(self): self.temp.cleanup()
 def make_session(self):
  return MailboxNodeSession(callsign=LOCAL,peer=PEER,alias="YWDNOD",store=self.store,clock_ns=lambda:self.now)
 def lines(self,result): return [x.decode("ascii").rstrip("\r") for x in result.responses]

 def test_help_info_banner_and_base_version_bye(self):
  self.assertIn(b"Mailbox ready",self.session.banner()[1])
  help_lines=self.lines(self.session.feed(b"HELP\r"))
  self.assertTrue(any(x.startswith("LIST") for x in help_lines)); self.assertTrue(any(x.startswith("SP ") for x in help_lines))
  self.assertIn("MAILBOX OWNER KJ6YWD-15",self.lines(self.session.feed(b"INFO\r")))
  self.assertTrue(self.lines(self.session.feed(b"VERSION\r"))[0].startswith("YWD-1278 "))
  bye=self.session.feed(b"BYE\r"); self.assertEqual(bye.responses,(b"BYE\r",)); self.assertTrue(bye.close_requested)

 def test_compose_deposit_list_read_and_peer_ownership(self):
  self.assertTrue(self.session.feed(b"SP KJ6YWD-1 Test subject\r").accepted)
  self.assertTrue(self.session.snapshot.composing)
  self.assertEqual(self.session.feed(b"First line\rSecond line\r").responses,())
  saved=self.session.feed(b"/EX\r"); self.assertEqual(self.lines(saved),["MESSAGE 1 SAVED FOR KJ6YWD-1"])
  message=self.store.read_for(OTHER,1); self.assertIsNotNone(message)
  assert message is not None
  self.assertEqual((message.sender,message.subject,message.body,message.created_at_ns),("KJ6YWD-15","Test subject",b"First line\rSecond line",self.now))
  self.store.deposit(sender=OTHER,recipient=PEER,subject="For peer",body=b"Secret",created_at_ns=2)
  listing=self.lines(self.session.feed(b"LIST\r")); self.assertEqual(listing[0],"MESSAGES 1 NEWEST FIRST")
  self.assertIn("FROM KJ6YWD-1 6B For peer",listing[1])
  read=self.lines(self.session.feed(b"READ 2\r")); self.assertIn("Secret",read); self.assertEqual(read[-1],"END MESSAGE")
  denied=self.session.feed(b"READ 1\r"); self.assertFalse(denied.accepted); self.assertIn(b"not found",denied.responses[0])

 def test_paged_read_and_bounded_list(self):
  body=b"X"*700
  msg=self.store.deposit(sender=OTHER,recipient=PEER,subject="Long",body=body,created_at_ns=1)
  first=self.lines(self.session.feed(f"READ {msg.message_id}\r".encode()))
  self.assertEqual(first[2],"BODY 0:512/700"); self.assertEqual(first[-1],f"MORE READ {msg.message_id} 512")
  second=self.lines(self.session.feed(f"READ {msg.message_id} 512\r".encode()))
  self.assertEqual(second[2],"BODY 512:700/700"); self.assertEqual(second[-1],"END MESSAGE")
  self.assertFalse(self.session.feed(b"LIST 13\r").accepted)

 def test_abort_overflow_bad_input_and_clock_failure_fail_closed(self):
  self.session.feed(b"SP KJ6YWD-1 Abort me\rbody\r")
  self.assertEqual(self.lines(self.session.feed(b"/ABORT\r")),["MESSAGE ABORTED"])
  self.session.feed(b"SP KJ6YWD-1 Huge\r")
  result=None
  for _ in range(40):
   result=self.session.feed((b"X"*120)+b"\r")
   if not result.accepted: break
  self.assertIsNotNone(result); self.assertFalse(result.accepted); self.assertFalse(self.session.snapshot.composing)
  self.assertFalse(self.make_session().feed(b"SP BAD! Subject\r").accepted)
  broken=MailboxNodeSession(callsign=LOCAL,peer=PEER,alias="YWDNOD",store=self.store,clock_ns=lambda:(_ for _ in ()).throw(RuntimeError()))
  broken.feed(b"SP KJ6YWD-1 Clock\rbody\r"); failed=broken.feed(b"/EX\r")
  self.assertFalse(failed.accepted); self.assertFalse(broken.snapshot.composing)

 def test_inbound_coordinator_uses_mailbox_factory(self):
  timers=LinkTimerConfig(t1_seconds=5,t2_seconds=1,t3_seconds=30,max_retries=2)
  node=InboundNodeSession(local=LOCAL,remote=PEER,maxframe=4,timers=timers,session_factory=self.make_session)
  sabm=build_unnumbered_frame(source=PEER,destination=LOCAL,frame_type="SABM",command=True,poll_final=True)
  started=node.handle_frame(sabm,now=0); frames=[parse_frame(x.frame_no_fcs,has_fcs=False) for x in started.actions]
  self.assertEqual([x["frame_type"] for x in frames],["UA","I","I"]); self.assertIn(b"Mailbox ready",frames[2]["info"])
  ack=build_s_frame(source=PEER,destination=LOCAL,frame_type="RR",nr=2,command=False)
  node.handle_frame(ack,now=.1)
  command=build_i_frame(source=PEER,destination=LOCAL,ns=0,nr=2,info=b"LIST\r",command=True)
  listed=node.handle_frame(command,now=.2); outbound=[parse_frame(x.frame_no_fcs,has_fcs=False) for x in listed.actions]
  self.assertEqual(outbound[0]["info"],b"NO MESSAGES\r")

if __name__=="__main__": unittest.main(verbosity=2)
