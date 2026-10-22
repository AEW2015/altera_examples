#ifndef ATUM_WIFI64_ACQUIRE_H
#define ATUM_WIFI64_ACQUIRE_H
/* Bounded portable Nios SOFTWARE frontend/acquisition; no runtime libm,
 * allocation, RF control or host assistance. Not parallel RTL acceleration.
 * Input CI8 burst <=16380 samples, nominal20/40MS/s ONLY. 40→20 uses129tap
 * Kaiser(beta8.6)9MHz lowpass Q15, valid convolution then /2; center offset64.
 * Output CI16 is raw*128 (uncalibrated). Acquisition uses16lag/80sample STF
 * coherence then matched paired64sample WLAN LTFs; fine CFO from their phase.
 * Q32 phase is signed turns/sample at20MS/s. CORDIC uses arithmetic rightshift
 * (GCC RV32/native targets). Rotations saturate and report clipping.
 * Scratch may change on failure; input data changes ONLY on successful return.
 * Caller must still validate L-SIG/DATA/FCS, pilot tracking and frame extent.
 * Algorithm independent reference: wifi_phy_reference.py _candidate_ltf in
 * this project's older RF reference; template IEEE L-LTF -26..26 signs.
 */
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#define W64A_MAX_SAMPLES 16380u
#define W64A_BAD_INPUT 1u
#define W64A_UNSUPPORTED_RATE 2u
#define W64A_TRUNCATED 4u
#define W64A_NOT_FOUND 8u
#define W64A_MIN_SCORE 14745u /* .45 normalized squared coherence, Q15 */
typedef struct {int16_t i,q;} w64a_complex;
typedef struct {uint32_t ltf_index,score_q15;int32_t coarse_q32;} w64a_candidate;
typedef struct {
 uint32_t status,output_samples,input_offset,decimation,frontend_clips;
 uint32_t ltf_index,signal_index,score_q15,stf_score_q15,candidates,rotation_clips;
 int32_t coarse_q32,fine_q32,cfo_q32;
 w64a_candidate candidate[8];
} w64a_result;
static const int16_t w64a_fir[129]={0,0,0,-1,0,1,1,-2,-2,3,4,-3,-7,1,11,2,-14,-8,16,16,-16,-27,11,39,0,-50,-18,57,42,-57,-73,45,106,-19,-136,-23,157,83,-162,-155,142,236,-90,-314,0,377,129,-409,-297,393,496,-308,-716,132,944,167,-1164,-644,1357,1439,-1509,-3070,1605,10292,14748,10292,1605,-3070,-1509,1439,1357,-644,-1164,167,944,132,-716,-308,496,393,-297,-409,129,377,0,-314,-90,236,142,-155,-162,83,157,-23,-136,-19,106,45,-73,-57,42,57,-18,-50,0,39,11,-27,-16,16,16,-8,-14,2,11,1,-7,-3,4,3,-2,-2,1,1,0,-1,0,0,0};
/* The exact symmetric FIR array is checked against an independent formula. */
static int16_t w64a_clip(int64_t x,uint32_t *clips){if(x>32767){(*clips)++;return 32767;}if(x< -32768){(*clips)++;return -32768;}return(int16_t)x;}
static int w64a_frontend(const int8_t *raw,unsigned n,unsigned rate,w64a_complex*out,unsigned capacity,w64a_result*r){
 if(!r)return -1;
 memset(r,0,sizeof(*r));
 if(!raw||!out||!n||n>W64A_MAX_SAMPLES){r->status=W64A_BAD_INPUT;return -1;}
 if(rate!=20000000&&rate!=40000000){r->status=W64A_UNSUPPORTED_RATE;return -1;}
 unsigned length=rate==20000000?n:(n>=129?(n-129)/2+1:0);
 if(!length){r->status=W64A_TRUNCATED;return 1;}
 if(capacity<length||((uintptr_t)raw<(uintptr_t)out+length*sizeof(*out)&&(uintptr_t)out<(uintptr_t)raw+2*n)){r->status=W64A_BAD_INPUT;return -1;}
 r->output_samples=length;r->decimation=rate==20000000?1:2;r->input_offset=rate==20000000?0:64;
 for(unsigned k=0;k<length;k++){
  int64_t i=0,q=0;
  if(rate==20000000){i=(int32_t)raw[2*k]*128;q=(int32_t)raw[2*k+1]*128;}
  else{
   for(unsigned j=0;j<129;j++){i+=(int32_t)raw[2*(2*k+j)]*w64a_fir[j];q+=(int32_t)raw[2*(2*k+j)+1]*w64a_fir[j];}
   /* Q15 filter times128; nearest rounding, half away fromzero. */
   i=i>=0?(i+128)/256:-((-i+128)/256);q=q>=0?(q+128)/256:-((-q+128)/256);
  }
  out[k].i=w64a_clip(i,&r->frontend_clips);out[k].q=w64a_clip(q,&r->frontend_clips);
 }return 0;
}
static const int32_t w64a_atan[24]={536870912,316933406,167458907,85004756,42667331,21354465,10679838,5340245,2670163,1335087,667544,333772,166886,83443,41722,20861,10430,5215,2608,1304,652,326,163,81};
static int32_t w64a_angle(int64_t x,int64_t y){
 if(!x&&!y)return 0;
 int64_t z=0;x*=65536;y*=65536;
 if(x<0){z=y>=0?2147483648LL:-2147483648LL;x=-x;y=-y;}
 for(unsigned k=0;k<24;k++){
  int64_t old=x;if(y>0){x+=y>>k;y-=old>>k;z+=w64a_atan[k];}
  else if(y<0){x-=y>>k;y+=old>>k;z-=w64a_atan[k];}
 }
 return(int32_t)(uint32_t)z;
}
static void w64a_sincos(int32_t phase,int32_t*c,int32_t*s){
 int64_t z=phase;int sign=1;
 if(z>1073741824LL){z-=2147483648LL;sign=-1;}
 if(z< -1073741824LL){z+=2147483648LL;sign=-1;}
 int32_t x=19898,y=0;
 for(unsigned k=0;k<24;k++){int32_t old=x;if(z>=0){x-=y>>k;y+=old>>k;z-=w64a_atan[k];}else{x+=y>>k;y-=old>>k;z+=w64a_atan[k];}}
 *c=sign*x;*s=sign*y;
}
static void w64a_rotate(const w64a_complex*in,w64a_complex*out,unsigned n,int32_t increment,uint32_t*clips){
 uint32_t phase=0;for(unsigned k=0;k<n;k++){
  int32_t c,s;w64a_sincos((int32_t)phase,&c,&s);
  int64_t i=((int64_t)in[k].i*c+(int64_t)in[k].q*s)/32768;
  int64_t q=((int64_t)in[k].q*c-(int64_t)in[k].i*s)/32768;
  out[k].i=w64a_clip(i,clips);out[k].q=w64a_clip(q,clips);phase+=(uint32_t)increment;
 }
}
static const int16_t w64a_ltf_i[64]={160,-5,41,99,22,61,-118,-39,100,55,1,-140,25,60,-23,122,64,38,-59,-134,84,71,-62,-58,-36,-125,-130,77,-3,-94,94,13,-160,13,94,-94,-3,77,-130,-125,-36,-58,-62,71,84,-134,-59,38,64,122,-23,60,25,-140,1,55,100,-39,-118,61,22,99,41,-5};
static const int16_t w64a_ltf_q[64]={0,-123,-114,85,29,-90,-57,-109,-27,4,-118,-49,-60,-15,165,-4,-64,101,40,67,95,14,83,-22,-155,-17,-21,-76,55,118,108,100,0,-100,-108,-118,-55,76,21,17,155,22,-83,-14,-95,-67,-40,-101,64,4,-165,15,60,49,118,-4,27,109,57,90,-29,-85,114,123};
static uint32_t w64a_score(int64_t ri,int64_t rq,uint64_t ea,uint64_t eb){
 if(ea<64||eb<64)return 0;
 uint64_t numerator=(uint64_t)(ri*ri+rq*rq),denominator=ea*eb;
 uint64_t score=numerator*32768/denominator;return score>32768?32768:(uint32_t)score;
}
static uint32_t w64a_match(const w64a_complex*x){
 int64_t ri=0,rq=0;uint64_t e=0,reference=0;
 for(unsigned k=0;k<64;k++){
  int32_t i=x[k].i/128,q=x[k].q/128,a=w64a_ltf_i[k],b=w64a_ltf_q[k];
  ri+=i*a+q*b;rq+=q*a-i*b;e+=i*i+q*q;reference+=a*a+b*b;
 }return w64a_score(ri,rq,e,reference);
}
static void w64a_candidate_add(w64a_result*r,unsigned index,unsigned score,int32_t coarse){
 for(unsigned k=0;k<r->candidates;k++){
  unsigned other=r->candidate[k].ltf_index;
  if((index>other?index-other:other-index)<8){
   if(score<=r->candidate[k].score_q15)return;
   for(unsigned j=k+1;j<r->candidates;j++)r->candidate[j-1]=r->candidate[j];
   r->candidates--;break;
  }
 }
 unsigned pos=0;while(pos<r->candidates&&r->candidate[pos].score_q15>=score)pos++;
 if(pos>=8)return;
 if(r->candidates<8)r->candidates++;
 for(unsigned k=r->candidates-1;k>pos;k--)r->candidate[k]=r->candidate[k-1];
 r->candidate[pos].ltf_index=index;r->candidate[pos].score_q15=score;r->candidate[pos].coarse_q32=coarse;
}
static int w64a_acquire(w64a_complex*data,unsigned n,w64a_complex*scratch,unsigned capacity,w64a_result*r){
 if(!r)return -1;
 memset(r,0,sizeof(*r));r->output_samples=n;
 if(!data||!scratch||n>W64A_MAX_SAMPLES||capacity<n||((uintptr_t)data<(uintptr_t)scratch+n*sizeof(*data)&&(uintptr_t)scratch<(uintptr_t)data+n*sizeof(*data))){r->status=W64A_BAD_INPUT;return -1;}
 if(n<320){r->status=W64A_TRUNCATED;return 1;}
 int32_t coarse[6]={0};uint32_t quality[6]={0};unsigned count=1;
 for(unsigned offset=0;offset+96<=n;offset+=4){
  int64_t ri=0,rq=0;uint64_t ea=0,eb=0;
  for(unsigned k=0;k<80;k++){
   int32_t ai=data[offset+k].i/128,aq=data[offset+k].q/128,bi=data[offset+k+16].i/128,bq=data[offset+k+16].q/128;
   ri+=ai*bi+aq*bq;rq+=ai*bq-aq*bi;ea+=ai*ai+aq*aq;eb+=bi*bi+bq*bq;
  }
  uint32_t score=w64a_score(ri,rq,ea,eb);if(score>r->stf_score_q15)r->stf_score_q15=score;
  if(score<W64A_MIN_SCORE)continue;
  int32_t phase=w64a_angle(ri,rq)/16;unsigned at=count;
  for(unsigned k=0;k<count;k++){int64_t diff=(int64_t)phase-coarse[k];if(diff<0)diff=-diff;if(diff<273426){at=k;break;}}
  if(at<count){if(at&&score>quality[at]){coarse[at]=phase;quality[at]=score;}continue;}
  if(count<6){coarse[count]=phase;quality[count++]=score;}
  else {unsigned worst=1;for(unsigned k=2;k<6;k++)if(quality[k]<quality[worst])worst=k;if(score>quality[worst]){coarse[worst]=phase;quality[worst]=score;}}
 }
 for(unsigned c=0;c<count;c++){
  uint32_t clips=0;w64a_rotate(data,scratch,n,coarse[c],&clips);
  for(unsigned index=0;index+128<=n;index++){
   unsigned first=w64a_match(scratch+index);if(first<W64A_MIN_SCORE)continue;
   unsigned second=w64a_match(scratch+index+64);unsigned score=first<second?first:second;
   if(score>=W64A_MIN_SCORE)w64a_candidate_add(r,index,score,coarse[c]);
  }
 }
 if(!r->candidates){r->status=W64A_NOT_FOUND;return 1;}
 unsigned selected=0;
 for(unsigned k=0;k<r->candidates;k++)if(r->candidate[k].ltf_index>=192&&r->candidate[k].ltf_index+208<=n){selected=k;break;}
 r->ltf_index=r->candidate[selected].ltf_index;r->signal_index=r->ltf_index+144;r->score_q15=r->candidate[selected].score_q15;r->coarse_q32=r->candidate[selected].coarse_q32;
 if(r->ltf_index<192||r->signal_index+64>n){r->status=W64A_TRUNCATED;return 1;}
 uint32_t ignored=0;w64a_rotate(data,scratch,n,r->coarse_q32,&ignored);
 int64_t ri=0,rq=0;
 for(unsigned k=0;k<64;k++){
  int32_t ai=scratch[r->ltf_index+k].i/128,aq=scratch[r->ltf_index+k].q/128,bi=scratch[r->ltf_index+k+64].i/128,bq=scratch[r->ltf_index+k+64].q/128;
  ri+=ai*bi+aq*bq;rq+=ai*bq-aq*bi;
 }
 r->fine_q32=w64a_angle(ri,rq)/64;r->cfo_q32=(int32_t)((uint32_t)r->coarse_q32+(uint32_t)r->fine_q32);
 w64a_rotate(data,scratch,n,r->cfo_q32,&r->rotation_clips);memcpy(data,scratch,n*sizeof(*data));return 0;
}
#endif
