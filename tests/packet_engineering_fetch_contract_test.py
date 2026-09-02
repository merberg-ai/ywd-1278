#!/usr/bin/env python3
from pathlib import Path
import json

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'firmware/tooling/packet-build-manifest.json').read_text())
wrapper = (root / 'firmware/build-packet-ywd1278-frozen.sh').read_text()

expected_commit = 'd25180ad663d781b761c525d1e699e7b052d6214'
assert manifest['engineering']['commit'] == expected_commit
assert manifest['engineering']['repository'] == 'merberg-ai/ywd-mmdvm'
assert manifest['engineering']['source'] == 'vendored'
assert manifest['engineering']['vendored_root'] == 'firmware/vendor/ywd-mmdvm'

# The historical wrapper now delegates to the self-contained vendored builder.
assert 'FROZEN_ENGINEERING_VENDOR=PASS' in wrapper
assert 'ENGINEERING_EXTERNAL_REPO_REQUIRED=NO' in wrapper
assert 'ENGINEERING_NETWORK_FETCH_REQUIRED=NO' in wrapper
assert 'ENGINEERING_WORKTREE_USED=NO' in wrapper
assert 'build-packet-ywd1278.sh' in wrapper
assert 'exec "$BUILDER" "$@"' in wrapper
assert "m['engineering']['source']" in wrapper
assert "m['engineering']['vendored_root']" in wrapper

# Never regress to requiring the old sibling checkout or fetching YWD-MMDVM.
for forbidden in (
    '--engineering-repo',
    'YWD1278_ENGINEERING_REPO',
    'mmdvm-lab/ywd-mmdvm',
    'git init -q "$REPO"',
    'fetch --quiet --no-tags --depth=1 origin "$ENG_COMMIT"',
):
    assert forbidden not in wrapper, forbidden

# The compatibility wrapper itself remains build-only and incapable of HAT/RF access.
for forbidden in (
    'stm32flash', '/dev/ttyAMA0', '/dev/serial0', 'pinctrl ',
    'raspi-gpio', 'gpio write', 'YWD_RF_TX_TONES', 'TX_TONES',
):
    assert forbidden not in wrapper, forbidden

print('PACKET_ENGINEERING_VENDOR_CONTRACT=PASS')
print(f'ENGINEERING_COMMIT={expected_commit}')
print('ENGINEERING_SOURCE=VENDORED_IN_YWD1278')
print('ENGINEERING_EXTERNAL_REPO_REQUIRED=NO')
print('ENGINEERING_NETWORK_FETCH_REQUIRED=NO')
print('MODEM_UART_OPENED=NO')
print('RF_TRANSMITTED=NO')
print('FLASH_WRITTEN=NO')
print('OPTION_BYTES_WRITTEN=NO')
