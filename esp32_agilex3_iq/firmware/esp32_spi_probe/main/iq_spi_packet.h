#pragma once
#include <stdint.h>
#include <stddef.h>
#define IQ_SPI_CHUNK 1024
#define IQ_SPI_PACKET 1056
// Portable wire encoder, used by DMA slave and native cross-language tests.
int iq_spi_packet_build(uint8_t *packet,const int8_t *capture,size_t total,
                        uint8_t source,uint32_t sequence,size_t offset,uint8_t synthetic);
// Full transaction only: 1=T/synthetic, 2=R/RF, 0=no valid bounded command.
int iq_spi_packet_command(const uint8_t *mosi,size_t length);
