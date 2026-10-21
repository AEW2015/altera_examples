#pragma once
#include <stdbool.h>
#include <stdint.h>
typedef struct { uint32_t channel, duration_ms, backoff_qdb, nco_step; bool nco, phase; uint32_t pattern, symbol_us, pulse_cycles, pulse180_cycles, pulse270_cycles; } probe_job_t;
/* Full-line validation; no implicit RF initialization. */
bool probe_parse_tone(const char *line, probe_job_t *job);

/* 16-bit 0x0651, K=7 (171,133 octal) payload8+CRC8+6 tails, 4 zeros.
 * Payload argument must be 0..255; native parser enforces this. */
void probe_frame_bits(uint16_t payload, uint8_t bits[64]);

void probe_qframe_states(uint16_t payload, uint8_t states[64]);

/* Valid only for deadlines less than 2^31 cycles in the future. */
static inline bool probe_cycle_before(uint32_t now, uint32_t deadline) {
    return (int32_t)(now-deadline)<0;
}
/* Remaining wall time is measured once at phase-run entry. */
bool probe_cycle_budget(uint32_t cpu_hz, int64_t remaining_us, uint32_t *cycles);
