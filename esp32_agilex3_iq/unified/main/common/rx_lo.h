#pragma once
#include <stdbool.h>

/* Qualified on ESP32, S2, S3, C2, C3 and C6: plan B divides the ordinary receive LO by
 * 6/5. Keep the vendor calibration in normal mode and select the final mode
 * only after RX setup. The frequency command always names the receive LO.
 * 1842..2209 MHz maps into the conservative 2210..2651 MHz PLL envelope;
 * other requests retain the existing direct-PLL tuning attempt. */
typedef struct {
    unsigned mhz;
    int offset_khz;
    bool alternate;
} rx_lo_plan_t;

static inline rx_lo_plan_t rx_lo_plan(unsigned mhz) {
    bool alternate = mhz >= 1842 && mhz < 2210;
    unsigned khz = mhz * (alternate ? 1200u : 1000u);
    return (rx_lo_plan_t){khz / 1000u, (int)(khz % 1000u), alternate};
}

/* Selector locations differ between radio generations. Extend these aliases
 * only after checking the register and LO ratio with an external RF source. */
#if CONFIG_IDF_TARGET_ESP32
extern unsigned ram_chip_i2c_readReg(unsigned, unsigned, unsigned);
extern void ram_chip_i2c_writeReg(unsigned, unsigned, unsigned, unsigned);
#define rx_lo_read  ram_chip_i2c_readReg
#define rx_lo_write ram_chip_i2c_writeReg
#define RX_LO_HOST  4
#elif CONFIG_IDF_TARGET_ESP32C3
extern unsigned rom1_chip_i2c_readReg(unsigned, unsigned, unsigned);
extern void rom1_chip_i2c_writeReg(unsigned, unsigned, unsigned, unsigned);
#define rx_lo_read  rom1_chip_i2c_readReg
#define rx_lo_write rom1_chip_i2c_writeReg
#elif CONFIG_IDF_TARGET_ESP32S2 || CONFIG_IDF_TARGET_ESP32S3 || CONFIG_IDF_TARGET_ESP32C2 ||                 \
    CONFIG_IDF_TARGET_ESP32C6
extern unsigned rom_chip_i2c_readReg(unsigned, unsigned, unsigned);
extern void rom_chip_i2c_writeReg(unsigned, unsigned, unsigned, unsigned);
#define rx_lo_read  rom_chip_i2c_readReg
#define rx_lo_write rom_chip_i2c_writeReg
#else
#error Unqualified alternate LO selector
#endif

#ifndef RX_LO_HOST
#define RX_LO_HOST 1
#endif

#if CONFIG_IDF_TARGET_ESP32C2 || CONFIG_IDF_TARGET_ESP32C6
#define RX_LO_BLOCK 0x62
#define RX_LO_REG   16
#define RX_LO_MASK  0x08u
#else
#define RX_LO_BLOCK 0x65
#define RX_LO_REG   0
#define RX_LO_MASK  0x10u
#endif

static inline bool rx_lo_select(bool alternate) {
    unsigned old = rx_lo_read(RX_LO_BLOCK, RX_LO_HOST, RX_LO_REG);
    unsigned value = (old & ~RX_LO_MASK) | (alternate ? RX_LO_MASK : 0u);
    if (value != old) rx_lo_write(RX_LO_BLOCK, RX_LO_HOST, RX_LO_REG, value);
    return value != old;
}
