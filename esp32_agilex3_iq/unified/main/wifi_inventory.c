#include "wifi_inventory.h"
#include <string.h>
static unsigned le16(const uint8_t *p) { return p[0] | ((unsigned)p[1]<<8); }
static const char *rsn_security(const uint8_t *p, size_t n)
{
    if (n < 8 || le16(p) != 1) return "RSN";
    size_t at=6;
    unsigned count=le16(p+at); at+=2;
    if (count > (n-at)/4) return "RSN";
    at += count*4;
    if (n-at < 2) return "RSN";
    count=le16(p+at); at+=2;
    if (count > (n-at)/4) return "RSN";
    bool psk=false, sae=false, owe=false;
    for (unsigned i=0; i<count; ++i,at+=4) {
        if (p[at] || p[at+1]!=0x0f || p[at+2]!=0xac) continue;
        if (p[at+3]==2 || p[at+3]==4 || p[at+3]==6) psk=true;
        if (p[at+3]==8 || p[at+3]==9) sae=true;
        if (p[at+3]==18) owe=true;
    }
    if (sae && psk) return "WPA2-WPA3";
    if (sae) return "WPA3";
    if (psk) return "WPA2";
    if (owe) return "OWE";
    return "RSN-other";
}
bool wifi_parse_advertisement(const uint8_t *frame, size_t len, wifi_advertisement_t *out)
{
    if (!frame || !out || len < 36 || (frame[0]!=0x80 && frame[0]!=0x50) ||
        (frame[1]&3)) return false;
    memset(out,0,sizeof(*out));
    memcpy(out->bssid,frame+16,6);
    out->security=(frame[34]&0x10) ? "Privacy-unspecified" : "Open";
    bool ssid_seen=false, rsn_seen=false;
    for (size_t pos=36; pos<len;) {
        if (len-pos < 2) return false;
        unsigned tag=frame[pos], n=frame[pos+1]; pos+=2;
        if (n > len-pos) return false;
        const uint8_t *value=frame+pos;
        if (tag==0 && !ssid_seen) {
            if (n>32) return false;
            memcpy(out->ssid,value,n); out->ssid_len=n; ssid_seen=true;
        } else if (tag==3 && n==1) out->channel=value[0];
        else if (tag==61 && n>=1 && !out->channel) out->channel=value[0];
        else if (tag==48) { out->security=rsn_security(value,n); rsn_seen=true; }
        else if (tag==221 && n>=4 && !rsn_seen &&
                 !memcmp(value,"\x00\x50\xf2\x01",4)) out->security="WPA";
        pos+=n;
    }
    return ssid_seen;
}
