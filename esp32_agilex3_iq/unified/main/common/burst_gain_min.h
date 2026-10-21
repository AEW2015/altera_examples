#pragma once
/* Lowest manual gain index a receiver accepts and advertises in LIMITS?. */
#if CONFIG_IDF_TARGET_ESP32H2
#define GAIN_MIN 2u /* indices 0 and 1 saturate like maximum gain */
#else
#define GAIN_MIN 0u
#endif
