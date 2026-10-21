// Nios replay harness: FPGA performs encoding/mapping/demapping/Viterbi.
// Noise is an explicitly approximate Gaussian: sum of 12 uniform bytes.
static uint32_t ms_rng,ms_valid,ms_tx[88],ms_rx[88],ms_payload[8],ms_decoded[8],ms_coded[17],ms_llr[131];
static uint32_t ms_next(void){uint32_t x=ms_rng;x^=x<<13;x^=x>>17;x^=x<<5;ms_rng=x;return x;}
static int32_t ms_noise(uint32_t sigma){
 int32_t z=-1530;for(uint32_t i=0;i<12;i++)z+=(int32_t)(ms_next()&255u);
 uint32_t a=(uint32_t)(z<0?-z:z),v=0,b=sigma;
 while(b){if(b&1u)v+=a;a<<=1;b>>=1;}
 v=(v+128u)>>8;return z<0?-(int32_t)v:(int32_t)v;
}
static int ms_wait(void){
 for(uint32_t n=0;n<2000000u;n++){uint32_t s=MODEM(1);if(s&4u)return 0;if((s&3u)==2u)return 1;}return 0;
}
static int32_t ms_clip(int32_t v,uint32_t *clips){if(v>32767){(*clips)++;return 32767;}if(v< -32768){(*clips)++;return -32768;}return v;}
static void ms_command(uint32_t id,char **t,uint32_t nt){
 int32_t a,b,c;
 if(equal(t[2],"MSVERSION")&&nt==3){prefix(id,"OK,MSVERSION");field("version",1);field("max_frames",32);field("payload",256);return;}
 if(equal(t[2],"MSRUN")&&nt==6&&integer(t[3],&a)&&a>0&&integer(t[4],&b)&&b>=0&&b<=8192&&integer(t[5],&c)&&c>=1&&c<=32){
  if(MODEM(0)!=0x4d440601u||(MODEM(1)&1u)){text(",MODEM_UNAVAILABLE");return;}
  uint32_t raw=0,post=0,raw_cpu=0,post_cpu=0,ec=0,dc=0,clips=0;
  ms_valid=0;ms_rng=(uint32_t)a;
  for(uint32_t frame=0;frame<(uint32_t)c;frame++){
   for(uint32_t i=0;i<8;i++){ms_payload[i]=0;ms_decoded[i]=0;}
   for(uint32_t i=0;i<17;i++)ms_coded[i]=0;
   for(uint32_t i=0;i<131;i++)ms_llr[i]=0;
   MODEM(2)=6;MODEM(3)=256;
   for(uint32_t i=0;i<256;i++){uint32_t bit=ms_next()&1u;ms_payload[i>>5]|=bit<<(i&31);MODEM(4)=i;MODEM(5)=bit;}
   MODEM(1)=1;if(!ms_wait()||MODEM(10)!=88u){text(",ENCODE_FAILED");return;}ec+=MODEM(11);
   for(uint32_t i=0;i<524;i++){MODEM(4)=i;ms_coded[i>>5]|=(MODEM(7)&1u)<<(i&31);}
   for(uint32_t i=0;i<88;i++){
    MODEM(4)=i;uint32_t v=MODEM(6);ms_tx[i]=v;
    int32_t ri=(int32_t)(int16_t)v+ms_noise((uint32_t)b),rq=(int32_t)(int16_t)(v>>16)+ms_noise((uint32_t)b);
    ri=ms_clip(ri,&clips);rq=ms_clip(rq,&clips);
    ms_rx[i]=((uint32_t)ri&65535u)|((uint32_t)rq<<16);MODEM(6)=ms_rx[i];
   }
   MODEM(1)=2;if(!ms_wait()){text(",DECODE_FAILED");return;}dc+=MODEM(11);raw+=MODEM(12);post+=MODEM(13);
   for(uint32_t i=0;i<524;i++){MODEM(4)=i;uint32_t v=MODEM(8);ms_llr[i>>2]|=(v&255u)<<((i&3)<<3);raw_cpu+=((v>>31)&1u)!=((ms_coded[i>>5]>>(i&31))&1u);}
   for(uint32_t i=0;i<256;i++){MODEM(4)=i;uint32_t v=MODEM(9)&1u;ms_decoded[i>>5]|=v<<(i&31);post_cpu+=v!=((ms_payload[i>>5]>>(i&31))&1u);}
  }
  if(raw!=raw_cpu||post!=post_cpu){text(",COUNTER_MISMATCH");return;}
  ms_valid=1;prefix(id,"OK,MSRUN");field("frames",(uint32_t)c);field("payload_bits",(uint32_t)c<<8);field("coded_bits",(uint32_t)c*524u);
  field("raw_errors",raw);field("decoded_errors",post);field("raw_audit",raw_cpu);field("decoded_audit",post_cpu);
  field("encode_cycles",ec);field("decode_cycles",dc);field("clips",clips);text(",next_bits=");hexword(ms_rng);return;
 }
 if(equal(t[2],"MSGET")&&nt==6&&integer(t[3],&a)&&a>=0&&a<=5&&integer(t[4],&b)&&b>=0&&integer(t[5],&c)&&c>=1&&c<=8&&ms_valid){
  static const uint32_t sizes[6]={88,88,8,8,17,131};static uint32_t *const buffers[6]={ms_tx,ms_rx,ms_payload,ms_decoded,ms_coded,ms_llr};
  if((uint32_t)b+(uint32_t)c>sizes[a]){text(",RANGE");return;}
  prefix(id,"OK,MSGET");field("kind",(uint32_t)a);field("offset",(uint32_t)b);field("count",(uint32_t)c);text(",bits=");
  for(uint32_t i=0;i<(uint32_t)c;i++)hexword(buffers[a][(uint32_t)b+i]);return;
 }
 text(",BAD_SWEEP_COMMAND");
}
