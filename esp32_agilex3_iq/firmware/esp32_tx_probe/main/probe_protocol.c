#include "probe_protocol.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <ctype.h>
#include <errno.h>
bool probe_parse_tone(const char *line, probe_job_t *job) {
    bool nco=!strncmp(line,"NCO ",4);
    if (!nco && strncmp(line, "TONE ", 5)) return false;
    const char *p=line+(nco?4:5); unsigned long values[4]={0};
    for (unsigned i=0;i<(nco?4:3);i++) {
        while (*p==' ') p++;
        if (!isdigit((unsigned char)*p)) return false;
        errno=0; char *end;
        values[i]=strtoul(p,&end,10);
        if (errno || end==p || (*end && *end!=' ')) return false;
        p=end;
    }
    while (*p==' ') p++;
    if (*p || values[0]<1 || values[0]>11 || values[1]<50 || values[1]>3000 ||
        values[2]<80 || values[2]>120 || (nco && values[3]>32)) return false;
    *job=(probe_job_t){.channel=values[0],.duration_ms=values[1],.backoff_qdb=values[2],.nco_step=values[3],.nco=nco}; return true;
}
