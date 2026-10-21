#include "probe_protocol.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <ctype.h>
#include <errno.h>
bool probe_parse_tone(const char *line, probe_job_t *job) {
    bool nco=!strncmp(line,"NCO ",4),fast=!strncmp(line,"FASTPHASE ",10),frame=!strncmp(line,"FRAME ",6),qframe=!strncmp(line,"QFRAME ",7);
    bool phase=!strncmp(line,"PHASE ",6)||fast||frame||qframe;
    if (!phase && !nco && strncmp(line, "TONE ", 5)) return false;
    const char *p=line+(fast?10:qframe?7:phase?6:nco?4:5); unsigned long values[8]={0};
    for (unsigned i=0;i<(qframe?8:fast?7:phase?6:nco?4:3);i++) {
        while (*p==' ') p++;
        if (!isdigit((unsigned char)*p)) return false;
        errno=0; char *end;
        values[i]=strtoul(p,&end,10);
        if (errno || end==p || (*end && *end!=' ')) return false;
        p=end;
    }
    while (*p==' ') p++;
    if (*p || values[0]<1 || values[0]>11 || values[1]<50 || values[1]>3000 ||
        values[2]<80 || values[2]>120 || (nco && values[3]>32) ||
        (phase && (values[1]>500 || values[3]>255 || values[4]<(fast||frame||qframe?8:32) || values[4]>256 || values[5]>8192)) ||
        (fast && (values[6]<1 || values[6]>3)) ||
        (qframe && (!values[5] || !values[6] || !values[7] || values[6]>8192 || values[7]>8192))) return false;
    *job=(probe_job_t){.channel=values[0],.duration_ms=values[1],.backoff_qdb=values[2],.nco_step=nco?values[3]:qframe?0x203:frame?0x103:fast?values[6]:0,.nco=nco,.phase=phase,.pattern=values[3],.symbol_us=values[4],.pulse_cycles=values[5],.pulse180_cycles=qframe?values[6]:0,.pulse270_cycles=qframe?values[7]:0}; return true;
}

static uint8_t parity7(uint8_t x) { x^=x>>4;x^=x>>2;x^=x>>1;return x&1; }
void probe_frame_bits(uint16_t payload, uint8_t bits[64]) {
    const uint16_t marker=0x0651;
    uint8_t crc=0,state=0;
    for (unsigned i=0;i<16;i++) bits[i]=(marker>>(15-i))&1;
    for (unsigned i=0;i<8;i++) {
        unsigned feedback=((crc>>7)^((payload>>(7-i))&1))&1;
        crc=(uint8_t)(crc<<1);if (feedback) crc^=7;
    }
    uint32_t word=(((uint32_t)(payload&255)<<8)|crc)<<6;
    for (unsigned i=0;i<22;i++) {
        uint8_t reg=(state<<1)|((word>>(21-i))&1);
        bits[16+2*i]=parity7(reg&0171);bits[17+2*i]=parity7(reg&0133);
        state=reg&63;
    }
    for(unsigned i=60;i<64;i++) bits[i]=0;
}

/* Gray-labelled cardinal phase states, negative quarter-turns on measured RF.
 * Training is fixed and independent of the payload. */
void probe_qframe_states(uint16_t payload, uint8_t states[64]) {
    static const char training[]="01320312023110233012032120310302";
    uint8_t bits[64]; probe_frame_bits(payload,bits);
    for(unsigned i=0;i<32;i++) states[i]=training[i]-'0';
    for(unsigned i=0;i<22;i++) {
        unsigned a=bits[16+2*i],b=bits[17+2*i];
        states[32+i]=(a<<1)|(a^b);
    }
    for(unsigned i=54;i<64;i++) states[i]=0;
}

bool probe_cycle_budget(uint32_t cpu_hz, int64_t remaining_us, uint32_t *cycles) {
    if (!cycles || !cpu_hz || remaining_us<=0 || remaining_us>500000) return false;
    uint64_t budget=(uint64_t)cpu_hz*(uint64_t)remaining_us/1000000u;
    if (!budget || budget>INT32_MAX) return false;
    *cycles=(uint32_t)budget; return true;
}
