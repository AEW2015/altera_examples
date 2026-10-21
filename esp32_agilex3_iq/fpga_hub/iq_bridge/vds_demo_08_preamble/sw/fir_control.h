// Included after the logger formatting helpers; one JTAG owner, ID-tagged commands.
#ifdef IQMON_HOST_TEST
static volatile uint32_t fir_test_regs[64];
static volatile uint16_t fir_test_coeff[16];
#define FIR(n) fir_test_regs[(n)]
#define COEFF(n) fir_test_coeff[(n)]
#else
#define FIR(n) (*(volatile uint32_t *)(0x10030000u+4u*(n)))
#define COEFF(n) (*(volatile uint16_t *)(0x10040000u+2u*(n)))
#endif
static char input_line[96],reply[512];
static uint32_t input_used,reply_used,dump_active,dump_offset,dump_id;
static int equal(const char *a,const char *b){while(*a && *a==*b){a++;b++;}return *a==*b;}
static int integer(const char *s,int32_t *out){
 uint32_t v=0;int neg=0;if(*s=='-'){neg=1;s++;}if(!*s)return 0;
 while(*s){if(*s<'0'||*s>'9'||v>214748364u)return 0;v=v*10u+(uint32_t)(*s++-'0');if(v>2147483647u)return 0;}
 *out=neg?-(int32_t)v:(int32_t)v;return 1;
}
static void hexbyte(uint32_t n){const char *h="0123456789abcdef";line[used++]=h[(n>>4)&15];line[used++]=h[n&15];}
static void reply_save(void){reply_used=used;for(uint32_t i=0;i<used;i++)reply[i]=line[i];}
static void prefix(uint32_t id,const char *status){used=0;text("FIR,");number(id);text(",");text(status);}
// Initialize every coefficient explicitly: generated FIR reload RAM can power up
// with tap0=0 despite the intended boxcar profile. Keep boot and PRESET identical.
static void fir_preset(uint32_t profile){
 static const int16_t hamming[16]={-42,-177,-406,-352,669,2961,5846,7885,7885,5846,2961,669,-352,-406,-177,-42};
 for(uint32_t i=0;i<16;i++)COEFF(i)=(uint16_t)(profile==1?2048:hamming[i]);
 FIR(20)=profile;
}
static void fir_boot_init(void){
 FIR(18)=0; // No automatic paired capture until explicitly enabled.
 FIR(19)=0; // Truncate until the lesson selects nearest rounding.
 fir_preset(1);
}
#include "preamble_control.h"
static void fir_command(void){
 char *tokens[6];uint32_t nt=0;char *p=input_line;
 while(*p && nt<6){while(*p==' ')p++;if(!*p)break;tokens[nt++]=p;while(*p && *p!=' ')p++;if(*p)*p++=0;}
 int32_t id=0,a=0,b=0;
 if(nt<3 || !equal(tokens[0],"FIR") || !integer(tokens[1],&id) || id<0)return;
 if(preamble_command(tokens,nt,(uint32_t)id)){text("\n");reply_save();return;}
 prefix((uint32_t)id,"ERR");
 uint32_t state=FIR(1);
 if(equal(tokens[2],"STATUS") && nt==3){
  prefix((uint32_t)id,"OK,STATUS");field("state",state);field("samples",FIR(3));field("job",FIR(4));field("source",FIR(5));
  field("mode",FIR(2));field("cycles",FIR(9));field("errors",FIR(10));text(",raw_crc=");hexword(FIR(11));text(",filtered_crc=");hexword(FIR(12));field("rate",FIR(13));field("frequency",FIR(14));field("clips",FIR(17));field("pair",FIR(18));field("round",FIR(21));field("profile",FIR(22));field("configured_round",FIR(19));field("configured_profile",FIR(20));
 }else if(equal(tokens[2],"CANCEL") && nt==3){dump_active=0;prefix((uint32_t)id,"OK,CANCEL");
 }else if(dump_active || (state&0x89)){text(",BUSY");
 }else if(equal(tokens[2],"PAIR") && nt==4 && integer(tokens[3],&a) && a>=0 && a<=1){
  FIR(18)=(uint32_t)a;prefix((uint32_t)id,"OK,PAIR");field("enabled",FIR(18));
 }else if(equal(tokens[2],"ROUND") && nt==4 && integer(tokens[3],&a) && a>=0 && a<=1){
  FIR(19)=(uint32_t)a;prefix((uint32_t)id,"OK,ROUND");field("nearest",FIR(19));
 }else if(equal(tokens[2],"PRESET") && nt==4 && integer(tokens[3],&a) && a>=1 && a<=2){
  fir_preset((uint32_t)a);prefix((uint32_t)id,"OK,PRESET");field("profile",(uint32_t)a);
 }else if(equal(tokens[2],"ARM") && nt==3){FIR(1)=1;prefix((uint32_t)id,"OK,ARM");
 }else if(equal(tokens[2],"RUN") && nt==4 && integer(tokens[3],&a) && a>=0 && a<=1){
  if(state&2){FIR(2)=(uint32_t)a;FIR(1)=2;prefix((uint32_t)id,"OK,RUN");}else text(",NO_CAPTURE");
 }else if(equal(tokens[2],"TEST") && nt==4 && integer(tokens[3],&a) && a>=1 && a<=2){FIR(16)=(uint32_t)a;prefix((uint32_t)id,"OK,TEST");
 }else if(equal(tokens[2],"COEFF") && nt==5 && integer(tokens[3],&a) && integer(tokens[4],&b) && a>=0 && a<16 && b>=-32768 && b<=32767){
  COEFF(a)=(uint16_t)b;FIR(20)=0;prefix((uint32_t)id,"OK,COEFF");field("index",(uint32_t)a);text(",bits=");hexword((uint16_t)b);
 }else if(equal(tokens[2],"READCOEFF") && nt==4 && integer(tokens[3],&a) && a>=0 && a<16){
  prefix((uint32_t)id,"OK,READCOEFF");field("index",(uint32_t)a);text(",bits=");hexword(COEFF(a));
 }else if(equal(tokens[2],"DUMP") && nt==3){
  if(FIR(18)){text(",DISABLE_PAIR_FIRST");}
  else if(state&4){dump_active=1;dump_offset=0;dump_id=(uint32_t)id;prefix((uint32_t)id,"OK,DUMP");field("samples",FIR(3));field("job",FIR(4));field("source",FIR(5));text(",raw_crc=");hexword(FIR(11));text(",filtered_crc=");hexword(FIR(12));field("rate",FIR(13));field("frequency",FIR(14));field("clips",FIR(17));field("pair",FIR(18));field("round",FIR(21));field("profile",FIR(22));field("configured_round",FIR(19));field("configured_profile",FIR(20));field("mode",(state>>6)&1);field("cycles",FIR(9));field("clips",FIR(17));field("round",FIR(21));field("profile",FIR(22));}
  else text(",NOT_DONE");
 }else text(",BAD_COMMAND");
 text("\n");reply_save();
}
static void fir_poll(void){
 if(reply_used){
  if((JCTRL>>16)>=reply_used){for(uint32_t i=0;i<reply_used;i++)JDATA=(unsigned char)reply[i];reply_used=0;}
  else return;
 }
 for(uint32_t i=0;i<64 && !reply_used;i++){
  uint32_t c=JDATA;if(!(c&0x8000u))break;c&=255;
  if(c=='\n'){input_line[input_used]=0;fir_command();input_used=0;}
  else if(c!='\r'){if(input_used<sizeof(input_line)-1)input_line[input_used++]=(char)c;else input_used=0;}
 }
 if(reply_used || !dump_active || (JCTRL>>16)<400)return;
 uint32_t samples=FIR(3);
 if(dump_offset>=samples){used=0;text("FIRDONE,");number(dump_id);text("\n");reply_save();dump_active=0;return;}
 uint32_t n=samples-dump_offset;if(n>32)n=32;
 uint16_t raw[32],filtered[32];
 for(uint32_t i=0;i<n;i++){FIR(6)=dump_offset+i;raw[i]=(uint16_t)FIR(7);filtered[i]=(uint16_t)FIR(8);}
 used=0;text("FIRDATA,");number(dump_id);text(",");number(dump_offset);text(",");number(n);text(",");
 for(uint32_t i=0;i<n;i++){hexbyte(raw[i]);hexbyte(raw[i]>>8);}text(",");
 for(uint32_t i=0;i<n;i++){hexbyte(filtered[i]);hexbyte(filtered[i]>>8);}text("\n");
 // Whole-row capacity checked above; only this firmware writes the FIFO.
 for(uint32_t i=0;i<used;i++)JDATA=(unsigned char)line[i];
 dump_offset+=n;
}
