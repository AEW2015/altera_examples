/* Original ESP32 native 802.11g TX: bounded explicit jobs, never boot TX. */
#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>
#include "protocol.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "driver/uart.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_timer.h"
#include "esp_mac.h"
#include "nvs_flash.h"

static unsigned channel=8,power=8,count=4,gap=2;
static uint32_t run=1,seed=1,job;
static uint8_t mac[6];
static volatile bool busy,armed,radio_on,cancel;
static volatile uint32_t accepted,rejected,completed,failed,rate54,rate_other;
static volatile int64_t deadline,arm_until,next_start;
static bool initialized;
static volatile int stop_error;
static SemaphoreHandle_t wifi_lock;
static void off_locked(void){
 if(radio_on){esp_err_t e=esp_wifi_stop();stop_error=e;
  if(e==ESP_OK||e==ESP_ERR_WIFI_NOT_STARTED){radio_on=false;stop_error=0;}
 }armed=false;
}
static void off(void){xSemaphoreTake(wifi_lock,portMAX_DELAY);off_locked();xSemaphoreGive(wifi_lock);}
static void done(const esp_80211_tx_info_t *p){
 if(!busy||p->ifidx!=WIFI_IF_STA)return;
 if(p->tx_status==WIFI_SEND_SUCCESS)completed++;else failed++;
 if(p->rate==WIFI_PHY_RATE_54M)rate54++;else rate_other++;
}
static esp_err_t prepare_locked(void){
 esp_err_t e;
 if(!initialized){
  if((e=esp_event_loop_create_default())!=ESP_OK&&e!=ESP_ERR_INVALID_STATE)return e;
  wifi_init_config_t c=WIFI_INIT_CONFIG_DEFAULT();
  if((e=esp_wifi_init(&c))!=ESP_OK)return e;
  initialized=true;
 }
 if((e=esp_wifi_set_storage(WIFI_STORAGE_RAM))!=ESP_OK)return e;
 if((e=esp_wifi_set_mode(WIFI_MODE_STA))!=ESP_OK)return e;
 if((e=esp_wifi_register_80211_tx_cb(done))!=ESP_OK)return e;
 if((e=esp_wifi_set_protocol(WIFI_IF_STA,(WIFI_PROTOCOL_11B|WIFI_PROTOCOL_11G)))!=ESP_OK)return e;
 if((e=esp_wifi_config_80211_tx_rate(WIFI_IF_STA,WIFI_PHY_RATE_54M))!=ESP_OK)return e;
 if((e=esp_wifi_start())!=ESP_OK)return e;
 radio_on=true;
 if((e=esp_wifi_set_channel(channel,WIFI_SECOND_CHAN_NONE))!=ESP_OK)return e;
 if((e=esp_wifi_set_max_tx_power((int8_t)power))!=ESP_OK)return e;
 cancel=false;arm_until=esp_timer_get_time()+5000000;armed=true;
 return ESP_OK;
}
static void status(const char *verb){
 printf("WIFI64_TX,%s,job=%"PRIu32",busy=%u,armed=%u,rf=%u,stop_err=%d\n",verb,job,busy,armed,radio_on,stop_error);
 vTaskDelay(pdMS_TO_TICKS(2));
 printf("WIFI64_TX,SUBMITTED,accepted=%"PRIu32",rejected=%"PRIu32"\n",accepted,rejected);
 vTaskDelay(pdMS_TO_TICKS(2));
 printf("WIFI64_TX,COUNTERS,done=%"PRIu32",failed=%"PRIu32",rate54=%"PRIu32",other=%"PRIu32"\n",completed,failed,rate54,rate_other);
}
static void guard(void *arg){(void)arg;for(;;){
 xSemaphoreTake(wifi_lock,portMAX_DELAY);
 int64_t now=esp_timer_get_time();
 if(radio_on&&((busy&&now>=deadline)||(!busy&&armed&&now>=arm_until)||(!busy&&!armed))){cancel=true;off_locked();}
 xSemaphoreGive(wifi_lock);
 vTaskDelay(pdMS_TO_TICKS(1));
}}
static void transmit(void *arg){(void)arg;
 /* The UART START acknowledgement must precede every job result. */
 ulTaskNotifyTake(pdTRUE,portMAX_DELAY);
 uint8_t frame[W64_FRAME];
 int64_t due=esp_timer_get_time();
 for(unsigned k=0;k<count;k++){
  while(!cancel&&esp_timer_get_time()<due)vTaskDelay(pdMS_TO_TICKS(1));
  xSemaphoreTake(wifi_lock,portMAX_DELAY);
  if(cancel||!radio_on||esp_timer_get_time()>=deadline){xSemaphoreGive(wifi_lock);break;}
  w64_frame(frame,mac,run,k,seed);
  esp_err_t e=esp_wifi_80211_tx(WIFI_IF_STA,frame,sizeof(frame),false);
  if(e==ESP_OK)accepted++;else rejected++;
  due=esp_timer_get_time()+(int64_t)gap*1000;
  xSemaphoreGive(wifi_lock);
 }
 /* Permit callbacks to drain within the independent 100-ms RF deadline. */
 while(!cancel&&completed+failed<accepted&&esp_timer_get_time()<deadline)vTaskDelay(pdMS_TO_TICKS(1));
 off();next_start=esp_timer_get_time()+2000000;busy=false;
 status(cancel?"CANCELLED":"DONE");vTaskDelete(NULL);
}
static void command(char *line){
 unsigned ch,p,c,g;uint32_t r,s;char extra;
 if(!strcmp(line,"INFO")){
  printf("WIFI64_TX,INFO,version=1,chip=esp32,phy=native11g,rate=54,uart=2000000\n");
  vTaskDelay(pdMS_TO_TICKS(2));
  printf("WIFI64_TX,IDENT,mac=%02x:%02x:%02x:%02x:%02x:%02x,frame_bytes=88\n",mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);vTaskDelay(pdMS_TO_TICKS(2));status("STATUS");
 }else if(!strcmp(line,"STATUS")){status("STATUS");
 }else if(!strcmp(line,"CONFIG?")){
  printf("WIFI64_TX,CONFIG,ch=%u,power_qdbm=%u,count=%u,gap_ms=%u,run=%"PRIu32",seed=%"PRIu32"\n",channel,power,count,gap,run,seed);
 }else if(!strncmp(line,"CONFIG ",7)){
  if(busy||armed){puts("WIFI64_TX,ERR,busy_or_armed");return;}
  if(sscanf(line+7,"%u %u %u %u %"SCNu32" %"SCNu32" %c",&ch,&p,&c,&g,&r,&s,&extra)!=6||!w64_valid_config(ch,p,c,g)){puts("WIFI64_TX,ERR,config_bounds");return;}
  channel=ch;power=p;count=c;gap=g;run=r;seed=s;puts("WIFI64_TX,CONFIG,ok=1");
 }else if(!strcmp(line,"ARM")){
  if(busy||armed||esp_timer_get_time()<next_start){puts("WIFI64_TX,ERR,busy_or_cooldown");return;}
  xSemaphoreTake(wifi_lock,portMAX_DELAY);
  esp_err_t e=prepare_locked();
  xSemaphoreGive(wifi_lock);if(e!=ESP_OK){off();printf("WIFI64_TX,ERR,prepare=%d\n",(int)e);return;}
  uint8_t actual_channel;wifi_second_chan_t second;int8_t actual_power;
  if(esp_wifi_get_channel(&actual_channel,&second)!=ESP_OK||esp_wifi_get_max_tx_power(&actual_power)!=ESP_OK){off();puts("WIFI64_TX,ERR,readback");return;}
  if(actual_channel!=channel){off();puts("WIFI64_TX,ERR,channel_mismatch");return;}
  printf("WIFI64_TX,ARM,ok=1,ch=%u,power_qdbm=%d,expires_ms=5000\n",actual_channel,actual_power);
 }else if(!strcmp(line,"START")){
  if(!armed||busy||!radio_on||esp_timer_get_time()>=arm_until||esp_timer_get_time()<next_start){puts("WIFI64_TX,ERR,not_armed");return;}
  accepted=rejected=completed=failed=rate54=rate_other=0;job++;cancel=false;deadline=esp_timer_get_time()+100000;busy=true;armed=false;
  TaskHandle_t worker=NULL;
  if(xTaskCreate(transmit,"wifi64_job",4096,NULL,5,&worker)!=pdPASS){busy=false;off();next_start=esp_timer_get_time()+2000000;puts("WIFI64_TX,ERR,task");return;}
  printf("WIFI64_TX,START,job=%"PRIu32",deadline_ms=100\n",job);
  xTaskNotifyGive(worker);
 }else if(!strcmp(line,"STOP")){cancel=true;off();next_start=esp_timer_get_time()+2000000;status("STOP");
 }else puts("WIFI64_TX,ERR,command");
}
void app_main(void){
 esp_err_t e=nvs_flash_init();if(e==ESP_ERR_NVS_NO_FREE_PAGES||e==ESP_ERR_NVS_NEW_VERSION_FOUND){ESP_ERROR_CHECK(nvs_flash_erase());e=nvs_flash_init();}ESP_ERROR_CHECK(e);
 ESP_ERROR_CHECK(esp_read_mac(mac,ESP_MAC_WIFI_STA));
 uart_config_t u={.baud_rate=2000000,.data_bits=UART_DATA_8_BITS,.parity=UART_PARITY_DISABLE,.stop_bits=UART_STOP_BITS_1,.flow_ctrl=UART_HW_FLOWCTRL_DISABLE,.source_clk=UART_SCLK_DEFAULT};
 ESP_ERROR_CHECK(uart_param_config(UART_NUM_0,&u));ESP_ERROR_CHECK(uart_set_pin(UART_NUM_0,17,16,UART_PIN_NO_CHANGE,UART_PIN_NO_CHANGE));ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0,1024,0,0,NULL,0));
 setvbuf(stdout,NULL,_IONBF,0);
 wifi_lock=xSemaphoreCreateMutex();if(!wifi_lock)abort();
 if(xTaskCreate(guard,"rf_deadline",3072,NULL,8,NULL)!=pdPASS)abort();
 puts("WIFI64_TX,READY,rf=0,version=1");
 char line[96];unsigned n=0;bool overflow=false;
 for(;;){uint8_t c;if(uart_read_bytes(UART_NUM_0,&c,1,pdMS_TO_TICKS(20))!=1)continue;
  if(c=='\r')continue;
  if(c=='\n'){if(overflow)puts("WIFI64_TX,ERR,line_too_long");else{line[n]=0;command(line);}n=0;overflow=false;}
  else if(n<sizeof(line)-1)line[n++]=(char)c;else overflow=true;
 }
}
