#ifndef WIFI_INVENTORY_H
#define WIFI_INVENTORY_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
typedef struct {
    uint8_t bssid[6], ssid[32], ssid_len, channel;
    const char *security;
} wifi_advertisement_t;
/* Frame excludes the four-byte FCS. Accepts beacon/probe-response management frames. */
bool wifi_parse_advertisement(const uint8_t *frame, size_t len, wifi_advertisement_t *out);
#endif
