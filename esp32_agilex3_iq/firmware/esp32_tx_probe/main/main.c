/* Original ESP32 bounded carrier diagnostic. No arbitrary IQ TX is claimed.
 * RF calls use esp_phy_cert_test.h; no guessed playback registers are written.
 */
#include <stdio.h>
#include <string.h>
#include <inttypes.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "driver/uart.h"
#include "esp_chip_info.h"
#include "esp_mac.h"
#include "esp_phy_cert_test.h"
#include "esp_phy_init.h"
#include "esp_timer.h"
#include "esp_private/periph_ctrl.h"
#include "soc/periph_defs.h"
#include "nvs_flash.h"
#include "probe_protocol.h"
static QueueHandle_t jobs;
static volatile bool busy, cancel;
static bool initialized;
static uint32_t job_id;
static void worker(void *unused) {
    probe_job_t job;
    for (;;) {
        if (xQueueReceive(jobs,&job,portMAX_DELAY)!=pdTRUE) continue;
        if (!initialized) {
            esp_wifi_power_domain_on();
            periph_module_enable(PERIPH_WIFI_MODULE);
            esp_phy_enable(PHY_MODEM_WIFI);
            esp_phy_rftest_config(1);
            esp_phy_rftest_init();
            esp_phy_tx_contin_en(false);
            esp_phy_cbw40m_en(false);
            initialized=true;
        }
        const uint32_t id=++job_id;
        int64_t started=0;
        if (!cancel) {
            esp_phy_test_start_stop(3);
            esp_phy_wifi_tx_tone(1,job.channel,job.backoff_qdb);
            started=esp_timer_get_time();
            printf("TX_ON,id=%"PRIu32",channel=%"PRIu32",backoff_qdb=%"PRIu32",limit_ms=%"PRIu32"\n",id,job.channel,job.backoff_qdb,job.duration_ms);
            while (!cancel && esp_timer_get_time()-started<(int64_t)job.duration_ms*1000)
                vTaskDelay(pdMS_TO_TICKS(5));
        }
        esp_phy_wifi_tx_tone(0,job.channel,job.backoff_qdb);
        esp_phy_test_start_stop(0);
        printf("TX_OFF,id=%"PRIu32",elapsed_us=%"PRIi64",reason=%s\n",id,started?esp_timer_get_time()-started:0,cancel?"stop":"deadline");
        busy=false;
    }
}
static void command(char *line) {
    if (!strcmp(line,"INFO")) {
        uint8_t mac[6]; esp_chip_info_t chip;
        ESP_ERROR_CHECK(esp_read_mac(mac,ESP_MAC_WIFI_STA)); esp_chip_info(&chip);
        printf("TX_PROBE,v=1,rev=%d,mac=%02x:%02x:%02x:%02x:%02x:%02x,tx=%d,rx=%d,baud=2000000,busy=%d,iq=unverified\n",chip.revision,mac[0],mac[1],mac[2],mac[3],mac[4],mac[5],CONFIG_ESP_SDR_UART_TX_PIN,CONFIG_ESP_SDR_UART_RX_PIN,busy);
    } else if (!strcmp(line,"STOP")) {
        cancel=true;
        printf("STOP_REQUESTED,busy=%d\n",busy);
    } else {
        probe_job_t job;
        if (!probe_parse_tone(line,&job)) { puts("ERR use_INFO_STOP_or_TONE_channel_1to11_ms_50to3000_backoff_80to120"); return; }
        if (busy) { puts("ERR busy"); return; }
        cancel=false; busy=true;
        if (xQueueSend(jobs,&job,0)!=pdTRUE) { busy=false; puts("ERR queue"); return; }
        puts("TX_QUEUED");
    }
}
void app_main(void) {
    setvbuf(stdout,NULL,_IONBF,0);
    ESP_ERROR_CHECK(nvs_flash_init());
    uart_config_t cfg={.baud_rate=2000000,.data_bits=UART_DATA_8_BITS,.parity=UART_PARITY_DISABLE,.stop_bits=UART_STOP_BITS_1,.flow_ctrl=UART_HW_FLOWCTRL_DISABLE,.source_clk=UART_SCLK_DEFAULT};
    ESP_ERROR_CHECK(uart_param_config(UART_NUM_0,&cfg));
    ESP_ERROR_CHECK(uart_set_pin(UART_NUM_0,CONFIG_ESP_SDR_UART_TX_PIN,CONFIG_ESP_SDR_UART_RX_PIN,UART_PIN_NO_CHANGE,UART_PIN_NO_CHANGE));
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0,2048,0,0,NULL,0));
    jobs=xQueueCreate(1,sizeof(probe_job_t)); configASSERT(jobs);
    configASSERT(xTaskCreate(worker,"bounded_tx",4096,NULL,5,NULL)==pdPASS);
    puts("TX_PROBE_READY,rf=off,commands=INFO_STOP_TONE,iq_playback=unverified");
    char line[96]; unsigned used=0; bool overflow=false;
    for (;;) {
        uint8_t c;
        if (uart_read_bytes(UART_NUM_0,&c,1,pdMS_TO_TICKS(20))!=1) continue;
        if (c=='\r') continue;
        if (c=='\n') {
            line[used]=0;
            if (overflow) puts("ERR line_too_long"); else if(used) command(line);
            used=0; overflow=false;
        } else if (used<sizeof(line)-1) line[used++]=(char)c;
        else overflow=true;
    }
}
