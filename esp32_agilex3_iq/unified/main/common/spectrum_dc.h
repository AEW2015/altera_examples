/* DC estimate in the normalized, bit-reversed Q15 FFT domain. */
#pragma once
#include <stdbool.h>
#include <stdint.h>
extern unsigned spectrum_dc_mode;
typedef struct {
    int32_t re, im;
    bool ready;
} spectrum_dc_t;
static inline int16_t spectrum_sat16(int32_t v) {
    return v > 32767 ? 32767 : v < -32768 ? -32768 : (int16_t)v;
}
static inline __attribute__((always_inline)) void spectrum_dc_apply(spectrum_dc_t *dc, int16_t *x,
                                                                    unsigned n) {
    int32_t dr = x[0], di = x[1];
    if (spectrum_dc_mode) {
        if (!dc->ready) {
            dc->re = dr * 256;
            dc->im = di * 256;
            dc->ready = true;
        } else {
            dc->re += (dr * 256 - dc->re) >> 6;
            dc->im += (di * 256 - dc->im) >> 6;
        }
        dr = (dc->re + 128) >> 8;
        di = (dc->im + 128) >> 8;
    }
    x[0] = spectrum_sat16(x[0] - dr);
    x[1] = spectrum_sat16(x[1] - di);
    for (unsigned k = 0; k < 2; k++) {
        unsigned j = k ? n - 1 : n / 2;
        x[2 * j] = spectrum_sat16(x[2 * j] + dr / 2);
        x[2 * j + 1] = spectrum_sat16(x[2 * j + 1] + di / 2);
    }
}
