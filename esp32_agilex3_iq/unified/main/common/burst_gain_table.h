#pragma once
#include <stdbool.h>

void burst_gain_mirror(int index);
/* Original, PHY-calibrated baseband DC codes for a forced-gain entry. */
bool burst_gain_dc_codes(unsigned index, unsigned codes[2]);
/* Update only baseband DC fields in both gain tables and the unused slot 79.
 * The caller latches slot 79, then index, without releasing forced gain.
 * Requires a calibrated gain maximum below 79. Originals stay unchanged. */
bool burst_gain_dc_set(unsigned index, unsigned i, unsigned q);
