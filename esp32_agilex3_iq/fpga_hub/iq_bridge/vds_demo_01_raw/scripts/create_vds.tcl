package require ::quartus::project
project_open iq_bridge_vds
load_package vds
foreach file [glob rtl/*.sv] {set_global_assignment -name SYSTEMVERILOG_FILE $file}
remove_all_global_assignments -name VDS_IP_FILE
remove_all_global_assignments -name IP_SEARCH_PATHS
vds::create_system -force iq_bridge_system
vds::create_cell -type rtl -files [list rtl/iq_bridge_controller.sv rtl/sync_fifo.sv] -top_module iq_bridge_controller capture_controller
vds::create_cell -type rtl -files [list rtl/iq_host_uart.sv rtl/uart_fractional.sv] -top_module iq_host_uart host_uart
vds::create_cell -type rtl -files [list rtl/iq_radio_uarts.sv rtl/uart_dynamic.sv] -top_module iq_radio_uarts radio_uarts
vds::create_cell -type rtl -files [list rtl/iq_capture_memory.sv] -top_module iq_capture_memory capture_ram
vds::create_cell -vlnv altera.com:ip:altera_clock_bridge:19.2.0 clock50
vds::create_cell -vlnv altera.com:ip:altera_reset_bridge:19.2.0 reset_bridge
puts "INTERFACES [vds::get_interface_pins]"
puts "PINS [vds::get_pins]"
vds::save_system
project_close
