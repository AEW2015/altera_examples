/* Nios software primitive qualification, offline fixture. No RF or RTL claim.
 * Link with checkpoint06 startup/linker; host builds the independent fixture.
 * Boot only waits. ASCII 'T' runs; other bytes are ignored. */
#include <stdint.h>
#include <stddef.h>

#ifndef W64_SELFTEST_NATIVE
void *memcpy(void *d,const void *s,size_t n){uint8_t *p=d;const uint8_t*q=s;while(n--)*p++=*q++;return d;}
void *memset(void *d,int c,size_t n){uint8_t*p=d;while(n--)*p++=(uint8_t)c;return d;}
#endif
#include "wifi64_ofdm.h"
#include "wifi64_decode.h"
#include "wifi64_fixture.h"
#ifdef W64_SELFTEST_NATIVE
#include <stdio.h>
static void put(char c){putchar(c);}
static uint32_t cycles(void){return 0;}
#else
static volatile uint32_t *const juart=(volatile uint32_t*)0x10010000u;
static void put(char c){while(!(juart[1]>>16)){}juart[0]=(uint8_t)c;}
/* Generated checkpoint06 BSP: ALT_CPU_MTIME_OFFSET=0x00030000. */
static uint32_t cycles(void){return *(volatile uint32_t*)0x00030000u;}
#endif
static void text(const char*s){while(*s)put(*s++);}
static void number(uint32_t v){char b[11];unsigned n=0;do{b[n++]=(char)('0'+v%10);v/=10;}while(v);while(n)put(b[--n]);}
static void result(const char *name,unsigned ok,uint32_t dt){text("WIFI64_SELFTEST,");text(name);text(",pass=");number(ok);text(",timer_ticks=");number(dt);put('\n');}
static w64d_workspace workspace;
static w64d_result decoded;
static w64_complex a[64],b[64],h[64],out[64];
static int16_t metrics[288];
static unsigned selftest(void){
 unsigned ok=1,pass=0;uint32_t begin=cycles();
 if(w64_fft64(fixture_tone,out)!=0)ok=0;
 for(unsigned n=0;n<64;n++){
  int32_t ri=out[n].i-(n==7?8192:0),rq=out[n].q;
  if(ri>7||ri< -7||rq>7||rq< -7)ok=0;
 }result("FFT_TONE",ok,cycles()-begin);pass+=ok;
 begin=cycles();
 for(unsigned n=0;n<64;n++){
  int k=n>31?(int)n-64:(int)n;
  a[n].i=b[n].i=w64_active(n)?w64_ltf[k+26]*8192:0;
  a[n].q=b[n].q=0;
 }
 w64_channel(a,b,h);
 for(unsigned n=0;n<64;n++){a[n].i=w64_active(n)?3792:0;a[n].q=w64_active(n)?-6320:0;}
 ok=w64_equalize(a,h,out)==0;
 for(unsigned n=0;n<64;n++)if(out[n].i!=a[n].i||out[n].q!=a[n].q)ok=0;
 h[1].i=h[1].q=0;if(w64_equalize(a,h,out)!=-2)ok=0;
 result("CHANNEL_NULL",ok,cycles()-begin);pass+=ok;
 begin=cycles();ok=1;
 static const int8_t pam[8]={-7,7,-1,1,-5,5,-3,3};
 for(unsigned label=0;label<64;label++){
  for(unsigned n=0;n<64;n++){a[n].i=pam[label&7]*1264;a[n].q=pam[label>>3]*1264;}
  if(w64_demap(a,metrics)!=0)ok=0;
  for(unsigned bit=0;bit<288;bit++)if((metrics[bit]>0)!=((label>>(bit%6))&1u)||!metrics[bit])ok=0;
 }result("DEMAP_64",ok,cycles()-begin);pass+=ok;
 begin=cycles();
 ok=w64d_decode(fixture_llr,FIXTURE_LLR_COUNT,FIXTURE_PSDU_BYTES,&workspace,&decoded)==0&&decoded.status==0&&decoded.seed==93;
 for(unsigned n=0;n<FIXTURE_PSDU_BYTES;n++)if(decoded.psdu[n]!=fixture_psdu[n])ok=0;
 result("BACKEND_FCS",ok,cycles()-begin);pass+=ok;
 text("WIFI64_SELFTEST,FCS,computed=");number(decoded.crc_computed);text(",received=");number(decoded.crc_received);text(",bytes=");number(decoded.psdu_bytes);put('\n');
 begin=cycles();
 ok=w64d_decode(fixture_bad_llr,FIXTURE_LLR_COUNT,FIXTURE_PSDU_BYTES,&workspace,&decoded)==1&&decoded.status==W64D_BAD_FCS;
 result("CORRUPT_FCS",ok,cycles()-begin);pass+=ok;
 text("WIFI64_SELFTEST,SUMMARY,passed=");number(pass);text(",total=5,workspace_bytes=");number(sizeof(workspace));put('\n');
 return pass==5?0:1;
}
int main(void){
 text("WIFI64_SELFTEST,READY,source=offline-fixture,tx=0,command=T\n");
#ifdef W64_SELFTEST_NATIVE
 return (int)selftest();
#else
 for(;;){uint32_t d=juart[0];if((d&0x8000u)&&(d&255)=='T')selftest();}
#endif
}
