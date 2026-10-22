/* One image; reboot isolates native Wi-Fi and certification PHY state. */
#include <stdio.h>
#include "txlab_mode.h"
#include "mode_protocol.h"
#include "esp_attr.h"
#include "esp_system.h"
#include "driver/uart.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
static RTC_NOINIT_ATTR struct {unsigned magic,mode,inverse;} selection;
static unsigned current;
static const char *names[]={"AMP","NATIVE","PHASE"};
void txlab_amp_main(void); void txlab_native_main(void); void txlab_phase_main(void);
bool txlab_command(const char *line,bool quiet) {
 if(!strcmp(line,"MODE?") || !strcmp(line,"LABCAPS")) {
  printf("TXLAB,MODE,mode=%s,quiet=%u,modes=AMP_NATIVE_PHASE,arbitrary_iq=unverified\n",names[current],quiet);return true;
 }
 if(strncmp(line,"MODE",4)) return false;
 int mode=txlab_parse_mode(line);
 if(mode<0){puts("TXLAB,ERR,mode_syntax");return true;}
 if(!quiet){puts("TXLAB,ERR,stop_and_wait_idle");return true;}
 printf("TXLAB,SWITCH,mode=%s,restart=1,rf_on_boot=0\n",names[mode]);
 fflush(stdout);uart_wait_tx_done(UART_NUM_0,pdMS_TO_TICKS(100));
 selection.magic=0x544c4142u;selection.mode=(unsigned)mode;selection.inverse=~(unsigned)mode;
 esp_restart();return true;
}
void app_main(void) {
 current=txlab_selection(esp_reset_reason()==ESP_RST_SW,selection.magic,selection.mode,selection.inverse);
 /* Consume selection: a later unrelated software restart defaults to AMP. */
 selection.magic=0;
 vTaskDelay(pdMS_TO_TICKS(2100));
 if(current==1)txlab_native_main();else if(current==2)txlab_phase_main();else txlab_amp_main();
}
