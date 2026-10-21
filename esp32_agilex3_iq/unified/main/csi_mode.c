#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/event_groups.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "nvs_flash.h"
#include "rf_mode.h"
#include "ping/ping_sock.h"

#define WIFI_SSID "YOUR_2G4_SSID"
#define CONNECTED BIT0
#define CSI_MAX_BYTES 256
static EventGroupHandle_t events;
static QueueHandle_t queue;
static portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
static uint8_t ap_mac[6];
static bool have_ap;
static uint32_t seen, dropped, ping_replies;
typedef struct {
    uint32_t sequence, timestamp;
    int8_t rssi, noise;
    uint8_t channel, rate, mode, invalid;
    uint16_t length;
    int8_t samples[CSI_MAX_BYTES];
} record_t;

static const char *disconnect_reason(uint8_t reason)
{
    switch (reason) {
    case WIFI_REASON_NO_AP_FOUND: return "no_ap_found";
    case WIFI_REASON_AUTH_EXPIRE: return "auth_timeout";
    case WIFI_REASON_AUTH_FAIL: return "auth_failed";
    case WIFI_REASON_ASSOC_FAIL: return "association_failed";
    case WIFI_REASON_4WAY_HANDSHAKE_TIMEOUT: return "four_way_handshake_timeout";
    case WIFI_REASON_HANDSHAKE_TIMEOUT: return "handshake_timeout";
    case WIFI_REASON_NO_AP_FOUND_W_COMPATIBLE_SECURITY: return "no_compatible_security";
    case WIFI_REASON_NO_AP_FOUND_IN_AUTHMODE_THRESHOLD: return "authmode_threshold";
    case WIFI_REASON_NO_AP_FOUND_IN_RSSI_THRESHOLD: return "rssi_threshold";
    default: return "other";
    }
}

static void wifi_event(void *ctx, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        ESP_ERROR_CHECK(esp_wifi_connect());
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        portENTER_CRITICAL(&lock);
        have_ap = false;
        portEXIT_CRITICAL(&lock);
        xEventGroupClearBits(events, CONNECTED);
        const wifi_event_sta_disconnected_t *disconnected = data;
        printf("STATUS,disconnected,reason=%u,detail=%s,retrying\n",
               disconnected->reason, disconnect_reason(disconnected->reason));
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        wifi_ap_record_t ap;
        ESP_ERROR_CHECK(esp_wifi_sta_get_ap_info(&ap));
        portENTER_CRITICAL(&lock);
        memcpy(ap_mac, ap.bssid, 6);
        have_ap = true;
        portEXIT_CRITICAL(&lock);
        printf("STATUS,connected,channel=%u,rssi=%d\n", ap.primary, ap.rssi);
        xEventGroupSetBits(events, CONNECTED);
    }
}

static void csi_received(void *ctx, wifi_csi_info_t *info)
{
    if (!info || !info->buf || !info->len) return;
    record_t record = {0};
    portENTER_CRITICAL(&lock);
    bool accept = have_ap && !memcmp(ap_mac, info->mac, 6);
    if (accept) record.sequence = ++seen;
    portEXIT_CRITICAL(&lock);
    if (!accept) return;
    if (info->len > CSI_MAX_BYTES || info->rx_ctrl.rx_state != 0) {
        portENTER_CRITICAL(&lock);
        dropped++;
        portEXIT_CRITICAL(&lock);
        return;
    }
    record.timestamp = info->rx_ctrl.timestamp;
    record.rssi = info->rx_ctrl.rssi;
    record.noise = info->rx_ctrl.noise_floor;
    record.channel = info->rx_ctrl.channel;
    record.rate = info->rx_ctrl.rate;
    record.mode = info->rx_ctrl.sig_mode;
    record.invalid = info->first_word_invalid;
    record.length = info->len;
    memcpy(record.samples, info->buf, info->len);
    if (xQueueSend(queue, &record, 0) != pdTRUE) {
        portENTER_CRITICAL(&lock);
        dropped++;
        portEXIT_CRITICAL(&lock);
    }
}

static void ping_success(esp_ping_handle_t handle, void *args)
{
    portENTER_CRITICAL(&lock);
    ping_replies++;
    portEXIT_CRITICAL(&lock);
}

