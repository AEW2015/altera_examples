#include "iq_spi_packet.h"
#include <string.h>
#ifdef ESP_PLATFORM
#include "esp_crc.h"
static uint32_t crc32(const uint8_t *data,size_t bytes){return esp_crc32_le(0,data,bytes);}
#else
static uint32_t crc32(const uint8_t *data,size_t bytes){
 uint32_t crc=~0u;
 for(size_t n=0;n<bytes;n++){
  crc^=data[n];
  for(unsigned bit=0;bit<8;bit++)crc=(crc>>1)^(0xedb88320u & (0u-(crc&1u)));
 }
 return ~crc;
}
#endif
static void put32(uint8_t *p,uint32_t value){for(unsigned n=0;n<4;n++)p[n]=(uint8_t)(value>>(n*8));}
int iq_spi_packet_build(uint8_t *packet,const int8_t *capture,size_t total,
 uint8_t source,uint32_t sequence,size_t offset,uint8_t synthetic){
 if(!packet || !capture || !total || total>32760 || total%2 || source>2 ||
    offset>=total || offset%IQ_SPI_CHUNK || synthetic>1)return -1;
 size_t length=total-offset;if(length>IQ_SPI_CHUNK)length=IQ_SPI_CHUNK;
 memset(packet,0,IQ_SPI_PACKET);memcpy(packet,"IQS1",4);
 packet[4]=1;packet[5]=source;packet[6]=((offset+length==total)?1:0)|(synthetic<<1);packet[7]=32;
 put32(packet+8,sequence);put32(packet+12,(uint32_t)offset);
 put32(packet+16,(uint32_t)total);put32(packet+20,(uint32_t)length);
 memcpy(packet+32,capture+offset,length);
 put32(packet+24,crc32(packet+32,length));put32(packet+28,crc32(packet,28));
 return 0;
}
int iq_spi_packet_command(const uint8_t *mosi,size_t length){
 if(!mosi || length!=IQ_SPI_PACKET)return 0;
 for(size_t n=1;n<length;n++)if(mosi[n])return 0;
 return mosi[0]=='T'?1:mosi[0]=='R'?2:0;
}
