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
#include "esp_cpu.h"
#include "esp_attr.h"
#include "esp_private/esp_clk.h"
#include "esp_private/periph_ctrl.h"
#include "soc/periph_defs.h"
#include "soc/dport_access.h"
#include "nvs_flash.h"
#include "probe_protocol.h"
static QueueHandle_t jobs;
static volatile bool busy, cancel;
static bool initialized;
static uint32_t job_id;
/* Original-chip ROM function and ABI reconstructed from matching ROM ELF and
 * SDK DWARF. These are two scalar tone generators, not Cartesian IQ inputs. */
extern void rom_start_tx_tone_step(bool, int16_t, uint8_t, bool, int16_t, uint8_t);
#define TONE1_REG 0x3ff460b8u
#define TONE2_REG 0x3ff460bcu
#define TONE_EXT_REG 0x3ff450a8u
static void tone_state(const char *prefix) {
    uint32_t a=DPORT_REG_READ(TONE1_REG),b=DPORT_REG_READ(TONE2_REG);
    printf("%s,tone1=%08"PRIx32",tone2=%08"PRIx32",ext=%08"PRIx32",mode12=%u\n",prefix,a,b,DPORT_REG_READ(TONE_EXT_REG),(unsigned)((a>>29)&1));
}
typedef struct { uint32_t job,cpu,symbols,flips,min,max,late,missed,frames; } phase_stats_t;
static volatile phase_stats_t phase_stats;
static portMUX_TYPE pulse_mux=portMUX_INITIALIZER_UNLOCKED;
static void phase_report(void) {
    printf("PHASESTAT,job=%"PRIu32",cpu=%"PRIu32",symbols=%"PRIu32",flips=%"PRIu32",min=%"PRIu32",max=%"PRIu32",late=%"PRIu32",missed=%"PRIu32",frames=%"PRIu32"\n",
           phase_stats.job,phase_stats.cpu,phase_stats.symbols,phase_stats.flips,
           phase_stats.min,phase_stats.max,phase_stats.late,phase_stats.missed,phase_stats.frames);
}
static bool wait_cycle(uint32_t target) {
    while ((int32_t)(esp_cpu_get_cycle_count()-target)<0) if (cancel) return false;
    return !cancel;
}
/* A frequency pulse advances the measured original-chip phase accumulator.
 * v4 extends the qualified slow step1 experiment with explicitly experimental
 * step3 fast pulses; RF qualification is still required at each new setting.
 * The main tone control word, gain and mode are never changed here. */
