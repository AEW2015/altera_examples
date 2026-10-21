#include "system.h"
#include "sys/alt_stdio.h"
#include <unistd.h>

int main(void)
{
    alt_putstr("Hello World from the Atum A3 Nano Nios V/m!\n");
    alt_printf("HAL BSP: %s, CPU: %s, clock: %x Hz (hex)\n",
               ALT_SYSTEM_NAME, ALT_CPU_NAME, ALT_CPU_FREQ);
    unsigned count = 0;
    for (;;) {
        alt_printf("Hello heartbeat %x\n", count++);
        usleep(1000000);
    }
}
