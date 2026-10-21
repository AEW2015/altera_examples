/* Opt-in, volatile RF filter investigation. No arbitrary address writes.
 * Each field is backed up before its first write; FRESET restores it.
 * The caller must restore before retuning. Never package a probe build. */
#ifdef FILTER_REGISTER_PROBE
#if CONFIG_IDF_TARGET_ESP32C5 || CONFIG_IDF_TARGET_ESP32C61
extern unsigned phy_chip_i2c_readReg(unsigned, unsigned, unsigned);
extern void phy_i2c_writeReg(unsigned, unsigned, unsigned, unsigned);
#define filter_i2c_read(r)     phy_chip_i2c_readReg(0x67, 1, (r))
#define filter_i2c_write(r, v) phy_i2c_writeReg(0x67, 1, (r), (v))
static const uint32_t filter_regs[] = {0x600a0430, 0x600a7904, 0x600a7074, 0x600a0874};
static const uint32_t filter_masks[] = {0x003c0000, 0x00400007, 0x00002000, 0x00070000};
static bool filter_cap_allowed(unsigned r) {
    return r >= 6 && r <= 21;
}
static unsigned filter_control_mask(unsigned r) {
    return r == 5 ? 0x68 : r == 29 ? 0x0c : 0;
}
#else
extern unsigned rom_chip_i2c_readReg(unsigned, unsigned, unsigned);
extern void rom_chip_i2c_writeReg(unsigned, unsigned, unsigned, unsigned);
#define filter_i2c_read(r)     rom_chip_i2c_readReg(0x67, 0, (r))
#define filter_i2c_write(r, v) rom_chip_i2c_writeReg(0x67, 0, (r), (v))
static const uint32_t filter_regs[] = {0x6001cd04, 0x6001cd08, 0x6001c074, 0x60006100};
static const uint32_t filter_masks[] = {0x10000007, 0x10000007, 0x00002000, 0x00070000};
static bool filter_cap_allowed(unsigned r) {
    return (r >= 4 && r <= 7) || (r >= 12 && r <= 15) || (r >= 20 && r <= 23) || (r >= 28 && r <= 31);
}
static unsigned filter_control_mask(unsigned r) {
    return r == 2 ? 0x0c : 0;
}
#endif
static uint32_t filter_saved[4];
static uint8_t filter_ana_saved[64];
static bool filter_changed[4], filter_ana_changed[64];
static bool filter_probe_command(const char *line) {
    unsigned a, m, v;
    char extra, answer[96];
    if (!strcmp(line, "FRESET")) {
        for (unsigned j = 0; j < 4; j++)
            if (filter_changed[j]) {
                REG_WRITE(filter_regs[j], filter_saved[j]);
                filter_changed[j] = false;
            }
        for (unsigned j = 0; j < 64; j++)
            if (filter_ana_changed[j]) {
                filter_i2c_write(j, filter_ana_saved[j]);
                filter_ana_changed[j] = false;
            }
        reply("OK\n");
        return true;
    }
    if (sscanf(line, "FREAD %x %c", &a, &extra) == 1) {
        for (unsigned j = 0; j < 4; j++)
            if (a == filter_regs[j]) {
                snprintf(answer, sizeof(answer), "FREG %08x %08x\n", a, (unsigned)REG_READ(a));
                reply(answer);
                return true;
            }
    }
    if (sscanf(line, "FREG %x %x %x %c", &a, &m, &v, &extra) == 3) {
        for (unsigned j = 0; j < 4; j++)
            if (a == filter_regs[j] && m && !(m & ~filter_masks[j]) && !(v & ~m)) {
                prepare_rx();
                if (!filter_changed[j]) {
                    filter_saved[j] = REG_READ(a);
                    filter_changed[j] = true;
                }
                REG_WRITE(a, (REG_READ(a) & ~m) | v);
                reply("OK\n");
                return true;
            }
    }
    if (sscanf(line, "FANA? %u %c", &a, &extra) == 1 && a < 64) {
        snprintf(answer, sizeof(answer), "FANA %u %u\n", a, filter_i2c_read(a));
        reply(answer);
        return true;
    }
    if (sscanf(line, "FIMASK %u %x %x %c", &a, &m, &v, &extra) == 3 && a < 64 && m &&
        !(m & ~filter_control_mask(a)) && !(v & ~m)) {
        prepare_rx();
        unsigned old = filter_i2c_read(a);
        if (!filter_ana_changed[a]) {
            filter_ana_saved[a] = old;
            filter_ana_changed[a] = true;
        }
        filter_i2c_write(a, (old & ~m) | v);
        reply("OK\n");
        return true;
    }
    if (sscanf(line, "FANA %u %u %c", &a, &v, &extra) == 2 && filter_cap_allowed(a) && v < 64) {
        prepare_rx();
        unsigned old = filter_i2c_read(a);
        if (!filter_ana_changed[a]) {
            filter_ana_saved[a] = old;
            filter_ana_changed[a] = true;
        }
        filter_i2c_write(a, (old & ~63u) | v);
        reply("OK\n");
        return true;
    }
    if (line[0] == 'F' && (!strncmp(line, "FREG", 4) || !strncmp(line, "FIMASK", 6) ||
                           !strncmp(line, "FANA", 4) || !strncmp(line, "FREAD", 5))) {
        reply("ERR filter_probe_field\n");
        return true;
    }
    return false;
}
#endif
