create_clock -name clk50 -period 20.000 [get_ports CLOCK1_50]
# Debug/JTAG maximum cable frequency 16 MHz (actual Atum cable: 15 MHz).
create_clock -name altera_reserved_tck -period 62.500 [get_ports altera_reserved_tck]
set_clock_groups -asynchronous -group [get_clocks altera_reserved_tck]
derive_clock_uncertainty
# Asynchronous UART enters two-register synchronizers. No synchronous external IO.
set_false_path -from [get_ports {HOST_RX RFS2_TX PMOD0_TX PMOD1_TX}]
set_false_path -to [get_ports {HOST_TX RFS2_RX PMOD0_RX PMOD1_RX}]
