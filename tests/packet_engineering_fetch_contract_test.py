#!/usr/bin/env python3
from pathlib import Path
import json

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'firmware/tooling/packet-build-manifest.json').read_text())
wrapper = (root / 'firmware/build-packet-ywd1278-frozen.sh').read_text()

expected_commit = 'd25180ad663d781b761c525d1e699e7b052d6214'
assert manifest['engineering']['commit'] == expected_commit
assert manifest['engineering']['repository'] == 'merberg-ai/ywd-mmdvm'

# Acquisition must be exact-commit, temporary, and checkout-free.
assert "m['engineering']['commit']" in wrapper
assert 'git init -q "$REPO"' in wrapper
assert 'fetch --quiet --no-tags --depth=1 origin "$ENG_COMMIT"' in wrapper
assert 'cat-file -e "$ENG_COMMIT^{commit}"' in wrapper
assert 'rev-parse "$ENG_COMMIT^{commit}"' in wrapper
assert 'ENGINEERING_CHECKOUT_CREATED=NO' in wrapper
assert 'ENGINEERING_WORKTREE_USED=NO' in wrapper
assert 'build-packet-ywd1278.sh' in wrapper
assert '--engineering-repo "$REPO"' in wrapper

# The acquisition wrapper itself must remain build-only and incapable of HAT/RF access.
for forbidden in (
    'stm32flash', '/dev/ttyAMA0', '/dev/serial0', 'pinctrl ',
    'raspi-gpio', 'gpio write', 'YWD_RF_TX_TONES', 'TX_TONES',
):
    assert forbidden not in wrapper, forbidden

print('PACKET_ENGINEERING_FETCH_CONTRACT=PASS')
print(f'ENGINEERING_COMMIT={expected_commit}')
print('ENGINEERING_SOURCE=AUTO_FETCH_EXACT_COMMIT')
print('ENGINEERING_CHECKOUT_CREATED=NO')
print('MODEM_UART_OPENED=NO')
print('RF_TRANSMITTED=NO')
print('FLASH_WRITTEN=NO')
print('OPTION_BYTES_WRITTEN=NO')
