/* Dedicated checkpoint11 Nios raw-capture receiver app. No RF TX commands.
 * This replaces the regular monitor until its ELF/SOF is restored explicitly.
 * Input/processing stays in FPGA RAM/Nios; host sends controls and displays.
 */
#include <stdint.h>
#include <stddef.h>
#ifndef WIFI64_CAPTURE_HOST_TEST
void *memcpy(void*d,const void*s,size_t n){uint8_t*p=d;const uint8_t*q=s;while(n--)*p++=*q++;return d;}
void *memset(void*d,int c,size_t n){uint8_t*p=d;while(n--)*p++=(uint8_t)c;return d;}
#endif
#include "platform_map.h"
#include "wifi64_receiver.h"
#ifdef WIFI64_CAPTURE_HOST_TEST
extern uint32_t wifi64_test_read(unsigned block,unsigned index);
extern void wifi64_test_write(unsigned block,unsigned index,uint32_t value);
extern void wifi64_test_emit(char byte);
#define READ(block,n) wifi64_test_read(block,n)
#define WRITE(block,n,v) wifi64_test_write(block,n,v)
static uint64_t clock_ticks(void){return READ(2,0);}
static void fence(void){}
static void output(char c){wifi64_test_emit(c);}
#else
static uintptr_t block_base(unsigned block){return block==0?WIFI64_FIR_BASE:WIFI64_DDC_BASE;}
#define READ(block,n) (*(volatile uint32_t*)(block_base(block)+4u*(n)))
#define WRITE(block,n,v) (*(volatile uint32_t*)(block_base(block)+4u*(n))=(v))
static void fence(void){__asm__ volatile("fence iorw,iorw":::"memory");}
static uint64_t clock_ticks(void){
 volatile uint32_t*const timer=(volatile uint32_t*)WIFI64_NIOS_MTIME_BASE;
 uint32_t hi,lo,after;do{hi=timer[1];lo=timer[0];after=timer[1];}while(hi!=after);
 return((uint64_t)hi<<32)|lo;
}
static void output(char c){
 volatile uint32_t*const uart=(volatile uint32_t*)WIFI64_JTAG_UART_BASE;
 static uint64_t began;static unsigned active,dropped;
 if(!active){began=clock_ticks();active=1;dropped=0;}
 if(!dropped){while(!(uart[1]>>16)){if(clock_ticks()-began>100000000u){dropped=1;break;}}}
 if(!dropped)uart[0]=(uint8_t)c;
 if(c=='\n')active=0;
}
#endif
static void text(const char*s){while(*s)output(*s++);}
static void number(uint32_t v){char b[10];unsigned n=0;do{b[n++]=(char)('0'+v%10);v/=10;}while(v);while(n)output(b[--n]);}
static void signed_number(int32_t v){if(v<0){output('-');number(0u-(uint32_t)v);}else number((uint32_t)v);}
static void field(const char*n,uint32_t v){output(',');text(n);output('=');number(v);}
static void signed_field(const char*n,int32_t v){output(',');text(n);output('=');signed_number(v);}
static void hex_field(const char*n,uint32_t v){output(',');text(n);output('=');for(int k=28;k>=0;k-=4){unsigned d=(v>>k)&15;output((char)(d<10?'0'+d:'a'+d-10));}}
static int equal(const char*a,const char*b){while(*a&&*a==*b){a++;b++;}return *a==*b;}
static int integer(const char*s,uint32_t*out){
 uint32_t v=0;if(!*s)return 0;
 while(*s){if(*s<'0'||*s>'9')return 0;unsigned d=(unsigned)(*s++-'0');if(v>429496729u||(v==429496729u&&d>5))return 0;v=v*10+d;}
 *out=v;return 1;
}
typedef struct {uint32_t state,samples,job,source,crc,rate,frequency,errors;} capture_meta;
static w64r_workspace workspace;
static w64r_result result;
static int8_t raw[W64A_MAX_SAMPLES*2];
static capture_meta saved;
static uint32_t result_valid,copied_crc;
static uint64_t elapsed;
static void snapshot(capture_meta*m){
 m->state=READ(0,1);m->samples=READ(0,3);m->job=READ(0,4);m->source=READ(0,5);
 m->crc=READ(0,11);m->rate=READ(0,13);m->frequency=READ(0,14);m->errors=READ(0,10);
}
static int stable(const capture_meta*a,const capture_meta*b){
 return(a->state&0x8b)==2&&(b->state&0x8b)==2&&a->samples==b->samples&&a->job==b->job&&a->source==b->source&&a->crc==b->crc&&a->rate==b->rate&&a->frequency==b->frequency&&a->errors==b->errors;
}
static void prefix(uint32_t id,const char*kind,const char*verb){text("FIR,");number(id);output(',');text(kind);output(',');text(verb);}
static void error(uint32_t id,const char*verb,unsigned code){prefix(id,"ERR",verb);field("error",code);output('\n');}
static void status_fields(void){
 field("state",READ(0,1));field("samples",READ(0,3));field("job",READ(0,4));field("source",READ(0,5));
 field("rate",READ(0,13));field("frequency",READ(0,14));hex_field("raw_crc",READ(0,11));
 field("ddc_busy",READ(1,1)&1u);field("valid",result_valid);field("status",result_valid?result.status:0);
}
static int capture_copy(void){
 capture_meta before,after;snapshot(&before);
 if((before.state&0x8b)!=2||(READ(1,1)&1u))return 2;
 if(before.rate!=40000000||before.source!=0||!before.samples||before.samples>W64A_MAX_SAMPLES)return 3;
 for(unsigned k=0;k<before.samples;k++){
  WRITE(0,6,k);fence();(void)READ(0,7);fence();uint32_t v=READ(0,7);
  raw[2*k]=(int8_t)(v&255u);raw[2*k+1]=(int8_t)((v>>8)&255u);
 }
 snapshot(&after);if(!stable(&before,&after)||(READ(1,1)&1u))return 4;
 copied_crc=w64d_crc32((const uint8_t*)raw,before.samples*2);
 if(copied_crc!=before.crc)return 5;
 /* CRC calculation itself takes time; freeze identity through its completion. */
 snapshot(&after);if(!stable(&before,&after))return 4;
 saved=before;return 0;
}
static void run_fields(void){
 field("valid",result_valid);field("status",result.status);field("stage",result.stage);field("accepted",result.accepted);
 field("rate_code",result.signal.rate_code);field("mbps",result.signal.rate_mbps);field("length",result.signal.psdu_bytes);
 field("points",result.data_points);field("symbols",result.data_symbols);field("packet_status",result.packet.status);
 hex_field("fcs_crc",result.packet.crc_computed);hex_field("received_crc",result.packet.crc_received);
 field("job",saved.job);field("source",saved.source);field("rate",saved.rate);field("frequency",saved.frequency);hex_field("raw_crc",copied_crc);
 field("ticks_lo",(uint32_t)elapsed);field("ticks_hi",(uint32_t)(elapsed>>32));field("clock_hz",50000000);
 field("capture_clips",result.capture_clipped_components);field("frontend_clips",result.frontend.frontend_clips);field("rotation_clips",result.acquisition.rotation_clips);field("equalizer_clips",result.equalizer_clips);
 field("candidates",result.acquisition.candidates);field("attempted",result.candidates_attempted);
 field("signal_status",result.signal.status);field("acquisition_status",result.acquisition.status);field("ltf_index",result.acquisition.ltf_index);
 field("ltf_score",result.acquisition.score_q15);signed_field("cfo_q32",result.acquisition.cfo_q32);
}
static void command(char*line){
 char*tokens[5];unsigned count=0;char*p=line;
 while(*p){while(*p==' '||*p=='\t')p++;if(!*p)break;if(count>=5){error(0,"PARSE",1);return;}tokens[count++]=p;while(*p&&*p!=' '&&*p!='\t')p++;if(*p)*p++=0;}
 uint32_t id=0,index=0;
 if(count<3||!equal(tokens[0],"FIR")||!integer(tokens[1],&id)){error(id,"PARSE",1);return;}
 const char*verb=tokens[2];
 if(READ(0,0)!=0x46495231u){error(id,verb,6);return;}
 if(equal(verb,"WVERSION")&&count==3){
  prefix(id,"OK",verb);field("version",1);field("ram_bytes",WIFI64_NIOS_RAM_BYTES);field("timer_base",WIFI64_NIOS_MTIME_BASE);field("fir_id",READ(0,0));field("ddc_id",READ(1,0));field("host_dsp",0);output('\n');
 }else if(equal(verb,"WSTATUS")&&count==3){prefix(id,"OK",verb);status_fields();output('\n');
 }else if(equal(verb,"WARM")&&count==3){
  if((READ(0,1)&0x89)||(READ(1,1)&1u)){error(id,verb,2);return;}
  result_valid=0;WRITE(0,18,0);fence();if(READ(0,18)){error(id,verb,7);return;}
  WRITE(0,1,1);fence();if((READ(0,1)&3u)!=1){error(id,verb,8);return;}
  prefix(id,"OK",verb);field("state",READ(0,1));field("pair",READ(0,18));output('\n');
 }else if(equal(verb,"WRUN")&&count==3){
  result_valid=0;int copied=capture_copy();if(copied){error(id,verb,(unsigned)copied);return;}
  uint64_t began=clock_ticks();(void)w64r_decode(raw,saved.samples,saved.rate,&workspace,&result);elapsed=clock_ticks()-began;result_valid=1;
  prefix(id,"OK",verb);run_fields();output('\n');
 }else if(equal(verb,"WPOINT")&&count==4&&integer(tokens[3],&index)){
  if(!result_valid||index>=result.data_points){error(id,verb,9);return;}
  prefix(id,"OK",verb);field("index",index);signed_field("i",result.constellation[index].i);signed_field("q",result.constellation[index].q);field("scale",8192);output('\n');
 }else if(equal(verb,"WBYTE")&&count==4&&integer(tokens[3],&index)){
  if(!result_valid||result.stage<4||index>=result.packet.psdu_bytes){error(id,verb,9);return;}
  prefix(id,"OK",verb);field("index",index);field("value",result.packet.psdu[index]);field("packet_status",result.packet.status);output('\n');
 }else error(id,verb,1);
}
static char command_line[96];static unsigned command_used,overflow;
static void input(uint8_t c){
 if(c=='\r')return;
 if(c=='\n'){
  if(overflow)error(0,"PARSE",10);else{command_line[command_used]=0;command(command_line);}
  command_used=overflow=0;
 }else if((c<32&&c!='\t')||c>126)overflow=1;
 else if(command_used<sizeof(command_line)-1)command_line[command_used++]=(char)c;else overflow=1;
}
#ifndef WIFI64_CAPTURE_HOST_TEST
int main(void){
 text("WIFI64_CAPTURE_APP,READY,version=1,tx=0,stage=11\n");
 volatile uint32_t*const uart=(volatile uint32_t*)WIFI64_JTAG_UART_BASE;
 for(;;){uint32_t d=uart[0];if(d&0x8000u)input((uint8_t)d);}
}
#endif
