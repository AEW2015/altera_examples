#include "burst_version.h"
#include "burst_serial.h"
#include "build_version.h"
#include <string.h>

/* The exporter reads this same NUL-terminated record from the app image.
 * Keep the marker and JSON together so packaging cannot substitute metadata. */
static const char version_record[] = ESP_SDR_VERSION_RECORD;

bool burst_version_command(const char *line) {
    if (strcmp(line, "VERSION?")) return false;
    const char *json = version_record + sizeof("ESP-SDR-VERSION:") - 1;
    burst_serial_send("VERSION ", 8);
    burst_serial_send(json, strlen(json));
    burst_serial_send("\n", 1);
    return true;
}
