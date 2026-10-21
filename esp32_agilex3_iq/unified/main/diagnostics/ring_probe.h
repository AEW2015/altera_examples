/* Bounded ring-mode investigation, never enabled in distributed firmware.
 * Uses only the existing reserved capture aperture. No additional SRAM banks
 * are handed to RF. The writer is stopped before returning to the scheduler. */
#ifdef RING_PROBE
#include "esp_cpu.h"
static bool ring_probe_command(const char *line) {
    unsigned rate;
    char extra;
    if (sscanf(line, "RINGPROBE %u %c", &rate, &extra) != 1) return false;
    if (rate > 6) {
        reply("ERR args\n");
        return true;
    }
    const uint32_t *data;
    unsigned elapsed;
    if (!spectrum_acquire(256, rate, &data, &elapsed)) return true;
#if CONFIG_IDF_TARGET_ESP32
    const uint32_t cr = DUMP_CTRL, wr = DUMP_STATUS, own_reg = DPORT_IRAM_DRAM_AHB_SEL_REG;
    const unsigned count = 16384;
    uint32_t owner = DPORT_REG_READ(own_reg),
             select = (owner & ~DPORT_MAC_DUMP_MODE_M) | (3 << DPORT_MAC_DUMP_MODE_S);
    uint32_t bits = rate == 6 ? BIT(16) : rate == 1 ? BIT(15) : 0;
#elif CONFIG_IDF_TARGET_ESP32S2
    const uint32_t cr = 0x60033d64, wr = 0x60033d68, own_reg = SRAM_OWNER_REG;
    const unsigned count = 8192;
    uint32_t owner = REG_READ(own_reg), select = (owner & ~15u) | 7u;
    uint32_t bits = rate == 6 ? BIT(16) : rate == 1 ? BIT(15) : 0;
#elif CONFIG_IDF_TARGET_ESP32C3
    const uint32_t cr = 0x60033d5c, wr = 0x60033d60, own_reg = SRAM_OWNER_REG;
    const unsigned count = 16384;
    uint32_t owner = REG_READ(own_reg), select = (owner & ~7u) | 2u | 8u;
    uint32_t bits = 0;
#elif CONFIG_IDF_TARGET_ESP32C5
    const uint32_t cr = 0x600a9004, wr = 0x600a9008, own_reg = SRAM_OWNER_REG;
    const unsigned count = 16384;
    uint32_t owner = REG_READ(own_reg), select = (owner & ~0xf00u) | 0x10200u;
    uint32_t bits = 0;
#elif CONFIG_IDF_TARGET_ESP32C6
    const uint32_t cr = 0x600a9004, wr = 0x600a9008, own_reg = SRAM_OWNER_REG;
    const unsigned count = 16384;
    uint32_t owner = REG_READ(own_reg), select = (owner & ~0xf00u) | 0x400u;
    uint32_t bits = 0;
#else
    reply("ERR unsupported\n");
    return true;
#endif
#if !CONFIG_IDF_TARGET_ESP32S31 && !CONFIG_IDF_TARGET_ESP32C61
    volatile uint32_t *probe = (volatile uint32_t *)data;
    for (unsigned j = 0; j < 8; j++) probe[j] = 0xa5c33c5a;
    unsigned irq = portSET_INTERRUPT_MASK_FROM_ISR();
    REG_WRITE(cr, 0);
    REG_WRITE(own_reg, select);
    (void)REG_READ(own_reg);
    uint32_t ctrl = bits | count | BIT(17);
    REG_WRITE(cr, ctrl | BIT(18));
    REG_WRITE(cr, ctrl);
    unsigned start = esp_cpu_get_cycle_count();
    REG_WRITE(cr, ctrl | BIT(31));
    unsigned prev = REG_READ(wr) & 0x1ffffu, first = prev, wraps = 0, changes = 0;
    while (esp_cpu_get_cycle_count() - start < CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ * 1000u) {
        unsigned cur = REG_READ(wr) & 0x1ffffu;
        if (cur != prev) changes++;
        if (cur < prev) wraps++;
        prev = cur;
    }
    unsigned live = 0, freed = 0;
    uint32_t live_words[4];
    for (unsigned j = 0; j < 4; j++) live_words[j] = probe[j];
    for (unsigned j = 0; j < 8; j++)
        if (probe[j] != 0xa5c33c5a) live++;
    REG_WRITE(cr, 0);
    REG_WRITE(own_reg, owner);
    (void)REG_READ(own_reg);
    for (unsigned j = 0; j < 8; j++)
        if (probe[j] != 0xa5c33c5a) freed++;
    portCLEAR_INTERRUPT_MASK_FROM_ISR(irq);
    char text[128];
    snprintf(text, sizeof(text), "RINGPROBE %u %u %u %u %u %u %u\n", rate, first, prev, wraps, changes, live,
             freed);
    reply(text);
    snprintf(text, sizeof(text), "RINGWORDS %08lx %08lx %08lx %08lx / %08lx %08lx %08lx %08lx\n",
             (unsigned long)live_words[0], (unsigned long)live_words[1], (unsigned long)live_words[2],
             (unsigned long)live_words[3], (unsigned long)probe[0], (unsigned long)probe[1],
             (unsigned long)probe[2], (unsigned long)probe[3]);
    reply(text);
#endif
    return true;
}
#endif
