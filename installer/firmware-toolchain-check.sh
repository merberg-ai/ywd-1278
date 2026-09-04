#!/usr/bin/env bash
set -Eeuo pipefail

mode="${1:-check}"
case "$mode" in
  check|install) ;;
  *) echo "Usage: $0 [check|install]" >&2; exit 2 ;;
esac

packages=(
  gcc-arm-none-eabi
  binutils-arm-none-eabi
  libnewlib-arm-none-eabi
  libstdc++-arm-none-eabi-dev
  stm32flash
)

if [[ "$mode" == install ]]; then
  [[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "[FAIL] install mode requires root" >&2; exit 2; }
  command -v apt-get >/dev/null 2>&1 || { echo "[FAIL] apt-get unavailable" >&2; exit 3; }
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-install-recommends "${packages[@]}"
fi

for cmd in arm-none-eabi-gcc arm-none-eabi-g++ arm-none-eabi-objcopy stm32flash; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "[FAIL] missing firmware tool: $cmd" >&2; exit 4; }
done

tmp="$(mktemp -d /tmp/ywd1278-fwtoolchain.XXXXXX)"
cleanup(){ rm -rf "$tmp"; }
trap cleanup EXIT

cat >"$tmp/probe.c" <<'EOF'
#include <stdint.h>
#include <string.h>
static uint8_t b[4];
int probe_c(void) { memset(b, 0, sizeof b); return (int)sizeof(uint32_t); }
EOF

cat >"$tmp/probe.cpp" <<'EOF'
#include <cstdint>
#include <cstring>
static std::uint8_t b[4];
int probe_cpp() { std::memset(b, 0, sizeof b); return (int)sizeof(std::uint32_t); }
EOF

arm-none-eabi-gcc -ffreestanding -c "$tmp/probe.c" -o "$tmp/probe-c.o"
arm-none-eabi-g++ -ffreestanding -fno-exceptions -fno-rtti -c "$tmp/probe.cpp" -o "$tmp/probe-cpp.o"

echo "YWD1278_FIRMWARE_TOOLCHAIN_CHECK=PASS"
echo "ARM_NONE_EABI_C_HEADERS=PASS"
echo "ARM_NONE_EABI_CPP_HEADERS=PASS"
echo "STM32FLASH_PRESENT=YES"
echo "HARDWARE_ACCESS=NO"
echo "FLASH_WRITTEN=NO"
echo "RF_TRANSMITTED=NO"
