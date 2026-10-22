#pragma once
#include <string.h>
/* Pure parser: no RF action, prefix matches or trailing tokens. */
static inline int txlab_parse_mode(const char *s) {
 if(!strcmp(s,"MODE AMP")) return 0;
 if(!strcmp(s,"MODE NATIVE")) return 1;
 if(!strcmp(s,"MODE PHASE")) return 2;
 return -1;
}
static inline int txlab_selection(unsigned reason_sw,unsigned magic,unsigned mode,unsigned inverse) {
 return reason_sw && magic==0x544c4142u && mode<3 && inverse==~mode ? (int)mode : 0;
}
