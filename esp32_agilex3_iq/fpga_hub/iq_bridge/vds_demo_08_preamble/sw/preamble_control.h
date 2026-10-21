// Control only: all averaging, differential products, correlation and scoring
// execute in iq_preamble RTL, never on Nios V or the host.
#ifdef IQMON_HOST_TEST
static volatile uint32_t preamble_test_regs[64];
#define PRE(n) preamble_test_regs[(n)]
#else
#define PRE(n) (*(volatile uint32_t *)(0x10070000u+4u*(n)))
#endif
static int pre_hex(char c){
 if(c>='0'&&c<='9')return c-'0';
 if(c>='a'&&c<='f')return c-'a'+10;
 if(c>='A'&&c<='F')return c-'A'+10;
 return -1;
}
static int preamble_command(char **t,uint32_t n,uint32_t id){
 // PAIR and PRESET belong to the existing FIR command namespace.
 if(t[2][0]!='P'||equal(t[2],"PAIR")||equal(t[2],"PRESET"))return 0;
 prefix(id,"ERR");int32_t a=0,b=0,c=0;
 uint32_t state=PRE(1);
 if(equal(t[2],"PSTATUS")&&n==3){
  prefix(id,"OK,PSTATUS");field("identity",PRE(0));field("state",state);
  field("samples",PRE(2));field("sps",PRE(3));field("step",PRE(4));field("threshold",PRE(5));field("min_energy",PRE(6));
  field("cycles",PRE(9));field("best_start",PRE(10));field("best_score",PRE(11));field("candidates",PRE(14));field("errors",PRE(15));
  text(",raw_crc=");hexword(PRE(16));field("job",PRE(17));field("source",PRE(18));field("rate",PRE(19));field("frequency",PRE(20));field("window",PRE(21));field("algorithm",PRE(22));field("written",PRE(27));
 }else if(equal(t[2],"PCLEAR")&&n==3){PRE(1)=1;prefix(id,"OK,PCLEAR");
 }else if(state&9u){text(",BUSY");
 }else if(equal(t[2],"PCONFIG")&&n==6&&integer(t[3],&a)&&integer(t[4],&b)&&integer(t[5],&c)&&a>=1&&a<=16384&&b>=128&&b<=240&&c>=0&&c<=32768){
  PRE(2)=(uint32_t)a;PRE(3)=(uint32_t)b;PRE(4)=4;PRE(5)=(uint32_t)c;PRE(6)=7936;
  prefix(id,"OK,PCONFIG");field("samples",PRE(2));field("sps",PRE(3));field("step",PRE(4));field("threshold",PRE(5));field("min_energy",PRE(6));
 }else if(equal(t[2],"PBEGIN")&&n==3){PRE(1)=2;prefix(id,"OK,PBEGIN");field("written",PRE(27));
 }else if(equal(t[2],"PLOAD")&&n==5&&integer(t[3],&a)&&a>=0&&a<16384){
  uint32_t length=0;while(t[4][length])length++;
  int valid=length>=4&&length<=64&&(length&3u)==0;
  for(uint32_t i=0;i<length;i++)if(pre_hex(t[4][i])<0)valid=0;
  if(valid&&(uint32_t)a==PRE(27)&&(uint32_t)a+length/4u<=PRE(2)){
   PRE(7)=(uint32_t)a;
   for(uint32_t i=0;i<length;i+=4){
    uint32_t lo=(uint32_t)((pre_hex(t[4][i])<<4)|pre_hex(t[4][i+1]));
    uint32_t hi=(uint32_t)((pre_hex(t[4][i+2])<<4)|pre_hex(t[4][i+3]));
    PRE(8)=lo|(hi<<8);
   }
   prefix(id,"OK,PLOAD");field("written",PRE(27));
  }else text(",BAD_LOAD");
 }else if(equal(t[2],"PFINISH")&&n==3){PRE(1)=3;prefix(id,"OK,PFINISH");field("state",PRE(1));field("written",PRE(27));text(",raw_crc=");hexword(PRE(16));
 }else if(equal(t[2],"PRUN")&&n==3){PRE(1)=4;prefix(id,"OK,PRUN");field("state",PRE(1));
 }else if(equal(t[2],"PARM")&&n==4&&integer(t[3],&a)&&a>=0&&a<=2){PRE(31)=(uint32_t)a;PRE(1)=5;prefix(id,"OK,PARM");field("state",PRE(1));
 }else if(equal(t[2],"PTRACES")&&n==5&&integer(t[3],&a)&&integer(t[4],&b)&&a>=0&&b>=1&&b<=32&&(uint32_t)(a+b)<=PRE(14)){
  prefix(id,"OK,PTRACES");field("index",(uint32_t)a);field("count",(uint32_t)b);
  for(int32_t i=0;i<b;i++){PRE(12)=(uint32_t)(a+i);uint32_t value=PRE(13);text(",v");number((uint32_t)i);text("=");number(value);}
 }else text(",BAD_PREAMBLE_COMMAND");
 return 1;
}
