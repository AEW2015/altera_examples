OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { ram (rwx) : ORIGIN = 0x00000000, LENGTH = 256K }
SECTIONS {
 .text : { KEEP(*(.text.start)) *(.text*) *(.rodata*) } > ram
 .data : { *(.data*) *(.sdata*) } > ram
 . = ALIGN(4);
 __global_pointer$ = . + 0x800;
 .bss (NOLOAD) : { __bss_start = .; *(.bss*) *(.sbss*) *(COMMON) . = ALIGN(4); __bss_end = .; } > ram
 _stack_top = ORIGIN(ram) + LENGTH(ram) - 16;
 ASSERT(__bss_end < _stack_top - 4096, "Firmware exceeds RAM/stack budget")
}
