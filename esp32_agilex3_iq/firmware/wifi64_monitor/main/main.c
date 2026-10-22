/* Independent original ESP32 native monitor. No TX API or association. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#include "protocol.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "driver/uart.h"
#include "esp_wifi.h"
#include "esp_timer.h"
#include "nvs_flash.h"
typedef struct {uint8_t frame[88];int8_t rssi;uint8_t rate,mode,channel,rx_state;uint32_t timestamp,length;} record;
static QueueHandle_t records;
static volatile uint32_t matched,drops;
static bool listening;
static int64_t until;
static unsigned channel=8;
static uint32_t u32(const uint8_t*p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void receive(void *data,wifi_promiscuous_pkt_type_t type){
 if(type!=WIFI_PKT_DATA)return;
 const wifi_promiscuous_pkt_t *p=data;
 if(p->rx_ctrl.sig_len<92||memcmp(p->payload+24,"W64A",4))return;
 record r;memcpy(r.frame,p->payload,88);r.rssi=p->rx_ctrl.rssi;r.rate=p->rx_ctrl.rate;r.mode=p->rx_ctrl.sig_mode;r.channel=p->rx_ctrl.channel;r.timestamp=p->rx_ctrl.timestamp;r.length=p->rx_ctrl.sig_len;r.rx_state=p->rx_ctrl.rx_state;
 matched++;if(xQueueSend(records,&r,0)!=pdPASS)drops++;
}
static void report(record*r){
 uint8_t expected[88];uint32_t run=u32(r->frame+32),packet=u32(r->frame+36),seed=u32(r->frame+40);
 w64_frame(expected,r->frame+10,run,packet,seed);
 /* MAC duration/sequence may be driver-updated; compare full deterministic body. */
 unsigned body_ok=!memcmp(expected+24,r->frame+24,64);
 printf("WIFI64_MON,PACKET,run=%"PRIu32",packet=%"PRIu32",seed=%"PRIu32",body_ok=%u\n",run,packet,seed,body_ok);
 vTaskDelay(pdMS_TO_TICKS(2));
 printf("WIFI64_MON,PHY,run=%"PRIu32",packet=%"PRIu32",rate_code=%u,sig_mode=%u,rssi=%d,ch=%u,rx_state=%u\n",run,packet,r->rate,r->mode,r->rssi,r->channel,r->rx_state);
 vTaskDelay(pdMS_TO_TICKS(2));
 printf("WIFI64_MON,META,run=%"PRIu32",packet=%"PRIu32",timestamp_us=%"PRIu32",length=%"PRIu32",native_rx=1\n",run,packet,r->timestamp,r->length);
 vTaskDelay(pdMS_TO_TICKS(2));
}
static void stop(void){
 esp_err_t e=esp_wifi_set_promiscuous(false);
 if(e==ESP_OK)listening=false;
 printf("WIFI64_MON,STOP,listening=%u,error=%d\n",listening,(int)e);
}
static void command(char*s){
 unsigned ch,ms;char extra;
 if(!strcmp(s,"INFO"))puts("WIFI64_MON,INFO,v=1,chip=esp32,uart=2000000,passive=1");
 else if(!strcmp(s,"STATUS"))printf("WIFI64_MON,STATUS,listening=%u,ch=%u,matched=%"PRIu32",drops=%"PRIu32"\n",listening,channel,matched,drops);
 else if(!strcmp(s,"STOP"))stop();
 else if(sscanf(s,"LISTEN %u %u %c",&ch,&ms,&extra)==2&&ch>=1&&ch<=11&&ms>=10&&ms<=10000&&!listening){
  esp_err_t e=esp_wifi_set_channel(ch,WIFI_SECOND_CHAN_NONE);
  if(e==ESP_OK)e=esp_wifi_set_promiscuous(true);
  if(e==ESP_OK){channel=ch;listening=true;until=esp_timer_get_time()+(int64_t)ms*1000;}
  printf("WIFI64_MON,LISTEN,ok=%u,ch=%u,ms=%u,error=%d\n",listening,ch,ms,(int)e);
 }else puts("WIFI64_MON,ERR,command_or_busy");
}
void app_main(void){
 /* No erase fallback: do not silently destroy an old installation's NVS. */
 ESP_ERROR_CHECK(nvs_flash_init());
 uart_config_t u={.baud_rate=2000000,.data_bits=UART_DATA_8_BITS,.parity=UART_PARITY_DISABLE,.stop_bits=UART_STOP_BITS_1,.flow_ctrl=UART_HW_FLOWCTRL_DISABLE,.source_clk=UART_SCLK_DEFAULT};
 ESP_ERROR_CHECK(uart_param_config(UART_NUM_0,&u));ESP_ERROR_CHECK(uart_set_pin(UART_NUM_0,17,16,UART_PIN_NO_CHANGE,UART_PIN_NO_CHANGE));ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0,1024,0,0,NULL,0));setvbuf(stdout,NULL,_IONBF,0);
 records=xQueueCreate(16,sizeof(record));if(!records)abort();
 wifi_init_config_t cfg=WIFI_INIT_CONFIG_DEFAULT();ESP_ERROR_CHECK(esp_wifi_init(&cfg));ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_NULL));ESP_ERROR_CHECK(esp_wifi_start());ESP_ERROR_CHECK(esp_wifi_set_promiscuous_rx_cb(receive));
 wifi_promiscuous_filter_t filter={.filter_mask=WIFI_PROMIS_FILTER_MASK_DATA};ESP_ERROR_CHECK(esp_wifi_set_promiscuous_filter(&filter));
 puts("WIFI64_MON,READY,listening=0,tx=disabled");char line[96];unsigned n=0;bool overflow=false;
 for(;;){
  if(listening&&esp_timer_get_time()>=until)stop();
  record r;while(xQueueReceive(records,&r,0)==pdPASS)report(&r);
  uint8_t c;if(uart_read_bytes(UART_NUM_0,&c,1,pdMS_TO_TICKS(2))!=1)continue;
  if(c=='\r')continue;
  if(c=='\n'){if(overflow)puts("WIFI64_MON,ERR,line_too_long");else{line[n]=0;command(line);}n=0;overflow=false;}
  else if(n<sizeof(line)-1)line[n++]=(char)c;else overflow=true;
 }
}
