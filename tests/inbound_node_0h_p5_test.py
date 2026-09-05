#!/usr/bin/env python3
from __future__ import annotations
import unittest
from ywd1278.ax25 import Address, parse_frame
from ywd1278.link.data_link import build_i_frame, build_s_frame
from ywd1278.link.modulo8 import LinkState, build_unnumbered_frame
from ywd1278.link.timed_link import LinkTimerConfig
from ywd1278.node.inbound import InboundNodeSession

LOCAL=Address.parse("KJ6YWD-10")
REMOTE=Address.parse("KJ6YWD-15")
TIMERS=LinkTimerConfig(t1_seconds=5,t2_seconds=1,t3_seconds=30,max_retries=2)

def u(name, source=REMOTE, command=True):
 return build_unnumbered_frame(source=source,destination=LOCAL,frame_type=name,command=command,poll_final=True)
def i(ns,nr,text):
 return build_i_frame(source=REMOTE,destination=LOCAL,ns=ns,nr=nr,info=text,command=True)
def rr(nr):
 return build_s_frame(source=REMOTE,destination=LOCAL,frame_type="RR",nr=nr,command=False)
def parsed(actions): return [parse_frame(x.frame_no_fcs,has_fcs=False) for x in actions]

class InboundNodeP5Tests(unittest.TestCase):
 def test_full_linbpq_style_session_and_ack_before_disc(self):
  node=InboundNodeSession(local=LOCAL,remote=REMOTE,timers=TIMERS)
  start=node.handle_frame(u("SABM"),now=0)
  frames=parsed(start.actions)
  self.assertEqual([x["frame_type"] for x in frames],["UA","I","I"])
  self.assertEqual([x["info"] for x in frames[1:]],list(node._node.banner()))
  self.assertEqual(node.snapshot.connections,1)
  node.handle_frame(rr(2),now=.1)
  help_result=node.handle_frame(i(0,2,b"HELP\r"),now=.2)
  help_frames=parsed(help_result.actions)
  self.assertEqual(len(help_frames),4)
  self.assertTrue(node.snapshot.help_seen)
  node.handle_frame(rr(6),now=.3)
  info_result=node.handle_frame(i(1,6,b"INFO\r"),now=.4)
  self.assertEqual(len(parsed(info_result.actions)),2)
  self.assertTrue(node.snapshot.info_seen)
  node.handle_frame(rr(0),now=.5)
  bye_result=node.handle_frame(i(2,0,b"BYE\r"),now=.6)
  self.assertEqual([x["frame_type"] for x in parsed(bye_result.actions)],["I"])
  self.assertFalse(node.snapshot.orderly_release_started)
  release=node.handle_frame(rr(1),now=.7)
  self.assertEqual([x["frame_type"] for x in parsed(release.actions)],["DISC"])
  self.assertTrue(node.snapshot.bye_seen)
  self.assertTrue(node.snapshot.orderly_release_started)
  final=node.handle_frame(u("UA",command=False),now=.8)
  self.assertTrue(final.accepted)
  self.assertEqual(node.snapshot.state,LinkState.DISCONNECTED)

 def test_fragmented_command_and_window_backpressure(self):
  node=InboundNodeSession(local=LOCAL,remote=REMOTE,maxframe=1,timers=TIMERS)
  start=node.handle_frame(u("SABM"),now=0)
  self.assertEqual([x["frame_type"] for x in parsed(start.actions)],["UA","I"])
  next_banner=node.handle_frame(rr(1),now=.1)
  self.assertEqual(len(next_banner.actions),1)
  node.handle_frame(rr(2),now=.2)
  self.assertEqual(node.handle_frame(i(0,2,b"HE"),now=.3).actions,())
  answer=node.handle_frame(i(1,2,b"LP\r"),now=.4)
  self.assertEqual(len(answer.actions),1)
  self.assertTrue(node.snapshot.help_seen)
  self.assertEqual(node.snapshot.pending_responses,3)

 def test_wrong_peer_and_malformed_frames_are_inert(self):
  node=InboundNodeSession(local=LOCAL,remote=REMOTE,timers=TIMERS)
  wrong=node.handle_frame(u("SABM",source=Address.parse("N0CALL-1")),now=0)
  self.assertFalse(wrong.accepted)
  self.assertEqual(wrong.actions,())
  self.assertEqual(node.snapshot.connections,0)
  malformed=node.handle_frame(b"bad",now=.1)
  self.assertFalse(malformed.accepted)
  self.assertEqual(malformed.actions,())

if __name__=="__main__": unittest.main(verbosity=2)
