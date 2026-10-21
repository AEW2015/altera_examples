#pragma once
#include <stdbool.h>

/* C61/S31 RFPLL capacitor: 0x62:1[7:0], 0x62:2[6]. The vendor
 * calibration can stop short of the required code below the Wi-Fi band.
 * Recover a failed calibration using the PLL's own comparator, without
 * changing the programmed frequency or applying any sample processing. */
#if !CONFIG_IDF_TARGET_ESP32C61 && !CONFIG_IDF_TARGET_ESP32S31
#error Unqualified PLL capacitor layout
#endif
extern unsigned phy_i2c_readReg(unsigned, unsigned, unsigned);
extern void phy_i2c_writeReg(unsigned, unsigned, unsigned, unsigned);

static unsigned rx_pll_status(void) {
    return (phy_i2c_readReg(0x62, 1, 12) >> 2) & 3u;
}

static unsigned rx_pll_probe(unsigned cap, unsigned reg2) {
    phy_i2c_writeReg(0x62, 1, 1, cap & 255u);
    phy_i2c_writeReg(0x62, 1, 2, (reg2 & ~64u) | ((cap >> 2) & 64u));
    esp_rom_delay_us(50);
    return rx_pll_status();
}

static bool rx_pll_recover(unsigned mhz) {
    if (mhz >= 2400 || rx_pll_status() == 0) return true;
    const unsigned reg1 = phy_i2c_readReg(0x62, 1, 1);
    const unsigned reg2 = phy_i2c_readReg(0x62, 1, 2);
    const unsigned reg11 = phy_i2c_readReg(0x62, 1, 11);
    phy_i2c_writeReg(0x62, 1, 11, reg11 | 64u); /* Manual capacitor. */

    /* Status 1 needs more capacitance, 2 less; 0 is the lock window.
     * Find both edges and choose the middle for drift margin. Every loop
     * is bounded by the nine-bit capacitor range. */
    unsigned low = 0, high = 512;
    while (low < high) {
        unsigned mid = low + (high - low) / 2;
        unsigned status = rx_pll_probe(mid, reg2);
        if (status == 3) goto restore;
        if (status == 1)
            low = mid + 1;
        else
            high = mid;
    }
    if (low == 512 || rx_pll_probe(low, reg2) != 0) goto restore;
    const unsigned first = low;
    high = 512;
    while (low < high) {
        unsigned mid = low + (high - low) / 2;
        unsigned status = rx_pll_probe(mid, reg2);
        if (status == 1 || status == 3) goto restore;
        if (status == 0)
            low = mid + 1;
        else
            high = mid;
    }
    if (rx_pll_probe(first + (low - first - 1) / 2, reg2) != 0) goto restore;
    for (unsigned i = 0; i < 3; i++) {
        esp_rom_delay_us(50);
        if (rx_pll_status() != 0) goto restore;
    }
    return true;

restore:
    phy_i2c_writeReg(0x62, 1, 1, reg1);
    phy_i2c_writeReg(0x62, 1, 2, reg2);
    phy_i2c_writeReg(0x62, 1, 11, reg11);
    return false;
}
