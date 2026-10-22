/* Original ESP32 amplitude experiment. No arbitrary-IQ or QAM claim. */
#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>
#include <stdarg.h>
#include "protocol.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "driver/uart.h"
#include "esp_chip_info.h"
#include "esp_mac.h"
#include "esp_phy_cert_test.h"
#include "esp_phy_init.h"
#include "esp_timer.h"
#include "esp_private/periph_ctrl.h"
#include "soc/periph_defs.h"
#include "soc/dport_access.h"
#include "nvs_flash.h"
#define TONE1 0x3ff460b8u
#define TONE2 0x3ff460bcu
#define EXT 0x3ff450a8u
static QueueHandle_t jobs;
static SemaphoreHandle_t reports;
static void emit(const char*fmt,...){
 xSemaphoreTake(reports,portMAX_DELAY);
 va_list args;va_start(args,fmt);vprintf(fmt,args);va_end(args);
 vTaskDelay(pdMS_TO_TICKS(2));xSemaphoreGive(reports);
}
static volatile bool busy,cancel,guard_active,registers_accessible,guard_trip;
static volatile int64_t deadline,next_start;
static uint32_t job_id;
static bool invariants(uint32_t a,uint32_t b,uint32_t e,unsigned code){
 return DPORT_REG_READ(TONE1)==oiq_atten_word(a,code)&&DPORT_REG_READ(TONE2)==b&&DPORT_REG_READ(EXT)==e;
}
static portMUX_TYPE mux=portMUX_INITIALIZER_UNLOCKED;
typedef struct {uint32_t a,b,e;int64_t at;bool valid;} tone_record;
static tone_record capture(void){return (tone_record){DPORT_REG_READ(TONE1),DPORT_REG_READ(TONE2),DPORT_REG_READ(EXT),esp_timer_get_time(),true};}
static void record(const char*name,tone_record r,int64_t start){if(r.valid)emit("OIQ,%s,at_us=%"PRIi64",t1=%08"PRIx32",t2=%08"PRIx32",ext=%08"PRIx32"\n",name,r.at-start,r.a,r.b,r.e);}
static void snapshot(const char*name){tone_record r=capture();record(name,r,r.at);}
/* No vendor mutex: repeated clearing while the deadline is overdue. A blocking
 * PHY call may later re-enable hardware, so this remains a software guard. */
