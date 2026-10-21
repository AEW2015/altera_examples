/* Optional SPS1 wire telemetry shared by snapshot and scalar ring backends. */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
typedef struct __attribute__((packed)) {
    uint32_t magic;
    uint16_t core0, core1, coverage, mode;
    uint32_t heap_free, heap_largest, abandoned, drops;
    uint16_t late_max, queue;
    uint32_t ffts_per_s;
} spectrum_stats_frame_t;
_Static_assert(sizeof(spectrum_stats_frame_t) == 36, "SPS1 layout");
typedef struct {
    int64_t at;
    uint64_t busy;
    uint32_t ffts, heap_free, heap_largest, cycles_per_us;
} spectrum_stats_t;
void spectrum_stats_init(spectrum_stats_t *s);
void spectrum_stats_emit(spectrum_stats_t *s, unsigned n, unsigned fs, uint32_t ffts, uint32_t abandoned,
                         uint32_t drops, uint32_t late, unsigned queue, bool (*send)(const void *, size_t));
