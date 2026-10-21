#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
/opt/altera/riscfree/toolchain/riscv32-unknown-elf/bin/riscv32-unknown-elf-gcc \
 -march=rv32i_zicsr -mabi=ilp32 -Os -ffreestanding -fno-builtin -mno-relax \
 -nostdlib -nostartfiles -Wl,-Map=sw/monitor.map -T sw/link.ld \
 sw/start.S sw/main.c -o sw/monitor.elf
/opt/altera/niosv/bin/elf2hex -i sw/monitor.elf -o sw/monitor.hex -b 0 -e 0xffff -w 32
/opt/altera/riscfree/toolchain/riscv32-unknown-elf/bin/riscv32-unknown-elf-size sw/monitor.elf
python3 - <<'MANIFEST'
import hashlib, json
from pathlib import Path
sw = Path('sw')
result = dict(status='PASS', architecture='rv32i_zicsr / ilp32', ram_bytes=65536,
              files={name: hashlib.sha256((sw/name).read_bytes()).hexdigest()
                     for name in ('main.c','fir_control.h','start.S','link.ld','monitor.elf','monitor.hex')})
(sw/'BUILD_RESULT.json').write_text(json.dumps(result, indent=2)+'\n')
MANIFEST
