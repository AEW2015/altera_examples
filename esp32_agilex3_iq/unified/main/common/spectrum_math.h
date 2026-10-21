/* Integer power-to-wire conversion, shared by scalar spectrum backends.
 * Piecewise-linear log2 approximation has <0.06 dB error before 0.5 dB
 * quantization. It avoids soft-float logarithms in the capture deadline. */
#pragma once
#include <stdint.h>
static inline uint32_t spectrum_complex_power(int16_t re, int16_t im) {
    /* Each product fits int32_t; the sum can be exactly 2^31. */
    return (uint32_t)((int32_t)re * re) + (uint32_t)((int32_t)im * im);
}
static inline uint8_t spectrum_log_power_code(unsigned exponent, uint32_t norm) {
    static const uint16_t log2_q12[17] = {0,    358,  696,  1016, 1319, 1607, 1882, 2144, 2396,
                                          2637, 2869, 3092, 3307, 3515, 3715, 3908, 4096};
    unsigned slot = (norm - 256u) >> 4, frac = norm & 15u;
    uint32_t logarithm =
        (exponent << 12) + log2_q12[slot] + ((log2_q12[slot + 1] - log2_q12[slot]) * frac + 8) / 16;
    unsigned code = (logarithm * 1541u + (1u << 19)) >> 20; /* 20 log10(power), rounded */
    return code > 255 ? 255 : code;
}
static inline uint8_t spectrum_power_code(uint32_t power) {
    if (!power) return 0;
    unsigned exponent = 31u - __builtin_clz(power);
    return spectrum_log_power_code(exponent, (power << (31u - exponent)) >> 23);
}
/* Averaged powers retain fractions: truncating them to integer power would
 * bias quiet bins down by several wire steps. Extract the float mantissa
 * directly, using the same approximation as the integer encoder. */
static inline uint8_t spectrum_mean_power_code(float power) {
    union {
        float f;
        uint32_t u;
    } value = {.f = power};
    /* Positive IEEE-754 encodings sort numerically. Also reject NaNs and
     * negative values without calling the software float comparator. */
    if (value.u < 0x3f800000u || value.u > 0x7f800000u) return 0;
    unsigned exponent = (value.u >> 23) - 127u;
    if (exponent >= 43) return 255;
    return spectrum_log_power_code(exponent, 256u + ((value.u & 0x7fffffu) >> 15));
}