static void output_task(void *args)
{
    record_t record;
    char hex[CSI_MAX_BYTES * 2 + 1];
    const char *digits = "0123456789abcdef";
    int64_t last = esp_timer_get_time();
    for (;;) {
        if (xQueueReceive(queue, &record, pdMS_TO_TICKS(100)) == pdTRUE) {
            for (int i=0; i<record.length; ++i) {
                uint8_t v = (uint8_t)record.samples[i];
                hex[i*2] = digits[v >> 4]; hex[i*2+1] = digits[v & 15];
            }
            hex[record.length*2] = 0;
            printf("CSI,%" PRIu32 ",%" PRIu32 ",%u,%d,%d,%u,%u,%u,%u,%s\n",
                   record.sequence, record.timestamp, record.channel, record.rssi,
                   record.noise, record.rate, record.mode, record.invalid,
                   record.length, hex);
        }
        if (esp_timer_get_time()-last > 5000000) {
            portENTER_CRITICAL(&lock);
            uint32_t count=seen, lost=dropped, replies=ping_replies;
            portEXIT_CRITICAL(&lock);
            printf("STATUS,seen=%" PRIu32 ",dropped=%" PRIu32 ",ping_replies=%" PRIu32 "\n",
                   count, lost, replies);
            last=esp_timer_get_time();
        }
    }
}

/* The local host sends PW:<password><LF>; credentials are RAM-only. */
static void read_password(uint8_t password[64])
{
    char line[72] = {0};
    size_t used = 0;
    bool overflow = false;
    int64_t prompt = -5000000;
    for (;;) {
        if (esp_timer_get_time()-prompt >= 5000000) {
            puts("PASSWORD_REQUIRED," WIFI_SSID);
            fflush(stdout);
            prompt=esp_timer_get_time();
        }
        char c;
        if (read(STDIN_FILENO, &c, 1) != 1) { vTaskDelay(pdMS_TO_TICKS(10)); continue; }
        if (c == '\r') continue;
        if (c == '\n') {
            line[used]=0;
            if (!overflow && rf_mode_dispatch(line, false)) {
                memset(line,0,sizeof(line)); used=0; overflow=false; continue;
            }
            if (!overflow && used >= 11 && used <= 66 && !memcmp(line,"PW:",3)) {
                memcpy(password,line+3,used-3);
                memset(line,0,sizeof(line));
                return;
            }
            memset(line,0,sizeof(line)); used=0; overflow=false;
            puts("STATUS,password_length_must_be_8_to_63_bytes");
        } else if (used < sizeof(line)-1) line[used++]=c;
        else overflow=true;
    }
}

void rf_csi_main(void)
{
    esp_err_t err=nvs_flash_init();
    if (err==ESP_ERR_NVS_NO_FREE_PAGES || err==ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase()); err=nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);
    events=xEventGroupCreate(); queue=xQueueCreate(24,sizeof(record_t));
    configASSERT(events && queue);
    wifi_config_t wifi={0};
    memcpy(wifi.sta.ssid, WIFI_SSID, sizeof(WIFI_SSID));
    read_password(wifi.sta.password);
    rf_control_start();
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_t *netif=esp_netif_create_default_wifi_sta();
    configASSERT(netif);
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT,ESP_EVENT_ANY_ID,wifi_event,NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT,IP_EVENT_STA_GOT_IP,wifi_event,NULL));
    wifi_init_config_t init=WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA,&wifi));
    memset(wifi.sta.password,0,sizeof(wifi.sta.password));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    xEventGroupWaitBits(events,CONNECTED,pdFALSE,pdTRUE,portMAX_DELAY);
    wifi_csi_config_t csi={.lltf_en=true,.htltf_en=false,.stbc_htltf2_en=false,
        .ltf_merge_en=false,.channel_filter_en=false,.manu_scale=false};
    ESP_ERROR_CHECK(esp_wifi_set_csi_config(&csi));
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(csi_received,NULL));
    puts("type,sequence,timestamp_us,channel,rssi_dbm,noise_dbm,rate,sig_mode,first_word_invalid,length,iq_hex");
    configASSERT(xTaskCreate(output_task,"csi_output",4096,NULL,3,NULL)==pdPASS);
    ESP_ERROR_CHECK(esp_wifi_set_csi(true));
    esp_netif_ip_info_t ip;
    ESP_ERROR_CHECK(esp_netif_get_ip_info(netif,&ip));
    esp_ping_config_t ping=ESP_PING_DEFAULT_CONFIG();
    ping.count=ESP_PING_COUNT_INFINITE; ping.interval_ms=50; ping.timeout_ms=100;
    ping.data_size=16; ping.target_addr.type=IPADDR_TYPE_V4;
    ping.target_addr.u_addr.ip4.addr=ip.gw.addr;
    esp_ping_callbacks_t callbacks={.on_ping_success=ping_success};
    esp_ping_handle_t handle;
    ESP_ERROR_CHECK(esp_ping_new_session(&ping,&callbacks,&handle));
    ESP_ERROR_CHECK(esp_ping_start(handle));
}
