/* Opt-in dump-engine investigation for S2 and S3 (S2_RF_PROBE, S3_RF_PROBE).
 * Never package a probe build. Include after prepare_rx(). */
#if defined(S2_RF_PROBE) || defined(S3_RF_PROBE)
static bool dump_probe_command(char *line) {
    unsigned n, rate;
    char extra;
    if (!strcmp(line, "WORDS?")) {
        char h[120];
        snprintf(h, sizeof(h), "WORDS %08x %08x %08x %08x OWNER %08x\n", (unsigned)IQ_BUFFER[0],
                 (unsigned)IQ_BUFFER[1], (unsigned)IQ_BUFFER[2], (unsigned)IQ_BUFFER[3],
                 (unsigned)REG_READ(SRAM_OWNER_REG));
        reply(h);
    } else if (!strcmp(line, "MEMTEST")) {
        for (unsigned j = 0; j < IQ_WORDS; j++) IQ_BUFFER[j] = 0x12345678u + j;
        reply("OK\n");
    } else if (sscanf(line, "RXWIDE %u %c", &n, &extra) == 1 && n < 2) {
        rx_wide = n;
        reply("OK\n");
    } else if (sscanf(line, "RXPREP %u %c", &n, &extra) == 1 && n < 4) {
        rx_prep = n;
        rx_ready = false;
        reply("OK\n");
    } else if (sscanf(line, "RXPACK %u %u %c", &n, &rate, &extra) == 2 && n <= 60 && rate <= 1) {
        rx_pack = n;
        rx_agc = rate;
        reply("OK\n");
    } else if (sscanf(line, "RXSRC %u %c", &n, &extra) == 1 && n < 256) {
        rx_source = n;
        reply("OK\n");
    } else if (sscanf(line, "RXMODE %u %c", &n, &extra) == 1 && n < 8) {
        rx_mode = n;
        reply("OK\n");
    } else if (sscanf(line, "RXFLAG %u %c", &n, &extra) == 1 && n < 2) {
        rx_flag = n;
        reply("OK\n");
    } else if (sscanf(line, "RXCLOCK %u %c", &n, &extra) == 1 && n < 2) {
        rx_clock = n;
        reply("OK\n");
    } else if (!strcmp(line, "RXREGS?")) {
        for (unsigned a = 0x60033d50; a <= 0x60033d98; a += 4) {
            char h[60];
            snprintf(h, sizeof(h), "REG %08x %08x\n", a, (unsigned)REG_READ(a));
            reply(h);
        }
        reply("END\n");
    } else if (!strcmp(line, "RFREG?")) {
        /* Dump control, write index and the word after; the S2's sit 8 bytes higher. */
#if CONFIG_IDF_TARGET_ESP32S2
        const uint32_t ctrl = 0x60033d64u;
#else
        const uint32_t ctrl = 0x60033d5cu;
#endif
        char h[120];
        snprintf(h, sizeof(h), "RFREG %08x %08x %08x\n", (unsigned)REG_READ(ctrl),
                 (unsigned)REG_READ(ctrl + 4), (unsigned)REG_READ(ctrl + 8));
        reply(h);
    } else if (sscanf(line, "FREQEX %u %c", &n, &extra) == 1 && n >= 100 && n <= 6000) {
        frequency_mhz = n;
        rx_ready = false;
        prepare_rx();
        reply("OK\n");
#if CONFIG_IDF_TARGET_ESP32S2
    } else if (sscanf(line, "ANAREAD %u %u %c", &n, &rate, &extra) == 2 && n < 2 && rate < 32) {
        char h[64];
        snprintf(h, sizeof(h), "ANA %u %u %u\n", n, rate, rom_chip_i2c_readReg(0x67, n, rate));
        reply(h);
    } else if (!strcmp(line, "GAINREG?")) {
        char h[64];
        snprintf(h, sizeof(h), "GAINREG %08x\n", (unsigned)REG_READ(0x6001c02c));
        reply(h);
#endif
    } else
        return false;
    return true;
}
#endif
