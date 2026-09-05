#!/usr/bin/env python3
from __future__ import annotations
import unittest
from ywd1278.ax25 import Address
from ywd1278.node.forwarding import ForwardDisposition, ForwardEnvelope, ForwardRoute, StaticForwardingPolicy

NODE=Address.parse("KJ6YWD-5"); LOCAL=Address.parse("KJ6YWD-1"); DEST=Address.parse("N0CALL"); HOP=Address.parse("W6NODE")

def policy(**kwargs):
    return StaticForwardingPolicy(node=NODE, local_destinations=(NODE,LOCAL), routes=(ForwardRoute(DEST,HOP),), **kwargs)

class ForwardingPolicyP3Tests(unittest.TestCase):
    def test_local_delivery_wins_without_route_or_trace_mutation(self):
        result=policy().decide(ForwardEnvelope(1,LOCAL,(HOP,)))
        self.assertEqual(result.disposition,ForwardDisposition.DELIVER_LOCAL); self.assertEqual(result.next_trace,(HOP,))
    def test_exact_route_returns_inert_next_hop_and_appended_trace(self):
        result=policy().decide(ForwardEnvelope(2,DEST))
        self.assertEqual(result.disposition,ForwardDisposition.FORWARD); self.assertEqual(result.next_hop,HOP); self.assertEqual(result.next_trace,(NODE,))
    def test_missing_and_disabled_routes_hold(self):
        self.assertEqual(policy().decide(ForwardEnvelope(1,Address.parse("K1ABC"))).disposition,ForwardDisposition.HOLD)
        disabled=StaticForwardingPolicy(node=NODE,local_destinations=(NODE,),routes=(ForwardRoute(DEST,HOP,False),))
        self.assertEqual(disabled.decide(ForwardEnvelope(1,DEST)).disposition,ForwardDisposition.HOLD)
    def test_loops_and_hop_limit_reject(self):
        for trace in ((NODE,), (HOP,HOP)):
            self.assertEqual(policy().decide(ForwardEnvelope(1,DEST,trace)).disposition,ForwardDisposition.REJECT)
        self.assertEqual(policy(max_hops=1).decide(ForwardEnvelope(1,DEST,(Address.parse("K1ABC"),))).disposition,ForwardDisposition.REJECT)
    def test_next_hop_in_trace_rejects(self):
        self.assertEqual(policy().decide(ForwardEnvelope(1,DEST,(HOP,))).disposition,ForwardDisposition.REJECT)
    def test_configuration_fails_closed(self):
        with self.assertRaises(ValueError): StaticForwardingPolicy(node=NODE,local_destinations=(NODE,NODE))
        with self.assertRaises(ValueError): StaticForwardingPolicy(node=NODE,local_destinations=(NODE,),routes=(ForwardRoute(NODE,HOP),))
        with self.assertRaises(ValueError): StaticForwardingPolicy(node=NODE,local_destinations=(NODE,),routes=(ForwardRoute(DEST,NODE),))
        with self.assertRaises(ValueError): policy(max_hops=9)
    def test_bad_envelope_fails_closed(self):
        with self.assertRaises(ValueError): policy().decide(ForwardEnvelope(0,DEST))
        with self.assertRaises(TypeError): policy().decide("bad")

if __name__=="__main__": unittest.main(verbosity=2)
