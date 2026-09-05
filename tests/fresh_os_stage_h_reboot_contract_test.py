#!/usr/bin/env python3
from pathlib import Path

prepare=Path('tools/stage_h_reboot_prepare.sh').read_text(encoding='utf-8')
qual=Path('tools/qualify_stage_h_reboot_rx.sh').read_text(encoding='utf-8')
expected='2f5299e65add072fea6ee55a54dc421faf00c276'
assert expected in prepare and expected in qual
assert '/var/lib/ywd-1278/stage-h-reboot-before.json' in prepare
assert '/var/lib/ywd-1278/stage-h-reboot-before.json' in qual
assert "'stage':'H-reboot'" in prepare
assert "d['stage']=='H-reboot'" in qual
assert 'kernel boot ID did not change' in qual
assert 'service did not auto-start after reboot' in qual
assert 'SERVICE_ELIGIBILITY_AFTER_REBOOT=PASS' in qual
assert 'EXACT_AX25R4_IDENTITY_AFTER_REBOOT=PASS' in qual
assert 'FRESH_TELNET_MHEARD_ADVANCE=PASS' in qual
assert 'FRESH_PTY_MHEARD_ADVANCE=PASS' in qual
assert 'TX_ENABLED=NO' in prepare and 'TX_ENABLED=NO' in qual
assert 'KISS_DATA_SENT=NO' in qual
assert 'RF_TRANSMITTED_BY_QUALIFIER=NO' in qual
for forbidden in ('deploy-product-firmware.sh','stm32flash','WRITE-FIRMWARE-NOW','tx_enabled = true','allow_automatic_flash = true'):
    assert forbidden not in prepare
    assert forbidden not in qual
print('STAGE_H_REBOOT_CONTRACT=PASS')
