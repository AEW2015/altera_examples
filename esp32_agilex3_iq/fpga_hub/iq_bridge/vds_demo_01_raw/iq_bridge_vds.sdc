create_clock -name clk50 -period 20.000 [get_ports CLOCK1_50]
derive_clock_uncertainty
# Asynchronous UART enters two-register synchronizers. No synchronous external IO.
set_false_path -from [get_ports {HOST_RX RFS2_TX PMOD0_TX PMOD1_TX}]
set_false_path -to [get_ports {HOST_TX RFS2_RX PMOD0_RX PMOD1_RX}]
