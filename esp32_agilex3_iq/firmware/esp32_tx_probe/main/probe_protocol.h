#pragma once
#include <stdbool.h>
#include <stdint.h>
typedef struct { uint32_t channel, duration_ms, backoff_qdb, nco_step; bool nco, phase; uint32_t pattern, symbol_us, pulse_cycles; } probe_job_t;
/* Full-line validation; no implicit RF initialization. */
bool probe_parse_tone(const char *line, probe_job_t *job);
