#pragma once
#include <stdbool.h>

/* Initialize once after the radio and transports have claimed their pins. */
void burst_gpio_init(void);
/* Dispatch after the receiver's serial ownership check, between captures. */
bool burst_gpio_command(const char *line);
