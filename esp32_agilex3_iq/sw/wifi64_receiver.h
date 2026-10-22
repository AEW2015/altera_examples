#ifndef ATUM_WIFI64_RECEIVER_H
#define ATUM_WIFI64_RECEIVER_H
/* Portable complete legacy54 receive-chain SOFTWARE prototype for Nios.
 * Caller provides contiguous CI8 at40MS/s and workspace; no allocation/libm,
 * radio actions, host runtime DSP or fabricated BER. Offline tests are synthetic.
 * Includes antialias/decimation, acquisition/CFO, FFT/channel/equalization,
 * pilot commonphase, L-SIG, WLAN64QAM demap, depuncture/Viterbi/descramble/FCS.
 * Pilot tracking removes common phase modulo pi; it is not sampleclock recovery.
 * Up to8 acquired candidates are attempted. Raw data remains untouched; each
 * alternate candidate regenerates filtered data from that same input capture.
 * Only54Mb/s DATA supported;48Mb/s is recognized and explicitly rejected.
 */
#include "wifi64_acquire.h"
#include "wifi64_ofdm.h"
#include "wifi64_signal.h"
#include "wifi64_decode.h"
#define W64R_MAX_OUTPUT ((W64A_MAX_SAMPLES-129u)/2u+1u)
#define W64R_BAD_INPUT 1u
#define W64R_FRONTEND_FAILED 2u
#define W64R_ACQUISITION_FAILED 4u
#define W64R_TRUNCATED 8u
#define W64R_CHANNEL_FAILED 16u
#define W64R_SIGNAL_FAILED 32u
#define W64R_UNSUPPORTED_RATE 64u
#define W64R_DATA_FAILED 128u
#define W64R_FCS_FAILED 256u
#define W64R_TOO_LARGE 512u

