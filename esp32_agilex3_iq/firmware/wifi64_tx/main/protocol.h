/* Native Wi-Fi packet fixture. No host-generated runtime waveform. */
#pragma once
#include <stdint.h>
#include <string.h>
#include <stdbool.h>
#define W64_PAYLOAD 64
#define W64_FRAME 88
static inline void w64_le32(uint8_t *p,uint32_t v){for(int k=0;k<4;k++)p[k]=(uint8_t)(v>>(8*k));}
static inline uint32_t w64_prng(uint32_t x){x^=x<<13;x^=x>>17;x^=x<<5;return x;}
static inline void w64_frame(uint8_t out[W64_FRAME],const uint8_t mac[6],uint32_t run,uint32_t packet,uint32_t seed){
 memset(out,0,W64_FRAME);out[0]=0x08; /* data, no DS, non-QoS */
 memset(out+4,0xff,6);memcpy(out+10,mac,6);memcpy(out+16,mac,6);
 out[22]=(uint8_t)((packet&15)<<4);out[23]=(uint8_t)(packet>>4);
 uint8_t *p=out+24;memcpy(p,"W64A",4);p[4]=1;p[5]=54;p[6]=W64_PAYLOAD;
 w64_le32(p+8,run);w64_le32(p+12,packet);w64_le32(p+16,seed);
 uint32_t x=seed^run^(packet*0x9e3779b9u);if(!x)x=1;
 for(unsigned i=20;i<W64_PAYLOAD;i++){x=w64_prng(x);p[i]=(uint8_t)x;}
}
static inline bool w64_valid_config(unsigned ch,unsigned power,unsigned count,unsigned gap){
 return ch>=1&&ch<=11&&power>=8&&power<=40&&count>=1&&count<=16&&gap>=2&&gap<=5;
}
