create_clock -name clk50 -period 20.000 [get_ports CLOCK1_50]
# Debug/JTAG maximum cable frequency 16 MHz (actual Atum cable: 15 MHz).
create_clock -name altera_reserved_tck -period 62.500 [get_ports altera_reserved_tck]
set_clock_groups -asynchronous -group [get_clocks altera_reserved_tck]
# Explicit external JTAG timing budget at <=16MHz; distinct from system UART.
set_input_delay -clock altera_reserved_tck -clock_fall -max 10.000 [get_ports {altera_reserved_tdi altera_reserved_tms}]
set_input_delay -clock altera_reserved_tck -clock_fall -min 0.000 [get_ports {altera_reserved_tdi altera_reserved_tms}]
set_output_delay -clock altera_reserved_tck -max 10.000 [get_ports altera_reserved_tdo]
set_output_delay -clock altera_reserved_tck -min 0.000 [get_ports altera_reserved_tdo]
derive_clock_uncertainty
# Asynchronous UART enters two-register synchronizers. No synchronous external IO.
set_false_path -from [get_ports {HOST_RX RFS2_TX PMOD0_TX}]
set_false_path -to [get_ports {HOST_TX RFS2_RX PMOD0_RX}]

# 5 MHz, mode1: slave launches after rising SCK, master samples after falling.
create_generated_clock -name spi_clk -source [get_ports CLOCK1_50] -divide_by 10 [get_registers {*spi_proxy|spi|sck}]
# Conservative first-pass external budget, not a measured board timing result.
set_input_delay -clock spi_clk -reference_pin [get_ports SPI_SCK] -max 75.000 [get_ports SPI_MISO]
set_input_delay -clock spi_clk -reference_pin [get_ports SPI_SCK] -min 0.000 [get_ports SPI_MISO]
# The master samples only each fifth 50 MHz edge after the launch edge.
set_multicycle_path 5 -setup -from [get_clocks spi_clk] -to [get_clocks clk50]
set_multicycle_path 4 -hold -from [get_clocks spi_clk] -to [get_clocks clk50]
set_output_delay -clock spi_clk -reference_pin [get_ports SPI_SCK] -clock_fall -max 10.000 [get_ports {SPI_MOSI SPI_CS_N}]
set_output_delay -clock spi_clk -reference_pin [get_ports SPI_SCK] -clock_fall -min 0.000 [get_ports {SPI_MOSI SPI_CS_N}]
set_false_path -from [get_ports SPI_READY]
# CS assertion precedes first sampling by >=5 clocks; release follows final
# sampling by one full clock (rx_valid/ready).
set_multicycle_path 5 -start -setup -from [get_clocks clk50] -to [get_ports SPI_CS_N]
# CS is released on the cycle AFTER final MISO sampling (rx_valid/ready).
# Therefore its earliest next transition is one 50MHz cycle after the sample.
set_multicycle_path 5 -start -hold -from [get_clocks clk50] -to [get_ports SPI_CS_N]
# Mode1 MOSI changes only on leading SCK edges, 100ns before/after sampling.
# Destination reference is falling SCK. Launch0 -> sample100 -> nextlaunch200.
set_multicycle_path 5 -start -setup -from [get_clocks clk50] -to [get_ports SPI_MOSI]
set_multicycle_path 9 -start -hold -from [get_clocks clk50] -to [get_ports SPI_MOSI]