typedef struct {
 uint32_t status,stage,accepted,candidates_attempted,capture_clipped_components;
 uint32_t equalizer_clips,data_points,data_symbols;
 uint32_t candidate_status[8],candidate_ltf[8];
 int32_t pilot_phase_q32[W64D_MAX_SYMBOLS+1];
 w64a_result frontend,acquisition;
 w64s_result signal;
 w64d_result packet;
 /* Actual equalized DATA points, Q13; no reconstructed constellation. */
 w64_complex constellation[W64D_MAX_SYMBOLS*48];
} w64r_result;
typedef struct {
 w64a_complex data[W64R_MAX_OUTPUT],scratch[W64R_MAX_OUTPUT];
 w64d_workspace decoder;
 int16_t llr[W64D_MAX_SYMBOLS*288];
 w64_complex time[64],ltf_a[64],channel[64],equalized[64];
 w64r_result trial;
} w64r_workspace;
static int w64r_fft(w64r_workspace*w,unsigned start,w64_complex*out){
 for(unsigned n=0;n<64;n++){w->time[n].i=w->data[start+n].i;w->time[n].q=w->data[start+n].q;}
 return w64_fft64(w->time,out);
}
static int w64r_equalize(w64r_workspace*w,unsigned start,int32_t*phase,uint32_t*clips){
 if(w64r_fft(w,start,w->ltf_a)||w64_equalize(w->ltf_a,w->channel,w->equalized))return -1;
 int64_t ri=(int64_t)w->equalized[43].i+w->equalized[57].i+w->equalized[7].i-w->equalized[21].i;
 int64_t rq=(int64_t)w->equalized[43].q+w->equalized[57].q+w->equalized[7].q-w->equalized[21].q;
 if(ri*ri+rq*rq<1024)return -2;
 *phase=w64a_angle(ri*ri-rq*rq,2*ri*rq)/2;
 int32_t c,s;w64a_sincos(*phase,&c,&s);
 for(unsigned n=0;n<64;n++){
  int64_t i=((int64_t)w->equalized[n].i*c+(int64_t)w->equalized[n].q*s)/32768;
  int64_t q=((int64_t)w->equalized[n].q*c-(int64_t)w->equalized[n].i*s)/32768;
  w->equalized[n].i=w64a_clip(i,clips);w->equalized[n].q=w64a_clip(q,clips);
 }return 0;
}
static void w64r_correct_candidate(w64r_workspace*w,unsigned n,w64a_result*a,const w64a_candidate*candidate){
 uint32_t clips=0;w64a_rotate(w->data,w->scratch,n,candidate->coarse_q32,&clips);
 int64_t ri=0,rq=0;unsigned start=candidate->ltf_index;
 for(unsigned k=0;k<64;k++){
  int32_t ai=w->scratch[start+k].i/128,aq=w->scratch[start+k].q/128,bi=w->scratch[start+k+64].i/128,bq=w->scratch[start+k+64].q/128;
  ri+=ai*bi+aq*bq;rq+=ai*bq-aq*bi;
 }
 a->ltf_index=start;a->signal_index=start+144;a->score_q15=candidate->score_q15;a->coarse_q32=candidate->coarse_q32;
 a->fine_q32=w64a_angle(ri,rq)/64;a->cfo_q32=(int32_t)((uint32_t)a->coarse_q32+(uint32_t)a->fine_q32);
 a->rotation_clips=0;w64a_rotate(w->data,w->scratch,n,a->cfo_q32,&a->rotation_clips);memcpy(w->data,w->scratch,n*sizeof(w->data[0]));
}
static void w64r_attempt(w64r_workspace*w,unsigned n,w64r_result*r){
 unsigned ltf=r->acquisition.ltf_index;r->stage=2;
 if(ltf+208>n){r->status=W64R_TRUNCATED;return;}
 if(w64r_fft(w,ltf,w->ltf_a)||w64r_fft(w,ltf+64,w->equalized)){r->status=W64R_CHANNEL_FAILED;return;}
 w64_channel(w->ltf_a,w->equalized,w->channel);
 if(w64r_equalize(w,ltf+144,&r->pilot_phase_q32[0],&r->equalizer_clips)){r->status=W64R_CHANNEL_FAILED;return;}
 int16_t signal_llr[48];unsigned at=0;
 for(int carrier=-26;carrier<=26;carrier++){
  unsigned bin=(unsigned)(carrier+64)%64;if(!w64_active(bin)||w64_pilot(bin))continue;
  signal_llr[at++]=(int16_t)w->equalized[bin].i;
 }
 if(w64s_decode(signal_llr,48,&r->signal)){r->status=W64R_SIGNAL_FAILED;return;}
 r->stage=3;
 if(!r->signal.backend54_supported){r->status=W64R_UNSUPPORTED_RATE;return;}
 if(r->signal.psdu_bytes>W64D_MAX_PSDU||r->signal.data_symbols>W64D_MAX_SYMBOLS){r->status=W64R_TOO_LARGE;return;}
 r->data_symbols=r->signal.data_symbols;
 if(ltf+208+80*r->data_symbols>n){r->status=W64R_TRUNCATED;return;}
 for(unsigned symbol=0;symbol<r->data_symbols;symbol++){
  if(w64r_equalize(w,ltf+224+80*symbol,&r->pilot_phase_q32[symbol+1],&r->equalizer_clips)){r->status=W64R_CHANNEL_FAILED;return;}
  if(w64_demap(w->equalized,w->llr+288*symbol)){r->status=W64R_DATA_FAILED;return;}
  for(int carrier=-26;carrier<=26;carrier++){
   unsigned bin=(unsigned)(carrier+64)%64;if(!w64_active(bin)||w64_pilot(bin))continue;
   r->constellation[r->data_points++]=w->equalized[bin];
  }
 }
 r->stage=4;
 int rc=w64d_decode(w->llr,r->data_symbols*288,r->signal.psdu_bytes,&w->decoder,&r->packet);
 if(rc||r->packet.status){r->status=(r->packet.status&W64D_BAD_FCS)?W64R_FCS_FAILED:W64R_DATA_FAILED;return;}
 r->stage=5;r->accepted=1;
}
static int w64r_decode_ex(const int8_t*raw,unsigned samples,unsigned rate,w64r_workspace*w,w64r_result*r,unsigned conjugate_q){
 if(!r)return -1;
 memset(r,0,sizeof(*r));
 if(!raw||!w||!samples||samples>W64A_MAX_SAMPLES||conjugate_q>1||
    ((uintptr_t)raw<(uintptr_t)w+sizeof(*w)&&(uintptr_t)w<(uintptr_t)raw+2*samples)||
    ((uintptr_t)r<(uintptr_t)w+sizeof(*w)&&(uintptr_t)w<(uintptr_t)r+sizeof(*r))){r->status=W64R_BAD_INPUT;return -1;}
 if(rate!=40000000){r->status=W64R_UNSUPPORTED_RATE;return -1;}
 for(unsigned k=0;k<2*samples;k++)if(raw[k]==127||raw[k]==-128)r->capture_clipped_components++;
 if(w64a_frontend_ex(raw,samples,rate,w->data,W64R_MAX_OUTPUT,&r->frontend,conjugate_q)){r->status=W64R_FRONTEND_FAILED;return 1;}
 unsigned n=r->frontend.output_samples;r->stage=1;
 if(w64a_acquire(w->data,n,w->scratch,W64R_MAX_OUTPUT,&r->acquisition)){r->status=W64R_ACQUISITION_FAILED;return 1;}
 /* Acquisition's metadata lives separately from its mutable processing arrays. */
 w64a_result candidates=r->acquisition;unsigned attempted=0;
 uint32_t statuses[8]={0},indices[8]={0};
 for(unsigned index=0;index<candidates.candidates;index++){
  w64a_candidate c=candidates.candidate[index];
  if(c.ltf_index<192||c.ltf_index+208>n)continue;
  memset(&w->trial,0,sizeof(w->trial));w->trial.frontend=r->frontend;w->trial.acquisition=candidates;
  w->trial.capture_clipped_components=r->capture_clipped_components;
  /* Recreate the same capture before each alternate CFO trial. */
  if(w64a_frontend_ex(raw,samples,rate,w->data,W64R_MAX_OUTPUT,&w->trial.frontend,conjugate_q)){r->status=W64R_FRONTEND_FAILED;return 1;}
  w64r_correct_candidate(w,n,&w->trial.acquisition,&c);attempted++;
  w64r_attempt(w,n,&w->trial);statuses[attempted-1]=w->trial.status;indices[attempted-1]=c.ltf_index;
  if(w->trial.stage>r->stage||w->trial.accepted)*r=w->trial;
  if(r->accepted){r->candidates_attempted=attempted;memcpy(r->candidate_status,statuses,sizeof(statuses));memcpy(r->candidate_ltf,indices,sizeof(indices));return 0;}
 }
 r->candidates_attempted=attempted;memcpy(r->candidate_status,statuses,sizeof(statuses));memcpy(r->candidate_ltf,indices,sizeof(indices));return 1;
}
/* Original API remains nonconjugating; raw CI8 is never modified. */
static inline int w64r_decode(const int8_t*raw,unsigned samples,unsigned rate,w64r_workspace*w,w64r_result*r){return w64r_decode_ex(raw,samples,rate,w,r,0);}
#endif