static uint32_t IRAM_ATTR phase_pulse(uint32_t original_ext,uint32_t step,uint32_t cycles) {
    /* Bound interrupt stretching to one pulse. STOP is checked between pulses;
     * a command never masks interrupts for the entire RF job. */
    portENTER_CRITICAL(&pulse_mux);
    DPORT_REG_WRITE(TONE_EXT_REG,(original_ext&~3u)|step);
    uint32_t begin=esp_cpu_get_cycle_count();
    while ((uint32_t)(esp_cpu_get_cycle_count()-begin)<cycles) { }
    DPORT_REG_WRITE(TONE_EXT_REG,original_ext);
    uint32_t width=esp_cpu_get_cycle_count()-begin;
    portEXIT_CRITICAL(&pulse_mux);
    return width;
}
static void phase_run(const probe_job_t *job,int64_t started,uint32_t original_ext) {
    uint32_t period=(uint64_t)esp_clk_cpu_freq()*job->symbol_us/1000000u;
    uint32_t next=esp_cpu_get_cycle_count();unsigned current=0,index=0;
    bool frame=(job->nco_step&0x100)!=0;
    unsigned step=job->nco_step&3;if (!step) step=1;
    uint8_t bits[64];if (frame) probe_frame_bits(job->pattern,bits);
    while (!cancel && esp_timer_get_time()-started<(int64_t)job->duration_ms*1000) {
        if (!wait_cycle(next)) break;
        uint32_t at=esp_cpu_get_cycle_count();
        if ((int32_t)(at-next)>(int32_t)(period/50)) phase_stats.late++;
        unsigned bit=frame?bits[index]:(job->pattern>>(7-index))&1;
        index=(index+1)&(frame?63:7);
        if(frame && index==0) phase_stats.frames++;
        if (bit!=current && job->pulse_cycles) {
            uint32_t width=phase_pulse(original_ext,step,job->pulse_cycles);
            if (!phase_stats.flips || width<phase_stats.min) phase_stats.min=width;
            if (width>phase_stats.max) phase_stats.max=width;
            phase_stats.flips++;
        }
        current=bit;phase_stats.symbols++;next+=period;
        /* Never compress missed slots. A damaged frame restarts at its marker. */
        if ((int32_t)(esp_cpu_get_cycle_count()-next)>0) {
            phase_stats.missed++;next=esp_cpu_get_cycle_count()+period;if(frame) index=0;
        }
    }
    DPORT_REG_WRITE(TONE_EXT_REG,original_ext);
}
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
        uint32_t saved1=0,saved2=0,saved_ext=0; bool nco_changed=false;
        if (!cancel) {
            esp_phy_test_start_stop(3);
            esp_phy_wifi_tx_tone(1,job.channel,job.backoff_qdb);
            if (job.phase) {
                uint32_t a=DPORT_REG_READ(TONE1_REG),b=DPORT_REG_READ(TONE2_REG),e=DPORT_REG_READ(TONE_EXT_REG);
                if (!((a>>29)&1) || ((a>>18)&255)!=1 || ((b>>18)&255)!=0 ||
                    ((a|b)&0x0c000000u) || (a&1023) || (e&3)) {
                    esp_phy_wifi_tx_tone(0,job.channel,job.backoff_qdb);esp_phy_test_start_stop(0);
                    puts("ERR phase_requires_canonical_hires_tone1_step0");busy=false;continue;
                }
                saved_ext=e;
                phase_stats=(phase_stats_t){.job=id,.cpu=esp_clk_cpu_freq()};
                if (job.nco_step&0x100)
                    printf("FRAME_CFG,job=%"PRIu32",cpu=%"PRIu32",period_us=%"PRIu32",pulse_cycles=%"PRIu32",payload=%"PRIu32",bits=64,step=3\n",
                           id,phase_stats.cpu,job.symbol_us,job.pulse_cycles,job.pattern);
                else
                    printf("PHASE_CFG,job=%"PRIu32",cpu=%"PRIu32",period_us=%"PRIu32",pulse_cycles=%"PRIu32",pattern=%"PRIu32",step=%u,frame=0\n",
                           id,phase_stats.cpu,job.symbol_us,job.pulse_cycles,job.pattern,
                           (unsigned)((job.nco_step&3)?(job.nco_step&3):1));
            }
            if (job.nco) {
                uint32_t a=DPORT_REG_READ(TONE1_REG),b=DPORT_REG_READ(TONE2_REG);
                unsigned e1=(a>>18)&255,e2=(b>>18)&255;
                tone_state("NCO_BEFORE");
                if ((!e1 && !e2) || e1>1 || e2>1 || ((a|b)&0x0c000000u)) {
                    esp_phy_wifi_tx_tone(0,job.channel,job.backoff_qdb);
                    esp_phy_test_start_stop(0);
                    puts("ERR noncanonical_tone_state");busy=false;continue;
                }
                /* Keep vendor enables, calibrated attenuation and bit29 mode.
                 * Nonnegative raw codes avoid ROM signed-step control spill. */
                saved1=a;saved2=b;saved_ext=DPORT_REG_READ(TONE_EXT_REG);nco_changed=true;
                rom_start_tx_tone_step(e1,(int16_t)job.nco_step,(uint8_t)(0u-((a>>10)&255)),
                                      e2,(int16_t)job.nco_step,(uint8_t)(0u-((b>>10)&255)));
                tone_state("NCO_STATE");
            }
            started=esp_timer_get_time();
            printf("TX_ON,id=%"PRIu32",channel=%"PRIu32",backoff_qdb=%"PRIu32",limit_ms=%"PRIu32"\n",id,job.channel,job.backoff_qdb,job.duration_ms);
            if (job.phase) phase_run(&job,started,saved_ext);
            else while (!cancel && esp_timer_get_time()-started<(int64_t)job.duration_ms*1000)
                    vTaskDelay(pdMS_TO_TICKS(5));
        }
        if (nco_changed) {
            bool hires=(saved1>>29)&1;
            unsigned f1=hires?((saved1&1023)<<2)|(saved_ext&3):(saved1&1023);
            unsigned f2=hires?((saved2&1023)<<2)|((saved_ext>>2)&3):(saved2&1023);
            rom_start_tx_tone_step((saved1>>18)&1,f1,(uint8_t)(0u-((saved1>>10)&255)),
                                  (saved2>>18)&1,f2,(uint8_t)(0u-((saved2>>10)&255)));
            tone_state("NCO_RESTORED");
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
        printf("TX_PROBE,v=4,rev=%d,mac=%02x:%02x:%02x:%02x:%02x:%02x,tx=%d,rx=%d,baud=2000000,busy=%d,iq=unverified\n",chip.revision,mac[0],mac[1],mac[2],mac[3],mac[4],mac[5],CONFIG_ESP_SDR_UART_TX_PIN,CONFIG_ESP_SDR_UART_RX_PIN,busy);
    } else if (!strcmp(line,"PHASECAP")) {
        uint32_t cpu=esp_clk_cpu_freq();
        printf("PHASECAP,cpu=%"PRIu32",half_cycles=%"PRIu32",step_nom_mHz=39062500,fast_half_cycles=%"PRIu32",fast_step=3\n",cpu,cpu/78125u,cpu/234375u);
    } else if (!strncmp(line,"FRAMEBITS ",10)) {
        probe_job_t parsed;char text[96];
        snprintf(text,sizeof(text),"FRAME 8 50 96 %s 8 0",line+10);
        if (!probe_parse_tone(text,&parsed)) {puts("ERR invalid_payload8");return;}
        uint8_t bits[64];probe_frame_bits(parsed.pattern,bits);
        printf("FRAMEBITS,payload=%"PRIu32",bits=",parsed.pattern);
        for(unsigned i=0;i<64;i++) putchar('0'+bits[i]);
        putchar('\n');
    } else if (!strcmp(line,"PHASESTAT")) {
        phase_report();
    } else if (!strcmp(line,"STATE")) {
        if (initialized) tone_state("TONE_STATE");else puts("ERR rf_not_initialized");
    } else if (!strcmp(line,"STOP")) {
        cancel=true;
        printf("STOP_REQUESTED,busy=%d\n",busy);
    } else {
        probe_job_t job;
        if (!probe_parse_tone(line,&job)) { puts("ERR use_INFO_STATE_STOP_TONE_or_NCO_bounded_job"); return; }
        if (job.phase && job.pulse_cycles>(uint64_t)esp_clk_cpu_freq()*job.symbol_us/(job.nco_step?1250000u:2000000u)) {
            puts("ERR phase_pulse_exceeds_slot_guard");return;
        }
        if (busy) { puts("ERR busy"); return; }
        cancel=false; busy=true;
        if (xQueueSend(jobs,&job,0)!=pdTRUE) { busy=false; puts("ERR queue"); return; }
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
    /* Use the configured scheduler affinity: this image is UNICORE and core 1
     * does not exist. xTaskCreate also supports a future dual-core build. */
    configASSERT(xTaskCreate(worker,"bounded_tx",4096,NULL,5,NULL)==pdPASS);
    /* UART STOP can preempt the bounded phase worker even during busy waits. */
    vTaskPrioritySet(NULL,6);
    puts("TX_PROBE_READY,rf=off,commands=INFO_STOP_TONE_NCO_PHASE_FASTPHASE_FRAME_FRAMEBITS_STATE,iq_playback=unverified");
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
