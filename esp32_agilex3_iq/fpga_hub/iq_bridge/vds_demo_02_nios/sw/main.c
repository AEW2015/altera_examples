#include <stdint.h>
#ifdef IQMON_HOST_TEST
extern volatile uint32_t test_regs[64],test_jdata,test_jctrl;
#define REG(n) test_regs[(n)]
#define JDATA test_jdata
#define JCTRL test_jctrl
#else
#define REG(n) (*(volatile uint32_t *)(0x10020000u+4u*(n)))
#define JDATA (*(volatile uint32_t *)0x10010000u)
#define JCTRL (*(volatile uint32_t *)0x10010004u)
#endif
static char line[2048];
static uint32_t used,log_drops;
static void text(const char *s) { while(*s && used<sizeof(line))line[used++]=*s++; }
static void number(uint32_t n) {
 char digits[10];uint32_t count=0;
 do { // Explicit software division: Nios V/m implements RV32I, without M.
  uint32_t quotient=0,remainder=0;
  for(int bit=31;bit>=0;--bit){remainder=(remainder<<1)|((n>>bit)&1u);if(remainder>=10){remainder-=10;quotient|=1u<<bit;}}
  digits[count++]=(char)('0'+remainder);n=quotient;
 }while(n);
 while(count && used<sizeof(line))line[used++]=digits[--count];
}
static void hexword(uint32_t n){for(int shift=28;shift>=0;shift-=4){uint32_t v=(n>>shift)&15u;line[used++]=(char)(v<10?'0'+v:'a'+v-10);}}
static void field(const char *name,uint32_t value){text(",");text(name);text("=");number(value);}
static void emit(void){
 // Reserve a complete row. A disconnected/full JTAG FIFO never blocks polling.
 if((JCTRL>>16)<used){log_drops++;return;}
 for(uint32_t i=0;i<used;i++)JDATA=(uint32_t)(unsigned char)line[i];
}
int main(void){
 uint32_t last_sequence=0xffffffffu;
 used=0;text("IQMON_BOOT,rv32i,clock_hz=");number(REG(2));text(",id=");hexword(REG(0));text("\n");emit();
 for(;;){
  uint32_t seq=REG(1);
  if(seq==last_sequence)continue;
  REG(3)=1; // Coherent atomic register snapshot, not a counter reset.
  uint32_t saved=REG(4);
  if(saved==last_sequence)continue;
  last_sequence=saved;
  used=0;text("IQMON");field("seq",saved);
  for(uint32_t source=0;source<3;source++){
   text(",r");number(source);text("_uart_Bps=");number(REG(12+source));
   text(",r");number(source);text("_tx_Bps=");number(REG(51+source));
   text(",r");number(source);text("_iq_Bps=");number(REG(15+source));
   text(",r");number(source);text("_captures=");number(REG(18+source));
  }
  field("host_rx_Bps",REG(21));field("host_uart_Bps",REG(22));field("host_iq_Bps",REG(23));field("host_captures",REG(24));
  field("command_errors",REG(8));field("radio_errors",REG(9));field("capture_errors",REG(10));field("text_drops",REG(11));
  field("log_drops",log_drops);text(",ticks=");hexword(REG(6));hexword(REG(5));
  for(uint32_t index=0;index<16;index++){
   text(",total");number(index);text("=");uint32_t low=index<13?25+2*index:54+2*(index-13);
   hexword(REG(low+1));hexword(REG(low));
  }
  text("\n");emit();
 }
}
