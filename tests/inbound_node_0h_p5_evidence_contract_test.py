#!/usr/bin/env python3
"""Immutable evidence contract for physically executed 0H-P5."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/"firmware/qualification/0h-p5-inbound-node-target-pi.json"
def blob(path):
 data=path.read_bytes(); return hashlib.sha1(f"blob {len(data)}\0".encode()+data).hexdigest()
class InboundNodeP5EvidenceTests(unittest.TestCase):
 def test_exact_physical_acceptance(self):
  data=json.loads(EVIDENCE.read_text())
  self.assertEqual(data["candidate_commit"],"07ca06cc0cd5b7b05de4dce4d3ca1e7c452caf2a")
  self.assertEqual((data["frequency_hz"],data["tx_power"]),(145050000,200))
  self.assertEqual((data["local_node"],data["remote_listener"],data["remote_downlink_identity"]),("KJ6YWD-10","KJ6YWD-5","KJ6YWD-15"))
  for key in ("dry_run_pass","service_eligibility_pass","hat_detect_pass","sabm_ua_exchange_pass","banner_sent_pass","help_pass","info_pass","version_pass","bye_pass","bye_ack_before_disc_pass","disc_ua_exchange_pass","normal_service_restored"):
   self.assertIs(data[key],True,key)
  self.assertEqual(data["link_actions_submitted"],12)
  capture=data["independent_packet_capture"]
  self.assertEqual(capture["sabm_times"],["23:11:17.459454","23:11:27.839326"])
  self.assertLess(capture["bye_ack_time"],capture["disc_time"])
  self.assertLess(capture["disc_time"],capture["final_ua_time"])
  for key in ("banner_exact","help_response_exact","info_response_exact","bye_response_exact"):
   self.assertIs(capture[key],True,key)
  self.assertIs(data["persistent_tx_enabled_final"],False)
  self.assertIs(data["persistent_config_mutated"],False)
  self.assertIs(data["flash_written"],False); self.assertIs(data["option_bytes_written"],False)
 def test_executed_harness_is_byte_exact(self):
  self.assertEqual(blob(ROOT/"tools/qualify_0h_p5_inbound_node.py"),"6e0a331344493cb7255c83144b10d39ba1851993")
if __name__=="__main__": unittest.main(verbosity=2)
