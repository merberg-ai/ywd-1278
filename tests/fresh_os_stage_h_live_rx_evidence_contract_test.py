#!/usr/bin/env python3
import json
from pathlib import Path

p=Path('firmware/qualification/0b-product-fresh-os-stage-h-live-rx-target-pi.json')
d=json.loads(p.read_text(encoding='utf-8'))
assert d['schema']==1 and d['stage']=='H'
assert d['status']=='target-pi-live-rx-qualified-reboot-pending'
assert d['installed_product_commit']=='2f5299e65add072fea6ee55a54dc421faf00c276'
assert d['firmware']['artifact_sha256']=='b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616'
assert d['firmware']['service_eligibility_revalidated'] is True
assert d['service_activation']['result']=='pass'
assert d['service_activation']['service_enabled'] is True
assert d['service_activation']['service_active'] is True
assert d['service_activation']['tx_enabled'] is False
assert d['service_activation']['automatic_flash_enabled'] is False
assert d['systemd_lifecycle']['stop_sigterm']=='pass'
assert d['systemd_lifecycle']['pty_cleanup']=='pass'
assert d['systemd_lifecycle']['uart_release']=='pass'
assert d['live_rx']['frequency_hz']==145050000
assert d['live_rx']['result']=='pass'
assert d['live_rx']['kiss_frame_bytes']==69
assert d['live_rx']['ax25_source']=='KJ6YWD'
assert d['live_rx']['kiss_data_received'] is True
assert d['live_rx']['telnet_mheard_source_match'] is True
assert d['live_rx']['pty_mheard_source_match'] is True
assert d['live_rx']['tx_command_sent'] is False
assert d['live_rx']['kiss_data_sent'] is False
assert d['live_rx']['rf_transmitted_by_qualifier'] is False
assert d['final_state']['reboot_qualification']=='pending'
print('STAGE_H_FRESH_OS_LIVE_RX_EVIDENCE=PASS')
