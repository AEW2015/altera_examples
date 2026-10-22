#ifndef ATUM_WIFI64_OFDM_H
#define ATUM_WIFI64_OFDM_H
/* Portable integer Nios V receiver primitives, not a complete receiver.
 * FFT: CI32 input, transform/64, six stages with truncation toward zero.
 * LTF/equalizer: Q13 frequency-domain channel and output. Demapper: positive
 * int16 LLR favors bit1; IEEE WLAN bits b0,b1,b2=I; b3,b4,b5=Q.
 * Caller must provide correctly acquired, CFO/pilot-corrected symbols.
 * Mapping checked against IEEE 802.11-99/074 constellation contribution.
 * These routines are Nios software, not parallel RTL/IP FFT acceleration. */
#include <stdint.h>
#include <limits.h>
typedef struct { int32_t i,q; } w64_complex;
static const int16_t w64_cos[32]={32767,32610,32138,31357,30274,28899,27246,25330,23170,20788,18205,15447,12540,9512,6393,3212,0,-3212,-6393,-9512,-12540,-15447,-18205,-20788,-23170,-25330,-27246,-28899,-30274,-31357,-32138,-32610};
static const int16_t w64_sin[32]={0,3212,6393,9512,12540,15447,18205,20788,23170,25330,27246,28899,30274,31357,32138,32610,32767,32610,32138,31357,30274,28899,27246,25330,23170,20788,18205,15447,12540,9512,6393,3212};
/* Bounds: input components <=2^20, no intermediate component can grow because
 * every butterfly scales by 1/2. Outputs are in natural bin order. */
static int w64_fft64(const w64_complex in[64],w64_complex out[64]){
 unsigned n,j,k,width;
 for(n=0;n<64;n++){
  if(in[n].i>1048576||in[n].i< -1048576||in[n].q>1048576||in[n].q< -1048576)return -1;
 }
 for(n=0;n<64;n++){j=0;for(k=0;k<6;k++)j=(j<<1)|((n>>k)&1);out[j]=in[n];}
 for(width=2;width<=64;width*=2)for(n=0;n<64;n+=width)for(j=0;j<width/2;j++){
  unsigned tw=j*64/width;w64_complex a=out[n+j],b=out[n+j+width/2];
  int32_t ri=(int32_t)(((int64_t)b.i*w64_cos[tw]+(int64_t)b.q*w64_sin[tw])/32768);
  int32_t rq=(int32_t)(((int64_t)b.q*w64_cos[tw]-(int64_t)b.i*w64_sin[tw])/32768);
  out[n+j].i=(a.i+ri)/2;out[n+j].q=(a.q+rq)/2;
  out[n+j+width/2].i=(a.i-ri)/2;out[n+j+width/2].q=(a.q-rq)/2;
 }
 return 0;
}
static int w64_active(unsigned bin){return (bin>=1&&bin<=26)||(bin>=38&&bin<=63);}
static int w64_pilot(unsigned bin){return bin==7||bin==21||bin==43||bin==57;}
/* LTF signs in -26..26 order. */
static const int8_t w64_ltf[53]={1,1,-1,-1,1,1,-1,1,-1,1,1,1,1,1,1,-1,-1,1,1,-1,1,-1,1,1,1,1,0,1,-1,-1,1,1,-1,1,-1,1,-1,-1,-1,-1,-1,1,1,-1,-1,1,-1,1,-1,1,1,1,1};
static void w64_channel(const w64_complex a[64],const w64_complex b[64],w64_complex h[64]){
 unsigned n;for(n=0;n<64;n++){
  int k=n>31?(int)n-64:(int)n;
  if(w64_active(n)){int sign=w64_ltf[k+26];h[n].i=(int32_t)(((int64_t)a[n].i+b[n].i)*sign/2);h[n].q=(int32_t)(((int64_t)a[n].q+b[n].q)*sign/2);}
  else h[n].i=h[n].q=0;
 }
}
static int w64_equalize(const w64_complex x[64],const w64_complex h[64],w64_complex out[64]){
 unsigned n;for(n=0;n<64;n++){
  out[n].i=out[n].q=0;if(!w64_active(n))continue;
  if(h[n].i>1048576||h[n].i< -1048576||h[n].q>1048576||h[n].q< -1048576||x[n].i>1048576||x[n].i< -1048576||x[n].q>1048576||x[n].q< -1048576)return -1;
  int64_t e=(int64_t)h[n].i*h[n].i+(int64_t)h[n].q*h[n].q;if(e<16)return -2;
  int64_t ri=((int64_t)x[n].i*h[n].i+(int64_t)x[n].q*h[n].q)*8192/e;
  int64_t rq=((int64_t)x[n].q*h[n].i-(int64_t)x[n].i*h[n].q)*8192/e;
  if(ri>32767||ri< -32768||rq>32767||rq< -32768)return -3;
  out[n].i=(int32_t)ri;out[n].q=(int32_t)rq;
 }return 0;
}
static void w64_pam_llr(int32_t value,int16_t out[3]){
 static const int8_t pam[8]={-7,7,-1,1,-5,5,-3,3};unsigned bit,index;
 for(bit=0;bit<3;bit++){
  int64_t best[2]={INT64_MAX,INT64_MAX};
  for(index=0;index<8;index++){int64_t d=(int64_t)value-pam[index]*1264;d*=d;unsigned b=(index>>bit)&1;if(d<best[b])best[b]=d;}
  int64_t llr=(best[0]-best[1])/1264;if(llr>32767)llr=32767;if(llr< -32767)llr= -32767;out[bit]=(int16_t)llr;
 }
}
/* 48 DATA carriers ascending signed frequency; each emits I3 then Q3. */
static int w64_demap(const w64_complex bins[64],int16_t llr[288]){
 int carrier;unsigned count=0;for(carrier=-26;carrier<=26;carrier++){
  unsigned bin=(unsigned)(carrier+64)%64;if(!w64_active(bin)||w64_pilot(bin))continue;
  if(bins[bin].i>32767||bins[bin].i< -32768||bins[bin].q>32767||bins[bin].q< -32768)return -1;
  w64_pam_llr(bins[bin].i,llr+count);w64_pam_llr(bins[bin].q,llr+count+3);count+=6;
 }return count==288?0:-1;
}
#endif