static void disable_tones(void){
 portENTER_CRITICAL(&mux);
 DPORT_REG_WRITE(TONE1,DPORT_REG_READ(TONE1)&~OIQ_ENABLE_MASK);
 DPORT_REG_WRITE(TONE2,DPORT_REG_READ(TONE2)&~OIQ_ENABLE_MASK);
 portEXIT_CRITICAL(&mux);
}
static void guard(void*arg){(void)arg;for(;;){
 if(registers_accessible&&guard_active&&(cancel||esp_timer_get_time()>=deadline)){
  guard_trip=true;cancel=true;disable_tones();
 }
 vTaskDelay(pdMS_TO_TICKS(1));
}}
static bool set_atten(unsigned code){
 bool applied=false;
 portENTER_CRITICAL(&mux);
 if(!cancel&&esp_timer_get_time()<deadline){DPORT_REG_WRITE(TONE1,oiq_atten_word(DPORT_REG_READ(TONE1),code));applied=true;}
 portEXIT_CRITICAL(&mux);return applied;
}
static void wait_until(int64_t until){while(!cancel&&esp_timer_get_time()<until)vTaskDelay(pdMS_TO_TICKS(1));}
static void worker(void*arg){(void)arg;oiq_job job;bool initialized=false;
 for(;;){
  if(xQueueReceive(jobs,&job,portMAX_DELAY)!=pdTRUE)continue;
  int64_t start=esp_timer_get_time();deadline=start+(int64_t)job.ms*1000;
  guard_trip=false;guard_active=true;
  uint32_t saved=0;bool have_saved=false,canonical_failed=false;unsigned fields_ok=1,baseline=0,trial=0;
  tone_record base={0},changed={0},returned={0},restored={0},off_state={0};
  tone_record trace[16]={0};unsigned trace_count=0,edges=0,late_us=0;
  int64_t on=0,trial_at=0,return_at=0;
  if(!initialized){
   esp_wifi_power_domain_on();periph_module_enable(PERIPH_WIFI_MODULE);registers_accessible=true;
   esp_phy_enable(PHY_MODEM_WIFI);esp_phy_rftest_config(1);esp_phy_rftest_init();
   esp_phy_tx_contin_en(false);esp_phy_cbw40m_en(false);initialized=true;
  }
  int64_t setup_done=esp_timer_get_time();
  if(!cancel&&esp_timer_get_time()<deadline){
   esp_phy_test_start_stop(3);
   if(!cancel&&esp_timer_get_time()<deadline)esp_phy_wifi_tx_tone(1,8,120);
   on=esp_timer_get_time();
   saved=DPORT_REG_READ(TONE1);uint32_t b=DPORT_REG_READ(TONE2),e=DPORT_REG_READ(EXT);
   base=capture();
   if(!cancel&&on<deadline&&(saved&(1u<<29))&&((saved>>18)&255)==1&&!(b&OIQ_ENABLE_MASK)&&!((saved|b)&0x0c000000u)&&!(saved&1023)&&!(e&3)){
    have_saved=true;baseline=oiq_atten_code(saved);trial=job.control?baseline:job.code;
    /* Setup is charged against the original deadline. Three plateaus use the
     * remaining register window; timestamps report actual scheduling. */
    int64_t window=deadline-on;
    if(job.period_us){
     int64_t next=esp_timer_get_time()+job.period_us;
     while(!cancel&&esp_timer_get_time()<deadline){
      int64_t now=esp_timer_get_time();if(now<next)continue;
      unsigned code=(edges&1u)?baseline:trial;
      if(!set_atten(code))break;
      tone_record edge=capture();
      if(!cancel&&!invariants(saved,b,e,code)){fields_ok=0;cancel=true;break;}
      if(trace_count<16)trace[trace_count++]=edge;
      if((uint64_t)(now-next)>late_us)late_us=(unsigned)(now-next);
      edges++;next=now+job.period_us;
      /* Permit UART STOP/main and the guard to run. The resulting gaps are
       * part of the measured actuator, not a claimed uniform sample clock. */
      if(!(edges%32u))vTaskDelay(pdMS_TO_TICKS(1));
     }
    }else{
    wait_until(on+window/3);
    if(set_atten(trial)){trial_at=esp_timer_get_time();changed=capture();if(!invariants(saved,b,e,trial)){fields_ok=0;cancel=true;}}
    wait_until(on+2*window/3);
    if(set_atten(baseline)){return_at=esp_timer_get_time();returned=capture();if(!invariants(saved,b,e,baseline)){fields_ok=0;cancel=true;}}
    wait_until(deadline);
    }
   }else canonical_failed=true;
  }
  /* Clear enable first, before any potentially blocking vendor stop routine.
   * Restoration modifies attenuation only and cannot re-enable a stopped tone. */
  cancel=true;if(registers_accessible)disable_tones();
  int64_t disabled=esp_timer_get_time();
  if(have_saved){
   portENTER_CRITICAL(&mux);
   uint32_t now=DPORT_REG_READ(TONE1);
   DPORT_REG_WRITE(TONE1,(now&~OIQ_ATTEN_MASK)|(saved&OIQ_ATTEN_MASK));
   portEXIT_CRITICAL(&mux);restored=capture();
  }
  esp_phy_wifi_tx_tone(0,8,120);esp_phy_test_start_stop(0);
  if(registers_accessible)disable_tones();
  guard_active=false;
  next_start=esp_timer_get_time()+2000000;
  if(registers_accessible)off_state=capture();
  /* All formatting/UART transfers happen after tone disable and API stop. */
  if(canonical_failed)emit("OIQ,ERR,canonical_or_deadline\n");
  if(have_saved)emit("OIQ,CODES,job=%"PRIu32",baseline=%u,trial=%u,control=%u\n",job_id,baseline,trial,job.control);
  record("BASELINE",base,start);record("TRIAL",changed,start);record("RETURN",returned,start);record("RESTORED",restored,start);
  if(job.period_us){
   emit("OIQ,TRAIN,job=%"PRIu32",period_us=%u,edges=%u,max_late_us=%u,trace=%u,uniform_clock=0\n",job_id,job.period_us,edges,late_us,trace_count);
   for(unsigned k=0;k<trace_count;k++)record("TRACE",trace[k],start);
  }
  emit("OIQ,TIMING,setup_us=%"PRIi64",register_window_us=%"PRIi64",guard_trip=%u\n",(on?on:setup_done)-start,on?disabled-on:0,guard_trip);
  emit("OIQ,EDGES,trial_us=%"PRIi64",return_us=%"PRIi64",software_bound=1\n",trial_at?trial_at-start:0,return_at?return_at-start:0);
  record("OFF",off_state,start);
  emit("OIQ,DONE,job=%"PRIu32",gain_restored=%u,fields_ok=%u,rf_off=%u\n",job_id,have_saved&&((DPORT_REG_READ(TONE1)^saved)&OIQ_ATTEN_MASK)==0,fields_ok,!(DPORT_REG_READ(TONE1)&OIQ_ENABLE_MASK)&&!(DPORT_REG_READ(TONE2)&OIQ_ENABLE_MASK));
  busy=false;
 }
}
static void command(char*s){
 if(!strcmp(s,"INFO")){
  esp_chip_info_t info;uint8_t mac[6];esp_chip_info(&info);ESP_ERROR_CHECK(esp_read_mac(mac,ESP_MAC_WIFI_STA));
  emit("OIQ,INFO,v=2,chip=esp32,uart=2000000,iq=unverified,busy=%u,amp_train=1,max_code=127\n",busy);
  emit("OIQ,IDENT,rev=%d,mac=%02x:%02x:%02x:%02x:%02x:%02x\n",info.revision,mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
 }
 else if(!strcmp(s,"STATE")){if(registers_accessible)snapshot("STATE");else emit("OIQ,STATE,rf_initialized=0\n");}
 else if(!strcmp(s,"STOP")){cancel=true;if(registers_accessible)disable_tones();emit("OIQ,STOP,requested=1\n");}
 else{oiq_job job;if(!oiq_parse(s,&job)){emit("OIQ,ERR,command_bounds\n");return;}
  if(busy||esp_timer_get_time()<next_start){emit("OIQ,ERR,busy_or_cooldown\n");return;}
  busy=true;cancel=false;job_id++;
  emit("OIQ,START,job=%"PRIu32",limit_ms=%u,tx=explicit\n",job_id,job.ms);
  if(xQueueSend(jobs,&job,0)!=pdPASS){busy=false;emit("OIQ,ERR,queue\n");}
 }
}
void app_main(void){
 /* Preserve existing NVS: no automatic erase fallback. */
 ESP_ERROR_CHECK(nvs_flash_init());
 uart_config_t u={.baud_rate=2000000,.data_bits=UART_DATA_8_BITS,.parity=UART_PARITY_DISABLE,.stop_bits=UART_STOP_BITS_1,.flow_ctrl=UART_HW_FLOWCTRL_DISABLE,.source_clk=UART_SCLK_DEFAULT};
 ESP_ERROR_CHECK(uart_param_config(UART_NUM_0,&u));ESP_ERROR_CHECK(uart_set_pin(UART_NUM_0,17,16,UART_PIN_NO_CHANGE,UART_PIN_NO_CHANGE));ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0,1024,0,0,NULL,0));setvbuf(stdout,NULL,_IONBF,0);
 jobs=xQueueCreate(1,sizeof(oiq_job));reports=xSemaphoreCreateMutex();if(!jobs||!reports)abort();
 if(xTaskCreate(worker,"oiq_probe",4096,NULL,5,NULL)!=pdPASS||xTaskCreate(guard,"oiq_guard",3072,NULL,8,NULL)!=pdPASS)abort();
 emit("OIQ,READY,rf_initialized=0,arbitrary_iq=unverified\n");
 char s[96];unsigned n=0;bool overflow=false;
 for(;;){uint8_t c;if(uart_read_bytes(UART_NUM_0,&c,1,pdMS_TO_TICKS(2))!=1)continue;
  if(c=='\r')continue;
  if(c=='\n'){if(overflow)emit("OIQ,ERR,line_length\n");else{s[n]=0;command(s);}n=0;overflow=false;}
  else if(n<sizeof(s)-1)s[n++]=(char)c;else overflow=true;
 }
}
