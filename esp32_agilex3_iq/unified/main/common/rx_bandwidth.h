#pragma once
#include <stdint.h>
/* C61: sensor-firmware/main/iq/modem.c noise-floor calibration, CBW20.
 * Approximate two-sided usable bandwidth, not a precision -3 dB specification.
 * S31 retains its separately characterized 21 MHz anchor.
 * S3 curve: measured noise spectrum at 2300 MHz, gain 75, 80 MS/s;
 * 12 snapshots/code, median windowed FFTs, approximate -3 dB full width. */
#if CONFIG_IDF_TARGET_ESP32H2
#define RX_BANDWIDTH_MIN 4u
#elif CONFIG_IDF_TARGET_ESP32C2
#define RX_BANDWIDTH_MIN 12u
#elif CONFIG_IDF_TARGET_ESP32C3
#define RX_BANDWIDTH_MIN 14u
#elif CONFIG_IDF_TARGET_ESP32S2
#define RX_BANDWIDTH_MIN 15u
#elif CONFIG_IDF_TARGET_ESP32C5
#define RX_BANDWIDTH_MIN 11u
#elif CONFIG_IDF_TARGET_ESP32 || CONFIG_IDF_TARGET_ESP32C6
#define RX_BANDWIDTH_MIN 12u
#else
#define RX_BANDWIDTH_MIN 13u
#endif
#if CONFIG_IDF_TARGET_ESP32H2
#define RX_BANDWIDTH_MAX 11u
#elif CONFIG_IDF_TARGET_ESP32C2
#define RX_BANDWIDTH_MAX 20u
#elif CONFIG_IDF_TARGET_ESP32C3
#define RX_BANDWIDTH_MAX 62u
#elif CONFIG_IDF_TARGET_ESP32S2
#define RX_BANDWIDTH_MAX 60u
#elif CONFIG_IDF_TARGET_ESP32
#define RX_BANDWIDTH_MAX 67u
#elif CONFIG_IDF_TARGET_ESP32C5
#define RX_BANDWIDTH_MAX 48u
#elif CONFIG_IDF_TARGET_ESP32S3
#define RX_BANDWIDTH_MAX 69u
#else
#define RX_BANDWIDTH_MAX 54u
#endif
/* C5 mode 1 runs the wide PHY path while retaining the RX0 cap DAC.
 * Modes 2/3 select the other analog branch and bypass this capacitor pair.
 * A complete channel setup is required: individual digital register writes
 * do not update the PHY's PBUS analog-control tables. */
static inline unsigned rx_bandwidth_phy_mode(unsigned mhz) {
#if CONFIG_IDF_TARGET_ESP32C5
    return !mhz || mhz > 23u ? 1u : 0u;
#else
    (void)mhz;
    return 0u;
#endif
}
typedef struct {
    uint8_t dcap, mhz;
} rx_bandwidth_point_t;
static inline uint8_t rx_bandwidth_dcap(unsigned mhz) {
    static const rx_bandwidth_point_t cal[] = {
#if CONFIG_IDF_TARGET_ESP32H2
        /* BBTOP 0, bits 6:0; 32 MS/s, gain 35, 2300/2412/2484 MHz.
         * Median noise spectra, 24 captures/code; approximate full -3 dB width. */
        {0, 11}, {8, 10}, {16, 9}, {24, 8}, {32, 7},
        {48, 6}, {80, 5}, {112, 4}
#elif CONFIG_IDF_TARGET_ESP32C2
        /* BBTOP 4/5; 80 MS/s, gain 75, 2300/2484 MHz, 24 captures/code.
         * Conservative full widths; low codes have a non-flat response. */
        {32, 20},
        {40, 17},
        {48, 14},
        {56, 13},
        {63, 12}
#elif CONFIG_IDF_TARGET_ESP32C3
        /* BBTOP 4/5, 2484 MHz, gain 79, 80 MS/s; median noise spectra, 24 captures/code. */
        {0, 62},  {4, 50},  {8, 45},  {12, 39}, {16, 34}, {24, 27}, {32, 23},
        {40, 20}, {48, 18}, {56, 16}, {60, 15}, {63, 14}
#elif CONFIG_IDF_TARGET_ESP32S2
        /* Measured S2 noise FFT full widths; code 0 remains wide open. */
        {8, 60},  {12, 49}, {16, 41}, {24, 32}, {32, 26},
        {40, 22}, {48, 19}, {56, 16}, {63, 15}
#elif CONFIG_IDF_TARGET_ESP32
        /* Original ESP32: seven-bit BBTOP 1/2, 2472 MHz, gain 72, IQ10.
         * Code 0 is wider than the measured span. Numeric max uses code 8. */
        {8, 67},  {12, 55}, {16, 48}, {24, 38},  {32, 32}, {48, 25},
        {64, 20}, {80, 17}, {96, 15}, {112, 14}, {127, 12}
#elif CONFIG_IDF_TARGET_ESP32C5
        /* C5: BBTOP 6/7; median noise FFTs at 2300/5500 MHz,
         * 80 MS/s IQ10, PHY channel mode 0. Approximate full width. */
        {0, 23},  {4, 22},  {8, 21},  {12, 20}, {16, 18}, {24, 16},
        {32, 15}, {40, 13}, {48, 12}, {60, 11}
#elif CONFIG_IDF_TARGET_ESP32C6
        /* C6: median noise FFTs at 2484 MHz, gain 79, 80 MS/s. */
        {0, 54},  {4, 48},  {8, 39},  {12, 33}, {16, 28}, {24, 23},
        {32, 20}, {40, 17}, {48, 15}, {60, 12}
#elif CONFIG_IDF_TARGET_ESP32S3
        {0, 69},  {4, 51},  {8, 45}, {16, 33}, {24, 25},
        {32, 21}, {48, 16}, {60, 13}
#else
        {0, 54},  {8, 36},
        {16, 30},
#if CONFIG_IDF_TARGET_ESP32S31
        {28, 21},
#else
        {24, 21},
#endif
        {32, 18}, {48, 15},
        {60, 13}
#endif
    };
    const rx_bandwidth_point_t *curve = cal;
    unsigned count = sizeof(cal) / sizeof(cal[0]);
#if CONFIG_IDF_TARGET_ESP32C5
    /* Mode 1: noise sweeps at 2300/5500 MHz, checked with a fixed RF tone.
     * Approximate two-sided widths; retain mode 0 for the 11–23 MHz range. */
    static const rx_bandwidth_point_t wide[] = {{0, 48},  {4, 45},  {8, 42},  {12, 40}, {16, 37}, {24, 34},
                                                {32, 30}, {40, 27}, {48, 25}, {56, 23}, {60, 22}};
    if (rx_bandwidth_phy_mode(mhz)) {
        curve = wide;
        count = sizeof(wide) / sizeof(wide[0]);
    }
#endif
    if (!mhz) return 0;
    if (mhz >= curve[0].mhz) return curve[0].dcap;
    if (mhz <= curve[count - 1].mhz) return curve[count - 1].dcap;
    for (unsigned i = 1; i < count; i++)
        if (mhz >= curve[i].mhz) {
            unsigned span = curve[i - 1].mhz - curve[i].mhz;
            return curve[i - 1].dcap +
                   ((curve[i].dcap - curve[i - 1].dcap) * (curve[i - 1].mhz - mhz) + span / 2) / span;
        }
    return curve[count - 1].dcap;
}
