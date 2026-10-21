#pragma once
#include <stdbool.h>
#include <stdint.h>
typedef struct { uint32_t channel, duration_ms, backoff_qdb, nco_step; bool nco, phase; uint32_t pattern, symbol_us, pulse_cycles; } probe_job_t;
/* Full-line validation; no implicit RF initialization. */
bool probe_parse_tone(const char *line, probe_job_t *job);

/* 16-bit 0x0651, K=7 (171,133 octal) payload8+CRC8+6 tails, 4 zeros.
 * Payload argument must be 0..255; native parser enforces this. */
void probe_frame_bits(uint16_t payload, uint8_t bits[64]);
