/* Scalar FFT processing for cores without the S3 SIMD kernel. A completed
 * block is copied out of RF SRAM immediately, then processed in short slices
 * across as many bank rotations as necessary. Completed FFT powers accumulate
 * until output is available; skipped work remains visible in sample indices. */
#include "spectrum_math.h"
enum { SCALAR_IDLE, SCALAR_FFT, SCALAR_BINS, SCALAR_COPY, SCALAR_FRAME, SCALAR_ENCODE, SCALAR_PHASES };
static struct {
    unsigned phase, half, groups, group, offset, emit, bank, first;
    uint64_t index, frame_index;
    unsigned merged, frame_pairs;
    float mean_scale;
    uint8_t gain;
    uint32_t cost[SCALAR_PHASES]; /* longest warm slice of each phase */
} scalar;

static void scalar_flush(void) {
    if (!scalar.merged) return;
    scalar.mean_scale = 1.0f / scalar.merged;
    scalar.emit = 0;
    scalar.phase = SCALAR_ENCODE;
}
static void scalar_accept(unsigned bank, unsigned first, uint64_t index) {
    if (scalar.phase) {
        st.res->abandoned++;
        return;
    }
    scalar.index = index;
    scalar.gain = bank_ptr(bank)[first] >> 20;
    scalar.bank = bank;
    scalar.first = first;
    st.work[bank].pending = true;
    scalar.half = spec_n / 2;
    scalar.groups = 1;
    scalar.group = scalar.offset = 0;
    scalar.phase = SCALAR_COPY;
}
static bool scalar_work(void) {
    if (!scalar.phase) return false;
    unsigned phase = scalar.phase;
    uint32_t start = esp_cpu_get_cycle_count();
    if (scalar.phase == SCALAR_COPY) {
        /* Scalar continuous profiles are limited to 256 samples. Copy the
         * complete window before the next bank is reclaimed; spreading this
         * small copy across polls can repeatedly abandon it before FFT work
         * even starts. FFT/encoding remain sliced in private SRAM. */
        spec_unpack(bank_ptr(scalar.bank), scalar.first, 0, spec_n);
        st.work[scalar.bank].pending = false;
        scalar.phase = SCALAR_FFT;
    } else if (scalar.phase == SCALAR_FFT) {
        for (unsigned budget = 0; budget < 32 && scalar.half; budget++) {
            unsigned a = scalar.group * scalar.half * 2 + scalar.offset, b = a + scalar.half;
            int32_t wr = dsps_fft_w_table_sc16[2 * scalar.group],
                    wi = dsps_fft_w_table_sc16[2 * scalar.group + 1];
            int32_t ar = fft_buf[2 * a], ai = fft_buf[2 * a + 1], br = fft_buf[2 * b],
                    bi = fft_buf[2 * b + 1];
            /* Each signed product fits int32_t. Only bits 16..31 of the
             * sum survive the output cast, so unsigned modular additions
             * give exactly the former int64_t result without carry chains. */
            uint32_t tr = (uint32_t)(wr * br) + (uint32_t)(wi * bi);
            uint32_t ti = (uint32_t)(wr * bi) - (uint32_t)(wi * br);
            uint32_t rr = (uint32_t)(ar * 32767) + 32767u, ri = (uint32_t)(ai * 32767) + 32767u;
            fft_buf[2 * a] = (int16_t)((rr + tr) >> 16);
            fft_buf[2 * a + 1] = (int16_t)((ri + ti) >> 16);
            fft_buf[2 * b] = (int16_t)((rr - tr) >> 16);
            fft_buf[2 * b + 1] = (int16_t)((ri - ti) >> 16);
            if (++scalar.offset == scalar.half) {
                scalar.offset = 0;
                if (++scalar.group == scalar.groups) {
                    scalar.group = 0;
                    scalar.groups *= 2;
                    scalar.half /= 2;
                }
            }
        }
        if (!scalar.half) {
            spec_remove_dc();
            scalar.emit = 0;
            scalar.phase = SCALAR_BINS;
        }
    } else if (scalar.phase == SCALAR_BINS) {
        unsigned end = scalar.emit + 32 < spec_n ? scalar.emit + 32 : spec_n;
        for (unsigned k = scalar.emit; k < end; k++) {
            int32_t re = fft_buf[2 * k], im = fft_buf[2 * k + 1];
            uint32_t power = spectrum_complex_power(re, im);
            if (st.cfg->max_hold) {
                uint32_t *maximum = (uint32_t *)accum;
                if (power > maximum[k]) maximum[k] = power;
            } else
                accum[k] += (float)power;
        }
        scalar.emit = end;
        if (end == spec_n) {
            if (!scalar.merged) scalar.frame_index = scalar.index;
            scalar.frame_pairs = (unsigned)(scalar.index + spec_n - scalar.frame_index);
            scalar.merged++;
            st.res->ffts++;
            scalar.phase = SCALAR_IDLE;
            if (txq_head == txq_tail || scalar.merged == 65535) scalar_flush();
        }
    } else if (scalar.phase == SCALAR_ENCODE) {
        unsigned end = scalar.emit + 32 < spec_n ? scalar.emit + 32 : spec_n;
        for (unsigned k = scalar.emit; k < end; k++) {
            frame_out[sizeof(spec_header_t) + bin_of[k]] =
                st.cfg->max_hold ? spectrum_power_code(((uint32_t *)accum)[k])
                                 : spectrum_mean_power_code(accum[k] * scalar.mean_scale);
            accum[k] = 0;
        }
        scalar.emit = end;
        if (end == spec_n) scalar.phase = SCALAR_FRAME;
    } else {
        ring_result_t *r = st.res;
        spec_header_t h = {.magic = SPEC_MAGIC,
                           .frame = r->frames + r->drops,
                           .pair_index = scalar.frame_index,
                           .pairs = scalar.frame_pairs,
                           .ffts = scalar.merged,
                           .flags = (st.cfg->max_hold ? 1 : 0) | (st.dropped ? 4 : 0) | 2,
                           .gain = scalar.gain,
                           .drops = r->drops > 65535 ? 65535 : r->drops,
                           .nfft_log2 = spec_log2,
                           .db_step = 2};
        memcpy(frame_out, &h, sizeof(h));
        unsigned len = sizeof(h) + spec_n;
        uint32_t crc = esp_rom_crc32_le(0, frame_out, len);
        memcpy(frame_out + len, &crc, 4);
        if (txq_push(frame_out, len + 4)) {
            r->frames++;
            st.last_ok = esp_timer_get_time();
            st.dropped = false;
        } else {
            r->drops++;
            st.dropped = true;
        }
        scalar.merged = 0;
        scalar.phase = SCALAR_IDLE;
    }
    uint32_t cycles = esp_cpu_get_cycle_count() - start;
    scalar_telemetry(cycles, scalar.phase == SCALAR_IDLE);
    cycles = esp_cpu_get_cycle_count() - start;
    if (cycles > scalar.cost[phase]) scalar.cost[phase] = cycles;
    if (cycles > st.res->work_max) st.res->work_max = cycles;
    return true;
}
