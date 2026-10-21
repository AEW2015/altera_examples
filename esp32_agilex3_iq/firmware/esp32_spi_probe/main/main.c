// Separate transport qualification image: synthetic CI8 only, no RF transmission.
#include "iq_spi_slave.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
static int8_t capture[32760];
void app_main(void){
 ESP_ERROR_CHECK(iq_spi_init(true));
 for(size_t n=0;n<sizeof(capture);n++)capture[n]=(int8_t)(n*37+11);
 ESP_LOGI("IQ_SPI","synthetic CI8 transport only; mode1, 1056-byte reads, READY J1.7");
 for(uint32_t seq=0;;seq++){
  iq_spi_set_capture_synthetic(true);
  esp_err_t e=iq_spi_publish(capture,sizeof(capture),2,seq,5000);
  ESP_LOGI("IQ_SPI","sequence=%lu result=%s",(unsigned long)seq,esp_err_to_name(e));
  vTaskDelay(pdMS_TO_TICKS(100));
 }
}
