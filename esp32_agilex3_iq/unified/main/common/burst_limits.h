/* Capability extension to protocol 6: numeric ranges are [min,max,step].
 * bandwidth adds its default MHz (0 = open); null means uncharacterized. */
#include "rx_bandwidth.h"
#include "burst_gain_min.h"
static bool limits_command(const char *line) {
    if (strcmp(line, "LIMITS?")) return false;
    char h[224];
    snprintf(h, sizeof(h),
             "LIMITS {\"gain\":[%u,%u,1],\"bandwidth\":"
#if CONFIG_IDF_TARGET_ESP32H2
             "[4,11,1,0]"
#elif CONFIG_IDF_TARGET_ESP32C2
             "[12,20,1,0]"
#elif CONFIG_IDF_TARGET_ESP32C3
             "[14,62,1,0]"
#elif CONFIG_IDF_TARGET_ESP32S2
             "[15,60,1,0]"
#elif CONFIG_IDF_TARGET_ESP32S3
             "[13,69,1,0]"
#elif CONFIG_IDF_TARGET_ESP32C6
             "[12,54,1,0]"
#elif CONFIG_IDF_TARGET_ESP32C5
             "[11,48,1,0]"
#elif CONFIG_IDF_TARGET_ESP32C61
             "[13,54,1,0]"
#else
             "null"
#endif
             ",\"rates\":["
#if CONFIG_IDF_TARGET_ESP32H2
             "32000000,16000000,10666667,6400000"
#elif CONFIG_IDF_TARGET_ESP32S3 || CONFIG_IDF_TARGET_ESP32S2 || CONFIG_IDF_TARGET_ESP32C2 ||                 \
    CONFIG_IDF_TARGET_ESP32C3 || CONFIG_IDF_TARGET_ESP32C6
             "80000000,40000000,16000000"
#else
             "80000000,40000000,20000000,10000000,8000000,4000000"
#endif
             "],\"bits\":[8,10]}\n",
             GAIN_MIN, gain_max());
    reply(h);
    return true;
}
