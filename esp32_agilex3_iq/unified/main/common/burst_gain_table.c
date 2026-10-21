/* Keep calibrated C61/S31 gain words, including the high-table originals.
 * Restore calibrated high-table slots on AGC; slots above the high-table
 * maximum are unused by AGC but must still be mirrored for forced gain.
 * About 2 KiB; no sample buffers or heap allocations. */
#include <stdint.h>
#include <stdbool.h>
#include "burst_gain_table.h"
static uint32_t words[160][3];
static bool valid[160];
static int mirrored = -1;
static int corrected = -1;
extern void __real_phy_write_gain_mem(uint32_t, uint32_t, uint32_t, uint32_t);
void __wrap_phy_write_gain_mem(uint32_t a, uint32_t b, uint32_t c, uint32_t index) {
    if (index < 160) {
        words[index][0] = a;
        words[index][1] = b;
        words[index][2] = c;
        valid[index] = true;
    }
    __real_phy_write_gain_mem(a, b, c, index);
}
void burst_gain_mirror(int index) {
    if (corrected >= 0) {
        unsigned low = (unsigned)corrected;
        __real_phy_write_gain_mem(words[low][0], words[low][1], words[low][2], low);
        corrected = -1;
    }
    if (mirrored >= 0) {
        unsigned high = (unsigned)mirrored + 80;
        if (valid[high]) __real_phy_write_gain_mem(words[high][0], words[high][1], words[high][2], high);
        mirrored = -1;
    }
    if (index >= 0 && index < 80 && valid[index]) {
        __real_phy_write_gain_mem(words[index][0], words[index][1], words[index][2], index + 80);
        mirrored = index;
    }
}

bool burst_gain_dc_codes(unsigned index, unsigned codes[2]) {
    if (index >= 79 || !valid[index] || mirrored != (int)index) return false;
    codes[0] = ((words[index][1] & 255u) << 1) | (words[index][0] >> 31);
    codes[1] = (words[index][0] >> 13) & 511u;
    return true;
}

bool burst_gain_dc_set(unsigned index, unsigned i, unsigned q) {
    if (index >= 79 || !valid[index] || mirrored != (int)index || i > 511 || q > 511) return false;
    /* Keep RF DC, RF/baseband gain and native I/Q calibration intact. */
    uint32_t a = (words[index][0] & ~((511u << 13) | (1u << 31))) | (q << 13) | ((i & 1u) << 31);
    uint32_t b = (words[index][1] & ~255u) | (i >> 1), c = words[index][2];
    const unsigned slots[] = {index, index + 80, 79, 159};
    for (unsigned j = 0; j < 4; j++) __real_phy_write_gain_mem(a, b, c, slots[j]);
    corrected = (int)index;
    return true;
}
