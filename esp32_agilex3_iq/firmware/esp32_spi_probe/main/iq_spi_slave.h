#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"
#include "iq_spi_packet.h"
// Single producer only. Copies one CI8 capture, blocks on SPI drain with timeout.
esp_err_t iq_spi_init(bool synthetic);
bool iq_spi_requested_synthetic(void);
void iq_spi_set_capture_synthetic(bool synthetic);
esp_err_t iq_spi_publish(const int8_t *ci8, size_t bytes, uint8_t source,
                         uint32_t sequence, uint32_t timeout_ms);
