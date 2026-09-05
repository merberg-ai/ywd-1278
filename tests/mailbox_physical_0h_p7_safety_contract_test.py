#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class MailboxPhysicalP7SafetyTests(unittest.TestCase):
 def test_exact_gates_and_disposable_storage(self):
  text=(ROOT/"tools/qualify_0h_p7_mailbox.py").read_text()
  for marker in ("ca4b17de379af9415448083177ffccb39c8fca0f","0H-P7-MAILBOX-145050-KJ6YWD15-ONE","TRANSMIT-0H-P7-MAILBOX-KJ6YWD-15-ONE","KJ6YWD-15","TEMP_MAILBOX=TEMP_ROOT","TEMPORARY_MAILBOX_REMOVED=YES","_restore_service"):
   self.assertIn(marker,text)
 def test_dry_run_precedes_hardware_and_tx(self):
  text=(ROOT/"tools/qualify_0h_p7_mailbox.py").read_text()
  self.assertLess(text.index("if not args.transmit"),text.index("os.geteuid"))
  self.assertLess(text.index("os.geteuid"),text.index("_verify_hardware_identity"))
  self.assertIn("PERSISTENT_CONFIG_MUTATED=NO",text)
  self.assertIn("FLASH_WRITTEN=NO",text); self.assertIn("OPTION_BYTES_WRITTEN=NO",text)
 def test_no_firmware_or_option_write_tools(self):
  text=(ROOT/"tools/qualify_0h_p7_mailbox.py").read_text()
  for forbidden in ("stm32flash","flash_write(","write_option","gpio write"):
   self.assertNotIn(forbidden,text.lower())
if __name__=="__main__": unittest.main(verbosity=2)
