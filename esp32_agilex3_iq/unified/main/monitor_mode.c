#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "nvs_flash.h"
#include "wifi_inventory.h"
#include "esp_log.h"

typedef struct {
    uint32_t frames, bytes, management, control, data, bad;
    int64_t rssi_sum;
    int rssi_min, rssi_max;
} stats_t;
static portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
static stats_t stats;
static uint8_t active_channel;
#define AP_LIMIT 64
typedef struct {
    bool used;
    wifi_advertisement_t advertisement;
    int rssi;
    uint32_t seen, window_seen;
    int64_t last_seen_us;
} ap_entry_t;
static ap_entry_t access_points[AP_LIMIT];
static uint32_t inventory_full;
static void inventory_receive(const wifi_promiscuous_pkt_t *packet)
{
    if (packet->rx_ctrl.sig_len < 4) return;
    wifi_advertisement_t advertisement;
    if (!wifi_parse_advertisement(packet->payload,packet->rx_ctrl.sig_len-4,&advertisement)) return;
    if (!advertisement.channel) advertisement.channel=packet->rx_ctrl.channel;
    int64_t now=esp_timer_get_time();
    portENTER_CRITICAL(&lock);
    int match=-1, free_slot=-1;
    for (int i=0; i<AP_LIMIT; ++i) {
        if (access_points[i].used && !memcmp(access_points[i].advertisement.bssid,advertisement.bssid,6)) { match=i; break; }
        if (!access_points[i].used && free_slot<0) free_slot=i;
    }
    if (match<0) match=free_slot;
    if (match>=0) {
        ap_entry_t *entry=&access_points[match];
        if (!advertisement.ssid_len && entry->used && entry->advertisement.ssid_len) {
            advertisement.ssid_len=entry->advertisement.ssid_len;
            memcpy(advertisement.ssid,entry->advertisement.ssid,advertisement.ssid_len);
        }
        entry->used=true; entry->advertisement=advertisement;
        entry->rssi=packet->rx_ctrl.rssi; entry->last_seen_us=now;
        entry->seen++; entry->window_seen++;
    } else inventory_full++;
    portEXIT_CRITICAL(&lock);
}
static void inventory_report(int64_t end)
{
    for (int i=0; i<AP_LIMIT; ++i) {
        portENTER_CRITICAL(&lock);
        ap_entry_t entry=access_points[i]; access_points[i].window_seen=0;
        portEXIT_CRITICAL(&lock);
        if (!entry.used || !entry.window_seen) continue;
        const wifi_advertisement_t *a=&entry.advertisement;
        char hex[65]; const char *digits="0123456789abcdef";
        for (unsigned j=0; j<a->ssid_len; ++j) {
            hex[2*j]=digits[a->ssid[j]>>4]; hex[2*j+1]=digits[a->ssid[j]&15];
        }
        hex[2*a->ssid_len]=0;
        printf("AP,%" PRId64 ",%02x:%02x:%02x:%02x:%02x:%02x,%u,%d,%" PRIu32 ",%" PRIu32 ",%" PRId64 ",%s,%s\n",
               end,a->bssid[0],a->bssid[1],a->bssid[2],a->bssid[3],a->bssid[4],a->bssid[5],
               a->channel,entry.rssi,entry.window_seen,entry.seen,entry.last_seen_us,a->security,hex);
    }
    printf("INVENTORY,%" PRId64 ",full=%" PRIu32 "\n",end,inventory_full);
}

/* Wi-Fi task callback: aggregate metadata only; never block or print here. */
static void receive(void *buffer, wifi_promiscuous_pkt_type_t type)
{
    if (!buffer || type == WIFI_PKT_MISC) return;
    const wifi_promiscuous_pkt_t *packet = buffer;
    const wifi_pkt_rx_ctrl_t *rx = &packet->rx_ctrl;
    portENTER_CRITICAL(&lock);
    if (rx->channel == active_channel) {
        if (rx->rx_state != 0) {
            stats.bad++;
        } else {
            if (!stats.frames || rx->rssi < stats.rssi_min) stats.rssi_min = rx->rssi;
            if (!stats.frames || rx->rssi > stats.rssi_max) stats.rssi_max = rx->rssi;
            stats.frames++;
            stats.bytes += rx->sig_len;
            stats.rssi_sum += rx->rssi;
            if (type == WIFI_PKT_MGMT) stats.management++;
            if (type == WIFI_PKT_CTRL) stats.control++;
            if (type == WIFI_PKT_DATA) stats.data++;
        }
    }
    portEXIT_CRITICAL(&lock);
    if (type == WIFI_PKT_MGMT && rx->rx_state == 0) inventory_receive(packet);
}

void rf_monitor_main(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    wifi_init_config_t config = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&config));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_NULL));
    ESP_ERROR_CHECK(esp_wifi_start());
    wifi_promiscuous_filter_t filter = {
        .filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT | WIFI_PROMIS_FILTER_MASK_CTRL |
                       WIFI_PROMIS_FILTER_MASK_DATA
    };
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous_filter(&filter));
    wifi_promiscuous_filter_t ctrl = {.filter_mask = WIFI_PROMIS_CTRL_FILTER_MASK_ALL};
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous_ctrl_filter(&ctrl));
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous_rx_cb(receive));
    esp_log_level_set("wifi", ESP_LOG_WARN);
    puts("RFS2_WIFI_MONITOR,v2,passive_ap_inventory,uart0=115200");
    puts("AP_COLUMNS,type,end_us,bssid,advertised_channel,rssi_dbm,window_advertisements,total_advertisements,last_seen_us,security,ssid_hex");
    puts("end_us,channel,dwell_us,frames,bytes,management,control,data,bad_rx,rssi_mean_dbm,rssi_min_dbm,rssi_max_dbm");
    uint8_t channel = CONFIG_MONITOR_CHANNEL ? CONFIG_MONITOR_CHANNEL : 1;
    for (;;) {
        ESP_ERROR_CHECK(esp_wifi_set_channel(channel, WIFI_SECOND_CHAN_NONE));
        portENTER_CRITICAL(&lock);
        memset(&stats, 0, sizeof(stats));
        active_channel = channel;
        portEXIT_CRITICAL(&lock);
        int64_t start = esp_timer_get_time();
        ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));
        vTaskDelay(pdMS_TO_TICKS(CONFIG_MONITOR_DWELL_MS));
        ESP_ERROR_CHECK(esp_wifi_set_promiscuous(false));
        int64_t end = esp_timer_get_time();
        portENTER_CRITICAL(&lock);
        stats_t snapshot = stats;
        portEXIT_CRITICAL(&lock);
        printf("%" PRId64 ",%u,%" PRId64 ",%" PRIu32 ",%" PRIu32 ",%" PRIu32
               ",%" PRIu32 ",%" PRIu32 ",%" PRIu32 ",", end, channel, end-start,
               snapshot.frames, snapshot.bytes, snapshot.management, snapshot.control,
               snapshot.data, snapshot.bad);
        if (snapshot.frames) {
            printf("%.2f,%d,%d\n", (double)snapshot.rssi_sum / snapshot.frames,
                   snapshot.rssi_min, snapshot.rssi_max);
        } else puts(",,");
        inventory_report(end);
        if (!CONFIG_MONITOR_CHANNEL) channel = channel == 11 ? 1 : channel + 1;
    }
}
