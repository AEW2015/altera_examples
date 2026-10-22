#ifndef WIFI64_DECODE_H
#define WIFI64_DECODE_H
/* Portable legacy OFDM54 DATA backend, no radio/host dependency.
 * Input: each symbol's 288 interleaved signed int16 LLRs in mapper bit order;
 * POSITIVE means bit1, zero is erasure. 48 subcarriers x6 bits. PHY upstream
 * must establish subcarrier/Gray labeling, polarity, pilots and frame length.
 * TX interleaver: i=18*(k%16)+k/16; j=3*(i/3)+(i+288-i/18)%3.
 * Mother order A0,B0,A1,B1,A2,B2, puncture 111001. K7 newest bit in bit0,
 * A mask0155, B mask0117 (reversed133/171). Initial state0; final UNFORCED:
 * DATA has scrambled pad after six overwritten-zero tail bits.
 * Caller owns workspace (25,712 bytes), so no unbounded stack/dynamic memory.
 * Puncture reference: https://www.mathworks.com/help/wireless-hdl/ug/convencpunc.html
 * Status bits are independent input/SERVICE/FCS/tail failures; zero means FCS
 * passed, not a measured BER. PSDU includes the four little-endian FCS bytes.
 * This implements no OFDM acquisition, FFT, equalizer or demapper.
 */
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#define W64D_MAX_PSDU 256u
#define W64D_MAX_SYMBOLS 10u
#define W64D_MAX_BITS (W64D_MAX_SYMBOLS*216u)
#define W64D_BAD_INPUT 1u
#define W64D_BAD_SERVICE 2u
#define W64D_BAD_FCS 4u
#define W64D_BAD_TAIL 8u

typedef struct {
    uint64_t trace[W64D_MAX_BITS];
    uint8_t bits[W64D_MAX_BITS];
    int16_t deinterleaved[W64D_MAX_SYMBOLS*288u];
    int32_t metric[64], next[64];
} w64d_workspace;
typedef struct {
    uint32_t status, symbols, decoded_bits, psdu_bytes;
    uint32_t crc_computed, crc_received, service_errors, tail_errors;
    uint8_t seed, final_state, psdu[W64D_MAX_PSDU];
} w64d_result;
static unsigned w64d_parity(unsigned x) {
    x ^= x>>4; x ^= x>>2; x ^= x>>1; return x&1u;
}
static unsigned w64d_scramble_step(unsigned *state) {
    unsigned f=((*state>>6)^(*state>>3))&1u;
    *state=((*state<<1)|f)&127u; return f;
}
static uint32_t w64d_crc32(const uint8_t *p, unsigned n) {
    uint32_t c=0xffffffffu;
    for(unsigned i=0;i<n;i++) {
        c ^= p[i];
        for(unsigned b=0;b<8;b++) c=(c>>1)^((0u-(c&1u))&0xedb88320u);
    }
    return ~c;
}
static int w64d_decode(const int16_t *llr, unsigned llr_count,
                      unsigned psdu_bytes, w64d_workspace *w, w64d_result *r) {
    static const unsigned keep[6]={1,1,1,0,0,1};
    if(!r) return -1;
    memset(r,0,sizeof(*r));
    if(!llr||!w||psdu_bytes<4||psdu_bytes>W64D_MAX_PSDU) {
        r->status=W64D_BAD_INPUT; return -1;
    }
    unsigned symbols=(16+8*psdu_bytes+6+215)/216;
    if(symbols>W64D_MAX_SYMBOLS||llr_count!=symbols*288) {
        r->status=W64D_BAD_INPUT; return -1;
    }
    unsigned nbits=symbols*216;
    r->symbols=symbols; r->decoded_bits=nbits; r->psdu_bytes=psdu_bytes;
    for(unsigned s=0;s<symbols;s++) for(unsigned k=0;k<288;k++) {
        unsigned i=18*(k%16)+k/16;
        unsigned j=3*(i/3)+(i+288-i/18)%3;
        w->deinterleaved[s*288+k]=llr[s*288+j];
    }
    for(unsigned s=0;s<64;s++) w->metric[s]=s ? -1000000000 : 0;
    unsigned consumed=0;
    for(unsigned t=0;t<nbits;t++) {
        int32_t v[2];
        for(unsigned q=0;q<2;q++) v[q]=keep[(2*t+q)%6] ? w->deinterleaved[consumed++] : 0;
        uint64_t decisions=0;
        for(unsigned next=0;next<64;next++) {
            unsigned input=next&1u, p0=next>>1, p1=p0|32;
            unsigned x0=(p0<<1)|input, x1=(p1<<1)|input;
            int32_t m0=w->metric[p0]+(w64d_parity(x0&0155)?v[0]:-v[0])+(w64d_parity(x0&0117)?v[1]:-v[1]);
            int32_t m1=w->metric[p1]+(w64d_parity(x1&0155)?v[0]:-v[0])+(w64d_parity(x1&0117)?v[1]:-v[1]);
            if(m1>m0) { w->next[next]=m1; decisions|=(uint64_t)1<<next; }
            else w->next[next]=m0;
        }
        w->trace[t]=decisions;
        memcpy(w->metric,w->next,sizeof(w->metric));
    }
    unsigned state=0;
    for(unsigned s=1;s<64;s++) if(w->metric[s]>w->metric[state]) state=s;
    r->final_state=(uint8_t)state;
    for(unsigned t=nbits;t-- >0;) {
        w->bits[t]=(uint8_t)(state&1u);
        state=(state>>1)|((unsigned)((w->trace[t]>>state)&1u)<<5);
    }
    unsigned tail=16+8*psdu_bytes;
    for(unsigned i=tail;i<tail+6;i++) r->tail_errors+=w->bits[i];
    if(r->tail_errors) r->status|=W64D_BAD_TAIL;
    for(unsigned seed=1;seed<128;seed++) {
        unsigned st=seed, errors=0;
        for(unsigned i=0;i<7;i++) errors+=w->bits[i]^w64d_scramble_step(&st);
        if(!errors) { r->seed=(uint8_t)seed; break; }
    }
    if(!r->seed) { r->status|=W64D_BAD_SERVICE; return 1; }
    unsigned st=r->seed;
    for(unsigned i=0;i<16+8*psdu_bytes;i++) {
        unsigned bit=w->bits[i]^w64d_scramble_step(&st);
        if(i<16) r->service_errors+=bit;
        else r->psdu[(i-16)/8]|=(uint8_t)(bit<<((i-16)%8));
    }
    if(r->service_errors) r->status|=W64D_BAD_SERVICE;
    unsigned f=psdu_bytes-4;
    r->crc_computed=w64d_crc32(r->psdu,f);
    r->crc_received=(uint32_t)r->psdu[f]|((uint32_t)r->psdu[f+1]<<8)|((uint32_t)r->psdu[f+2]<<16)|((uint32_t)r->psdu[f+3]<<24);
    if(r->crc_computed!=r->crc_received) r->status|=W64D_BAD_FCS;
    return r->status ? 1 : 0;
}
#endif
