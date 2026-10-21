#include "spectrum_stats.h"
#include "spectrum_dc.h"
#include "esp_heap_caps.h"
#include "esp_private/esp_clk.h"
#include "esp_rom_crc.h"
#include "esp_timer.h"
#include <string.h>
unsigned spectrum_dc_mode = 1;
void spectrum_stats_init(spectrum_stats_t *s) {
    *s = (spectrum_stats_t){.at = esp_timer_get_time(),
                            .cycles_per_us = esp_clk_cpu_freq() / 1000000u,
                            .heap_free = heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
                            .heap_largest = heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL)};
}
void spectrum_stats_emit(spectrum_stats_t *s, unsigned n, unsigned fs, uint32_t ffts, uint32_t abandoned,
                         uint32_t drops, uint32_t late, unsigned queue, bool (*send)(const void *, size_t)) {
    int64_t now = esp_timer_get_time();
    uint64_t dt = now - s->at;
    if (dt < 250000) return;
    uint64_t load = s->busy * 1000 / (dt * s->cycles_per_us), df = ffts - s->ffts;
    uint64_t coverage = df * n * 1000000000ull / (dt * fs);
    spectrum_stats_frame_t frame = {.magic = 0x31535053u,
                                    .core0 = load > 1000 ? 1000 : load,
                                    .coverage = coverage > 1000 ? 1000 : coverage,
                                    .heap_free = s->heap_free,
                                    .heap_largest = s->heap_largest,
                                    .abandoned = abandoned,
                                    .drops = drops,
                                    .late_max = late > 65535 ? 65535 : late,
                                    .queue = queue > 1000 ? 1000 : queue,
                                    .ffts_per_s = df * 1000000 / dt};
    uint8_t bytes[40];
    memcpy(bytes, &frame, 36);
    uint32_t crc = esp_rom_crc32_le(0, bytes, 36);
    memcpy(bytes + 36, &crc, 4);
    send(bytes, sizeof(bytes));
    s->at = now;
    s->ffts = ffts;
    s->busy = 0;
}
