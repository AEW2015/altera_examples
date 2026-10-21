#ifndef RF_MODE_H
#define RF_MODE_H
#include <stdbool.h>
bool rf_mode_dispatch(const char *line, bool sdr_transport);
void rf_control_start(void);
#endif
