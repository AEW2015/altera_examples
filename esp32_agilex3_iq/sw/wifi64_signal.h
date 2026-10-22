#ifndef ATUM_WIFI64_SIGNAL_H
#define ATUM_WIFI64_SIGNAL_H
/* Portable Nios software L-SIG decoder, not acquisition or an RTL accelerator.
 * Input: 48 equalized/pilot-corrected BPSK LLRs in ascending DATA-carrier order;
 * positive favors1, zero erasure. SIGNAL uses unpunctured K7 rate1/2 and has
 * no scrambling. Inverse interleaver: rx[3*(k%16)+k/16]. Newest register bit0,
 * left shift, A/B masks0155/0117, initial/final state0, full24-bit traceback.
 * RATE code is FIRST TRANSMITTED BIT AS BIT0: 6Mb/s=0xB,48=0x8,54=0xC.
 * This differs from the common printed MSB-first field0xD/0x1/0x3.
 * Independent implementation references (no upstream code incorporated):
 * https://github.com/bastibl/gr-ieee802-11/blob/maint-3.10/lib/signal_field_impl.cc
 * https://github.com/bastibl/gr-ieee802-11/blob/maint-3.10/lib/frame_equalizer_impl.cc
 * Strict qualification rejects a stronger nonterminated survivor as BAD_TAIL;
 * expose its metric gap so this is distinguishable from a decoded parity error.
 * DATA48 metadata is recognized, but the separate current DATA backend is54only.
 */
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#define W64S_BAD_INPUT 1u
#define W64S_NO_ENERGY 2u
#define W64S_BAD_RESERVED 4u
#define W64S_BAD_PARITY 8u
#define W64S_BAD_TAIL 16u
#define W64S_BAD_RATE 32u
#define W64S_BAD_LENGTH 64u

typedef struct {
 uint32_t status,rate_code,rate_mbps,psdu_bytes,data_symbols;
 uint32_t n_bpsc,n_cbps,n_dbps,code_numerator,code_denominator;
 uint32_t qam64,backend54_supported,unforced_state,tail_metric_gap;
 uint8_t bits[24];
} w64s_result;
static unsigned w64s_parity(unsigned v){v^=v>>4;v^=v>>2;v^=v>>1;return v&1u;}
static int w64s_decode(const int16_t *llr,unsigned count,w64s_result *r){
 if(!r)return -1;
 memset(r,0,sizeof(*r));
 if(!llr||count!=48){r->status=W64S_BAD_INPUT;return -1;}
 int16_t soft[48];unsigned energy=0;
 for(unsigned k=0;k<48;k++){soft[k]=llr[3*(k%16)+k/16];energy|=(unsigned)(soft[k]!=0);}
 if(!energy){r->status=W64S_NO_ENERGY;return 1;}
 int32_t metric[64],next[64];uint64_t trace[24];
 for(unsigned s=0;s<64;s++)metric[s]=s?-1000000000:0;
 for(unsigned t=0;t<24;t++){
  int32_t a=soft[2*t],b=soft[2*t+1];uint64_t choices=0;
  for(unsigned state=0;state<64;state++){
   unsigned bit=state&1u,p0=state>>1,p1=p0|32u,x0=(p0<<1)|bit,x1=(p1<<1)|bit;
   int32_t m0=metric[p0]+(w64s_parity(x0&0155)?a:-a)+(w64s_parity(x0&0117)?b:-b);
   int32_t m1=metric[p1]+(w64s_parity(x1&0155)?a:-a)+(w64s_parity(x1&0117)?b:-b);
   if(m1>m0){next[state]=m1;choices|=(uint64_t)1<<state;}else next[state]=m0;
  }
  trace[t]=choices;memcpy(metric,next,sizeof(metric));
 }
 unsigned best=0;
 for(unsigned s=1;s<64;s++)if(metric[s]>metric[best])best=s;
 r->unforced_state=best;r->tail_metric_gap=(uint32_t)(metric[best]-metric[0]);
 if(best&&metric[best]>metric[0])r->status|=W64S_BAD_TAIL;
 unsigned state=0;
 for(unsigned t=24;t-- >0;){r->bits[t]=(uint8_t)(state&1u);state=(state>>1)|((unsigned)((trace[t]>>state)&1u)<<5);}
 for(unsigned n=0;n<4;n++)r->rate_code|=(uint32_t)r->bits[n]<<n;
 for(unsigned n=5;n<17;n++)r->psdu_bytes|=(uint32_t)r->bits[n]<<(n-5);
 if(r->bits[4])r->status|=W64S_BAD_RESERVED;
 unsigned parity=0;for(unsigned n=0;n<18;n++)parity^=r->bits[n];
 if(parity)r->status|=W64S_BAD_PARITY;
 for(unsigned n=18;n<24;n++)if(r->bits[n])r->status|=W64S_BAD_TAIL;
 static const uint8_t code[8]={11,15,10,14,9,13,8,12};
 static const uint8_t mbps[8]={6,9,12,18,24,36,48,54};
 static const uint8_t dbps[8]={24,36,48,72,96,144,192,216};
 static const uint8_t bpsc[8]={1,1,2,2,4,4,6,6};
 unsigned index=8;for(unsigned n=0;n<8;n++)if(code[n]==r->rate_code)index=n;
 if(index==8)r->status|=W64S_BAD_RATE;
 else{
  r->rate_mbps=mbps[index];r->n_dbps=dbps[index];r->n_bpsc=bpsc[index];r->n_cbps=48*bpsc[index];
  r->code_numerator=index==6?2:((index&1)?3:1);r->code_denominator=index==6?3:((index&1)?4:2);
  r->qam64=index>=6;r->backend54_supported=index==7;
  r->data_symbols=(16+8*r->psdu_bytes+6+r->n_dbps-1)/r->n_dbps;
 }
 if(r->psdu_bytes<4||r->psdu_bytes>4095)r->status|=W64S_BAD_LENGTH;
 return r->status?1:0;
}
#endif
