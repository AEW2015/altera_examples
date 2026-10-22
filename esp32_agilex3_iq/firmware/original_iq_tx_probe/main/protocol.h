#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#define OIQ_ATTEN_MASK (255u<<10)
#define OIQ_ENABLE_MASK (255u<<18)
typedef struct {unsigned code,ms;bool control;unsigned period_us;} oiq_job;
static inline bool oiq_number(const char **p,unsigned *value){
 unsigned n=0,digits=0;while(**p>='0'&&**p<='9'){
  unsigned d=(unsigned)(**p-'0');if(n>25||(n==25&&d>5))return false;
  n=n*10+d;(*p)++;digits++;
 }if(!digits)return false;*value=n;return true;
}
static inline bool oiq_parse(const char *s,oiq_job*j){
 unsigned code=0,ms=0,period=0;bool control,train=false;
 if(!strncmp(s,"ATTEN ",6)){s+=6;control=false;if(!oiq_number(&s,&code)||*s++!=' '||code<120||code>127)return false;}
 else if(!strncmp(s,"LEVEL ",6)){s+=6;control=false;if(!oiq_number(&s,&code)||*s++!=' '||code>127)return false;}
 else if(!strncmp(s,"TRAIN ",6)){s+=6;control=false;train=true;if(!oiq_number(&s,&code)||*s++!=' '||code>127)return false;}
 else if(!strncmp(s,"CONTROL ",8)){s+=8;control=true;}
 else return false;
 if(!oiq_number(&s,&ms)||ms<3||ms>50)return false;
 if(train&&(*s++!=' '||!oiq_number(&s,&period)||period<32||period>128))return false;
 if(*s)return false;
 *j=(oiq_job){code,ms,control,period};return true;
}
/* Only attenuation bits change; the negated-u8 field is the original ROM ABI. */
static inline uint32_t oiq_atten_word(uint32_t original,unsigned code){return (original&~OIQ_ATTEN_MASK)|(((0u-code)&255u)<<10);}
static inline unsigned oiq_atten_code(uint32_t word){return (0u-(word>>10))&255u;}
