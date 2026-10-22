/* Standalone Nios software L-SIG fixture test. Boot waits; ASCII T runs.
 * No radio, waveform generation, acquisition or RTL acceleration claim. */
#include <stdint.h>
#include <stddef.h>
#ifndef W64_SELFTEST_NATIVE
void *memcpy(void*d,const void*s,size_t n){uint8_t*p=d;const uint8_t*q=s;while(n--)*p++=*q++;return d;}
void *memset(void*d,int c,size_t n){uint8_t*p=d;while(n--)*p++=(uint8_t)c;return d;}
#endif
#include "wifi64_signal.h"
#include "wifi64_signal_fixture.h"
#ifdef W64_SELFTEST_NATIVE
#include <stdio.h>
static void put(char c){putchar(c);}
static uint32_t ticks(void){return 0;}
#else
static volatile uint32_t*const uart=(volatile uint32_t*)0x10010000u;
static void put(char c){while(!(uart[1]>>16)){}uart[0]=(uint8_t)c;}
static uint32_t ticks(void){return *(volatile uint32_t*)0x00030000u;}
#endif
static void text(const char*s){while(*s)put(*s++);}
static void number(uint32_t x){char b[11];unsigned n=0;do{b[n++]=(char)('0'+x%10);x/=10;}while(x);while(n)put(b[--n]);}
static w64s_result result;
static unsigned selftest(void){
 static const uint8_t codes[4]={11,8,12,12},rates[4]={6,48,54,54},symbols[4]={32,4,4,4};
 unsigned passed=0;
 for(unsigned n=0;n<4;n++){
  uint32_t began=ticks();int rc=w64s_decode(signal_fixtures[n],48,&result);uint32_t elapsed=ticks()-began;
  unsigned pass=result.rate_code==codes[n]&&result.rate_mbps==rates[n]&&result.psdu_bytes==92&&result.data_symbols==symbols[n];
  pass=pass&&(n==3?(rc==1&&result.status==W64S_BAD_PARITY):(rc==0&&result.status==0));
  text("WIFI64_SIGNAL_TEST,CASE,index=");number(n);text(",pass=");number(pass);
  text(",rate_code=");number(result.rate_code);text(",mbps=");number(result.rate_mbps);
  text(",length=");number(result.psdu_bytes);text(",symbols=");number(result.data_symbols);
  text(",status=");number(result.status);text(",timer_ticks=");number(elapsed);put('\n');passed+=pass;
 }
 text("WIFI64_SIGNAL_TEST,SUMMARY,passed=");number(passed);text(",total=4,source=offline-fixture\n");return passed==4?0:1;
}
int main(void){
 text("WIFI64_SIGNAL_TEST,READY,tx=0,command=T\n");
#ifdef W64_SELFTEST_NATIVE
 return (int)selftest();
#else
 for(;;){uint32_t d=uart[0];if((d&0x8000u)&&(d&255)=='T')selftest();}
#endif
}
