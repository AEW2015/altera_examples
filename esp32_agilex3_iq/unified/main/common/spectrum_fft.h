/* Rounded Q15 radix-2 FFT, with bounded transport-service points.
 * Same butterflies and bit-reversed twiddles as the ESP-DSP ANSI kernel. */
#pragma once
#include <stdint.h>
static inline void spectrum_fft_poll(int16_t *x, unsigned n, const int16_t *w, void (*poll)(void *),
                                     void *context) {
    unsigned work = 0;
    for (unsigned half = n / 2, groups = 1; half; half /= 2, groups *= 2)
        for (unsigned group = 0; group < groups; group++)
            for (unsigned offset = 0; offset < half; offset++) {
                unsigned a = group * half * 2 + offset, b = a + half;
                int32_t wr = w[2 * group], wi = w[2 * group + 1];
                int32_t ar = x[2 * a], ai = x[2 * a + 1], br = x[2 * b], bi = x[2 * b + 1];
                uint32_t tr = (uint32_t)(wr * br) + (uint32_t)(wi * bi);
                uint32_t ti = (uint32_t)(wr * bi) - (uint32_t)(wi * br);
                uint32_t rr = (uint32_t)(ar * 32767) + 32767u, ri = (uint32_t)(ai * 32767) + 32767u;
                x[2 * a] = (int16_t)((rr + tr) >> 16);
                x[2 * a + 1] = (int16_t)((ri + ti) >> 16);
                x[2 * b] = (int16_t)((rr - tr) >> 16);
                x[2 * b + 1] = (int16_t)((ri - ti) >> 16);
                if ((++work & 31u) == 0) poll(context);
            }
}
