#pragma once
/* Commands that every snapshot receiver answers the same way. Include after
 * defining BURST_ID (e.g. "C3SDR"), BURST_MAX_RATE (highest CAP rate code),
 * IQ_WORDS, and providing frequency_mhz, rx_ready, frequency_valid(), prepare_rx(),
 * reply() and capture(samples, rate, format). See docs/protocol.md. */
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "rx_tuning.h"

/* Returns true if the line was one of these commands (answered or rejected). */
static bool burst_common_command(char *line) {
    unsigned n, rate, format, repeats;
    char extra;
    uint64_t nonce;
    bool iq8 = false;
    /* CAP16 is CAP20's capture packed as 8-bit I/Q. */
    if (!strncmp(line, "CAP16 ", 6)) {
        memcpy(line, "CAP20", 5);
        iq8 = true;
    }
    if (!strcmp(line, "TRANSPORT?")) {
        char answer[64];
        snprintf(answer, sizeof(answer), "TRANSPORT %s %u\n",
                 burst_serial_port() == BURST_SERIAL_UART ? "UART" : "USB", burst_serial_baud());
        reply(answer);
    } else if (sscanf(line, "SYNC %" SCNu64 " %c", &nonce, &extra) == 1) {
        char answer[48];
        snprintf(answer, sizeof(answer), "SYNC %" PRIu64 "\n", nonce);
        reply(answer);
    } else if (!strcmp(line, "INFO")) {
        char answer[48];
        snprintf(answer, sizeof(answer), BURST_ID " 6 burst %u\n", (unsigned)IQ_WORDS);
        reply(answer);
    } else if (!strcmp(line, "RANGE?")) {
        char answer[64];
        snprintf(answer, sizeof(answer), "RANGE %u %u 1\n", RX_FREQ_MIN, RX_FREQ_MAX);
        reply(answer);
    } else if (sscanf(line, "FREQ %u %c", &n, &extra) == 1 && frequency_valid(n)) {
        frequency_mhz = n;
        rx_ready = false;
        prepare_rx();
        reply("OK\n");
    } else if (sscanf(line, "RXRUN %u %u %u %u %c", &n, &rate, &repeats, &format, &extra) == 4 && n >= 256 &&
               n <= IQ_WORDS && rate <= BURST_MAX_RATE && repeats > 0 && repeats <= 1000 &&
               (format == 16 || format == 20)) {
        /* A series of separate captures, with RF gaps during each transfer. */
        bool ok = true;
        for (unsigned j = 0; j < repeats && ok; j++) {
            ok = capture(n, rate, format);
            vTaskDelay(1);
        }
        if (ok) reply("END\n");
    } else if (((!strncmp(line, "CAP ", 4) && sscanf(line, "CAP %u %u %c", &n, &rate, &extra) == 2) ||
                (!strncmp(line, "CAP20 ", 6) && sscanf(line, "CAP20 %u %u %c", &n, &rate, &extra) == 2)) &&
               n >= 256 && n <= IQ_WORDS && rate <= BURST_MAX_RATE) {
        capture(n, rate, !strncmp(line, "CAP20 ", 6) ? (iq8 ? 16 : 20) : 0);
    } else
        return false;
    return true;
}
