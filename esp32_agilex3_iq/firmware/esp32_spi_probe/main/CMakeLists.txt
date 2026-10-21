idf_component_register(SRCS "main.c" "iq_spi_slave.c" "iq_spi_packet.c" INCLUDE_DIRS "." REQUIRES esp_driver_spi esp_driver_gpio esp_hw_support)
