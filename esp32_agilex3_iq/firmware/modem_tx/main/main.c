/* SPDX-License-Identifier: GPL-3.0-or-later
 * Buffered IQ transmitter control; built against pinned esp32-iq-tx component.
 * No RF initialization at boot. INIT explicitly prepares RF (brief CW).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <inttypes.h>
#include "freertos/FreeRTOS.h"
#include "driver/uart.h"
#include "driver/usb_serial_jtag.h"
#include "esp_timer.h"
#include "iq_tx.h"

static bool initialized, loaded;
static uint32_t loaded_crc;
static int read_transport(void *buf, size_t len, unsigned timeout_ms) {
#ifdef CONFIG_MODEM_TX_UART
    return uart_read_bytes(UART_NUM_1, buf, len, pdMS_TO_TICKS(timeout_ms));
#else
    return usb_serial_jtag_read_bytes(buf, len, pdMS_TO_TICKS(timeout_ms));
#endif
}
static void reply(const char *fmt, ...) {
    char line[320];va_list ap;va_start(ap,fmt);int n=vsnprintf(line,sizeof(line),fmt,ap);va_end(ap);
    if(n<0)return;
    if(n>=(int)sizeof(line))n=sizeof(line)-1;
#ifdef CONFIG_MODEM_TX_UART
    uart_write_bytes(UART_NUM_1,line,n);
#else
    usb_serial_jtag_write_bytes(line,n,pdMS_TO_TICKS(1000));
#endif
}
static uint32_t crc32(const uint8_t *p,size_t n) {
    uint32_t c=~0u;for(size_t k=0;k<n;k++){c^=p[k];for(int b=0;b<8;b++)c=(c>>1)^(0xedb88320u&-(c&1));}return ~c;
}
static void handle(char *line) {
    unsigned channel,backoff,rate,count;uint32_t crc;char extra;
    if(!strcmp(line,"INFO")) {
        const iq_tx_caps_t *c=iq_tx_capabilities();iq_tx_status_t s=iq_tx_status();
        reply("MODEM_TX chip=%s initialized=%u running=%u loaded=%u samples=%u rate=%"PRIu32" max=%u alignment=%u crc=%08"PRIx32"\n",c->chip,initialized,s.running,loaded,(unsigned)s.samples,c->sample_rate_hz,(unsigned)c->max_samples,(unsigned)c->loop_alignment_samples,loaded_crc);
    } else if(sscanf(line,"INIT %u %u %c",&channel,&backoff,&extra)==2) {
        if(initialized){reply("ERROR already_initialized_reset_to_retune\n");return;}
        iq_tx_config_t cfg={.channel=channel,.rf_backoff_qdb=backoff};esp_err_t e=iq_tx_init(&cfg);
        initialized=e==ESP_OK;reply(e==ESP_OK?"OK INIT\n":"ERROR INIT %d\n",e);
    } else if(sscanf(line,"RATE %u %c",&rate,&extra)==1) {
        esp_err_t e=iq_tx_set_sample_rate(rate);reply(e==ESP_OK?"OK RATE\n":"ERROR RATE %d\n",e);
    } else if(sscanf(line,"LOAD %u %"SCNx32" %c",&count,&crc,&extra)==2) {
        const iq_tx_caps_t *caps=iq_tx_capabilities();
        if(!initialized||iq_tx_status().running||!count||count>caps->max_samples||count%caps->loop_alignment_samples){reply("ERROR invalid_load_state_or_length\n");return;}
        uint32_t *words=malloc((size_t)count*4);if(!words){reply("ERROR memory\n");return;}
        loaded=false;loaded_crc=0;reply("READY %u\n",count*4);
        size_t got=0,total=(size_t)count*4;int64_t deadline=esp_timer_get_time()+10000000;
        while(got<total && esp_timer_get_time()<deadline){int n=read_transport((uint8_t*)words+got,total-got,100);if(n>0)got+=(size_t)n;}
        esp_err_t e=ESP_FAIL;
        if(got==total && crc32((uint8_t*)words,total)==crc)e=iq_tx_load(words,count);
        free(words);loaded=e==ESP_OK;if(loaded)loaded_crc=crc;
        reply(loaded?"OK LOAD %08"PRIx32"\n":"ERROR LOAD %08"PRIx32"\n",crc);
    } else if(!strcmp(line,"START")) {
        if(!loaded){reply("ERROR no_verified_load\n");return;}
        esp_err_t e=iq_tx_start_loop();reply(e==ESP_OK?"OK START\n":"ERROR START %d\n",e);
    } else if(!strcmp(line,"STOP")) {
        esp_err_t e=initialized?iq_tx_stop():ESP_OK;reply(e==ESP_OK?"OK STOP\n":"ERROR STOP %d\n",e);
    } else reply("ERROR command\n");
}
void app_main(void) {
#ifdef CONFIG_MODEM_TX_UART
    uart_config_t cfg={.baud_rate=2000000,.data_bits=UART_DATA_8_BITS,.parity=UART_PARITY_DISABLE,.stop_bits=UART_STOP_BITS_1,.flow_ctrl=UART_HW_FLOWCTRL_DISABLE,.source_clk=UART_SCLK_DEFAULT};
    ESP_ERROR_CHECK(uart_param_config(UART_NUM_1,&cfg));
    ESP_ERROR_CHECK(uart_set_pin(UART_NUM_1,CONFIG_MODEM_TX_UART_TX,CONFIG_MODEM_TX_UART_RX,UART_PIN_NO_CHANGE,UART_PIN_NO_CHANGE));
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_1,4096,0,0,NULL,0));
#else
    usb_serial_jtag_driver_config_t cfg={.tx_buffer_size=4096,.rx_buffer_size=4096};
    ESP_ERROR_CHECK(usb_serial_jtag_driver_install(&cfg));
#endif
    char line[128];size_t used=0;bool discard=false;
    reply("MODEM_TX READY RF_UNINITIALIZED\n");
    for(;;){char c;if(read_transport(&c,1,100)<=0)continue;
        if(c=='\n'){if(!discard){line[used]=0;handle(line);}else reply("ERROR line_too_long\n");used=0;discard=false;}
        else if(c!='\r'){if(used+1<sizeof(line)&&!discard)line[used++]=c;else discard=true;}
    }
}
