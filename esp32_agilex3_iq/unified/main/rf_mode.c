#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "esp_log.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "driver/uart.h"
#include "burst_serial.h"
#include "rf_mode.h"

typedef enum { RF_MONITOR=0, RF_CSI=1, RF_SDR=2 } rf_mode_t;
static rf_mode_t current_mode;
static bool control_started;
static const char *mode_name(rf_mode_t mode)
{
    return mode==RF_CSI ? "CSI" : mode==RF_SDR ? "SDR" : "MONITOR";
}
static void send_response(const char *text, bool sdr)
{
    if (sdr) {
        burst_serial_send(text,strlen(text));
        uart_wait_tx_done(UART_NUM_0,pdMS_TO_TICKS(1000));
    } else {
        fputs(text,stdout); fflush(stdout);
    }
}
bool rf_mode_dispatch(const char *line, bool sdr)
{
    if (!strcmp(line,"MODE?")) {
        char text[80];
        snprintf(text,sizeof(text),"RF_MODE,%s,baud=%u\n",mode_name(current_mode),
                 sdr ? burst_serial_baud() : 115200u);
        send_response(text,sdr); return true;
    }
    if (strncmp(line,"MODE ",5)) return false;
    rf_mode_t next;
    if (!strcmp(line+5,"MONITOR")) next=RF_MONITOR;
    else if (!strcmp(line+5,"CSI")) next=RF_CSI;
    else if (!strcmp(line+5,"SDR")) next=RF_SDR;
    else { send_response("RF_ERROR,mode_must_be_MONITOR_CSI_or_SDR\n",sdr); return true; }
    nvs_handle_t handle;
    esp_err_t err=nvs_open("rf_suite",NVS_READWRITE,&handle);
    if (err==ESP_OK) {
        err=nvs_set_u8(handle,"mode",(uint8_t)next);
        if (err==ESP_OK) err=nvs_commit(handle);
        nvs_close(handle);
    }
    if (err!=ESP_OK) { send_response("RF_ERROR,cannot_save_mode\n",sdr); return true; }
    char text[80];
    snprintf(text,sizeof(text),"RF_MODE_ACK,%s,rebooting\n",mode_name(next));
    send_response(text,sdr);
    vTaskDelay(pdMS_TO_TICKS(150));
    esp_restart();
    return true;
}
static void control_task(void *unused)
{
    char line[80]; size_t used=0; bool overflow=false;
    for (;;) {
        char c;
        if (read(STDIN_FILENO,&c,1)!=1) { vTaskDelay(pdMS_TO_TICKS(10)); continue; }
        if (c=='\r') continue;
        if (c=='\n') {
            line[used]=0;
            if (!overflow) rf_mode_dispatch(line,false);
            memset(line,0,sizeof(line)); used=0; overflow=false;
        } else if (used<sizeof(line)-1) line[used++]=c;
        else overflow=true;
    }
}
void rf_control_start(void)
{
    if (!control_started) {
        control_started=true;
        configASSERT(xTaskCreate(control_task,"rf_control",3072,NULL,2,NULL)==pdPASS);
    }
}
void rf_monitor_main(void);
void rf_csi_main(void);
void rf_sdr_main(void);
void app_main(void)
{
#ifdef IQ_SPI_RX_PROFILE
    // Explicit separate qualification profile; never use a saved MONITOR/CSI mode.
    current_mode=RF_SDR;
    rf_sdr_main();
    return;
#endif
    esp_err_t err=nvs_flash_init();
    if (err==ESP_ERR_NVS_NO_FREE_PAGES || err==ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase()); err=nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);
    nvs_handle_t handle; uint8_t saved=0;
    err=nvs_open("rf_suite",NVS_READONLY,&handle);
    if (err==ESP_OK) { nvs_get_u8(handle,"mode",&saved); nvs_close(handle); }
    current_mode=saved<=RF_SDR ? (rf_mode_t)saved : RF_MONITOR;
    printf("RF_SUITE,v1,mode=%s,run_baud=%u\n",mode_name(current_mode),current_mode==RF_SDR?2000000u:115200u);
    fflush(stdout);
    vTaskDelay(pdMS_TO_TICKS(250));
    if (current_mode==RF_MONITOR) { rf_control_start(); rf_monitor_main(); }
    else if (current_mode==RF_CSI) rf_csi_main();
    else rf_sdr_main();
}
