#include "iq_spi_slave.h"
#include <string.h>
#include "driver/spi_slave.h"
#include "driver/gpio.h"
#include "esp_attr.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#define READY GPIO_NUM_2
static uint8_t *packet,*commands;
static spi_slave_transaction_t transaction;
static int pending;
static bool artificial,requested_artificial;
bool iq_spi_requested_synthetic(void){return requested_artificial;}
void iq_spi_set_capture_synthetic(bool synthetic){artificial=synthetic;}
static void apply_command(void){
 int mode=iq_spi_packet_command(commands,IQ_SPI_PACKET);
 if(mode==1)requested_artificial=true;
 else if(mode==2)requested_artificial=false;
}
static void IRAM_ATTR armed(spi_slave_transaction_t *t){(void)t;gpio_set_level(READY,1);}
static void IRAM_ATTR completed(spi_slave_transaction_t *t){(void)t;gpio_set_level(READY,0);}
esp_err_t iq_spi_init(bool synthetic){
 artificial=synthetic;requested_artificial=synthetic;
 gpio_config_t ready={.pin_bit_mask=1ULL<<READY,.mode=GPIO_MODE_OUTPUT};
 esp_err_t err=gpio_config(&ready);if(err!=ESP_OK)return err;gpio_set_level(READY,0);
 packet=heap_caps_malloc(IQ_SPI_PACKET,MALLOC_CAP_DMA|MALLOC_CAP_INTERNAL);
 commands=heap_caps_malloc(IQ_SPI_PACKET,MALLOC_CAP_DMA|MALLOC_CAP_INTERNAL);
 if(!packet || !commands){heap_caps_free(packet);heap_caps_free(commands);packet=NULL;return ESP_ERR_NO_MEM;}
 spi_bus_config_t bus={.mosi_io_num=23,.miso_io_num=19,.sclk_io_num=18,
  .quadwp_io_num=-1,.quadhd_io_num=-1,.max_transfer_sz=IQ_SPI_PACKET};
 // Original ESP32 DMA timing: mode 1, MSB first, initial qualification at 5 MHz.
 spi_slave_interface_config_t slave={.spics_io_num=5,.mode=1,.queue_size=1,
  .post_setup_cb=armed,.post_trans_cb=completed};
 err=spi_slave_initialize(SPI3_HOST,&bus,&slave,SPI_DMA_CH_AUTO);
 if(err!=ESP_OK){heap_caps_free(packet);heap_caps_free(commands);packet=NULL;}return err;
}
esp_err_t iq_spi_publish(const int8_t *ci8,size_t bytes,uint8_t source,
 uint32_t sequence,uint32_t timeout_ms){
 if(!packet || !ci8 || !bytes || bytes>32760 || bytes%2 || source>2)return ESP_ERR_INVALID_ARG;
 TickType_t wait=pdMS_TO_TICKS(timeout_ms);if(!wait)wait=1;
 spi_slave_transaction_t *done;
 // A timed-out DMA owns packet until the master drains it. Never overwrite it.
 if(pending){esp_err_t e=spi_slave_get_trans_result(SPI3_HOST,&done,wait);
  if(e!=ESP_OK)return e;
  pending=0;
  if(done->trans_len!=IQ_SPI_PACKET*8)return ESP_ERR_INVALID_SIZE;
  apply_command();
  if(artificial!=requested_artificial)return ESP_ERR_INVALID_STATE;}
 for(size_t offset=0;offset<bytes;offset+=IQ_SPI_CHUNK){
  if(iq_spi_packet_build(packet,ci8,bytes,source,sequence,offset,artificial))return ESP_ERR_INVALID_ARG;
  memset(&transaction,0,sizeof(transaction));transaction.length=IQ_SPI_PACKET*8;
  memset(commands,0,IQ_SPI_PACKET);
  transaction.tx_buffer=packet;transaction.rx_buffer=commands;
  esp_err_t err=spi_slave_queue_trans(SPI3_HOST,&transaction,wait);
  if(err!=ESP_OK)return err;
  pending=1;
  err=spi_slave_get_trans_result(SPI3_HOST,&done,wait);
  if(err!=ESP_OK)return err;
  pending=0;
  if(done->trans_len!=IQ_SPI_PACKET*8)return ESP_ERR_INVALID_SIZE;
  apply_command();
  if(artificial!=requested_artificial)return ESP_ERR_INVALID_STATE;
 }
 return ESP_OK;
}
