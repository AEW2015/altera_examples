#pragma once
/* Packing and sending a snapshot in IQ_BUFFER, shared by the burst receivers.
 * Include after defining IQ_BUFFER and send_bytes(). The packers work in place:
 * each output format is no larger than the 32-bit words it replaces. */
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include "esp_rom_crc.h"

static size_t packed_size(unsigned n) {
    return (n * 20u + 7u) / 8u;
}

/* IQ10 (CAP20): two complete samples occupy five bytes, an odd tail three. */
static void pack_iq(unsigned n) {
    uint8_t *p = (uint8_t *)IQ_BUFFER;
    for (unsigned j = 0; j < n; j += 2, p += 5) {
        uint32_t a = IQ_BUFFER[j] & 0xfffffu;
        uint32_t b = j + 1 < n ? IQ_BUFFER[j + 1] & 0xfffffu : 0;
        p[0] = a;
        p[1] = a >> 8;
        p[2] = (a >> 16) | (b << 4);
        if (j + 1 < n) {
            p[3] = b >> 4;
            p[4] = b >> 12;
        }
    }
}

/* IQ8 (CAP16): signed I then Q, the upper eight bits of each 10-bit field. */
static void pack_iq8(unsigned n) {
    uint8_t *p = (uint8_t *)IQ_BUFFER;
    for (unsigned j = 0; j < n; j++) {
        uint32_t w = IQ_BUFFER[j];
        p[2 * j] = (w >> 2) & 255;
        p[2 * j + 1] = (w >> 12) & 255;
    }
}

/* Format 16 = IQ8, 20 = IQ10, anything else = raw 32-bit words. */
static size_t wire_size(unsigned n, unsigned format) {
    return format == 16 ? n * 2 : format == 20 ? packed_size(n) : n * 4;
}

/* Pack n captured samples and send "DATA <n> <crc32> <us>" plus the payload. */
static bool burst_send_capture(unsigned n, unsigned format, uint32_t elapsed_us) {
    size_t bytes = wire_size(n, format);
    if (format == 16)
        pack_iq8(n);
    else if (format == 20)
        pack_iq(n);
    uint32_t crc = esp_rom_crc32_le(0, (const uint8_t *)IQ_BUFFER, bytes);
    char h[96];
    snprintf(h, sizeof(h), "DATA %u %08" PRIx32 " %" PRIu32 "\n", n, crc, elapsed_us);
    return send_bytes(h, strlen(h)) && send_bytes(IQ_BUFFER, bytes);
}
