#!/usr/bin/env python3
"""Immutable evidence contract for physically executed 0H-P7."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]; EVIDENCE=ROOT/"firmware/qualification/0h-p7-mailbox-target-pi.json"
def blob(path):
 data=path.read_bytes(); return hashlib.sha1(f"blob {len(data)}\0".encode()+data).hexdigest()
class MailboxPhysicalP7EvidenceTests(unittest.TestCase):
 def test_exact_mailbox_round_trip(self):
  data=json.loads(EVIDENCE.read_text())
  self.assertEqual(data["candidate_commit"],"33d49c2b6c0824cf6b182e1a5636ee0250a189bb")
  self.assertEqual((data["frequency_hz"],data["tx_power"]),(145050000,200))
  self.assertEqual((data["local_node"],data["remote_listener"],data["remote_downlink_identity"]),("KJ6YWD-10","KJ6YWD-5","KJ6YWD-15"))
  self.assertEqual((data["subject"],data["body"]),("P7 TEST","YWD-1278 0H-P7 MAILBOX TEST 1/1"))
  for key in ("dry_run_pass","service_eligibility_pass","hat_detect_pass","sabm_ua_exchange_pass","mailbox_help_pass","empty_list_pass","message_deposit_pass","populated_list_pass","owner_read_pass","message_content_exact","bye_ack_before_disc_pass","disc_ua_exchange_pass","temporary_mailbox_removed","normal_service_restored"):
   self.assertIs(data[key],True,key)
  self.assertEqual(data["link_actions_submitted"],25)
  self.assertIs(data["persistent_tx_enabled_final"],False); self.assertIs(data["persistent_config_mutated"],False)
  self.assertIs(data["flash_written"],False); self.assertIs(data["option_bytes_written"],False)
  self.assertIs(data["operator_observation"]["linbpq_style_l_alias_supported"],False)
  self.assertIs(data["operator_observation"]["linbpq_style_r_alias_supported"],False)
 def test_executed_harness_is_byte_exact(self):
  self.assertEqual(blob(ROOT/"tools/qualify_0h_p7_mailbox.py"),"b9ba6c07a210a946e5988cb051b5a7c6f6ca9635")
if __name__=="__main__": unittest.main(verbosity=2)
