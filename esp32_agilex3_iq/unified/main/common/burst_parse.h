#pragma once
#include <stdbool.h>

/* Strict decimal parsing for serial commands. sscanf("%u") silently accepts
 * signs, overflow and (with optional fields) trailing text; these helpers
 * reject all of them before a command touches receiver state. */

/* Parse up to `max` space-separated unsigned decimal fields. Returns the
 * number of fields, or -1 for malformed text, overflow or excess fields. */
static inline int burst_parse_uints(const char *s, unsigned *v, int max) {
    int n = 0;
    for (;;) {
        while (*s == ' ') s++;
        if (!*s) return n;
        if (n == max || *s < '0' || *s > '9') return -1;
        unsigned x = 0;
        do {
            unsigned d = (unsigned)(*s++ - '0');
            if (x > (~0u - d) / 10u) return -1;
            x = x * 10u + d;
        } while (*s >= '0' && *s <= '9');
        if (*s && *s != ' ') return -1;
        v[n++] = x;
    }
}

/* Parse exactly one optionally signed decimal integer within [low, high]. */
static inline bool burst_parse_int(const char *s, int low, int high, int *out) {
    while (*s == ' ') s++;
    bool negative = *s == '-';
    if (*s == '-' || *s == '+') s++;
    if (*s < '0' || *s > '9') return false;
    unsigned v;
    if (burst_parse_uints(s, &v, 1) != 1) return false;
    long long x = negative ? -(long long)v : (long long)v;
    if (x < low || x > high) return false;
    *out = (int)x;
    return true;
}
