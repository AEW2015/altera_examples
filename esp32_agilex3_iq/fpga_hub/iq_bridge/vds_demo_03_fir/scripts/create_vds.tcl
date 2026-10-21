package require ::quartus::project
project_open iq_bridge_vds
foreach file [glob rtl/*.sv] {if {[file tail $file] ni {iq_transfer_monitor.sv iq_fir_capture.sv}} {set_global_assignment -name SYSTEMVERILOG_FILE $file}}
remove_all_global_assignments -name VDS_IP_FILE
remove_all_global_assignments -name IP_SEARCH_PATHS
set_global_assignment -name IP_SEARCH_PATHS "ip/**/*;$::env(QUARTUS_ROOTDIR)/../ip/**/*"
export_assignments
load_package vds
vds::create_system -force iq_bridge_system
vds::create_cell -type rtl -files [list rtl/iq_bridge_controller.sv rtl/sync_fifo.sv] -top_module iq_bridge_controller capture_controller
vds::create_cell -type rtl -files [list rtl/iq_host_uart.sv rtl/uart_fractional.sv] -top_module iq_host_uart host_uart
vds::create_cell -type rtl -files [list rtl/iq_radio_uarts.sv rtl/uart_dynamic.sv] -top_module iq_radio_uarts radio_uarts
vds::create_cell -type rtl -files [list rtl/iq_capture_memory.sv] -top_module iq_capture_memory capture_ram
vds::create_cell -vlnv altera.com:ip:altera_clock_bridge:19.2.0 clock50
vds::create_cell -vlnv altera.com:ip:altera_reset_bridge:19.2.0 reset_bridge
vds::create_cell -properties {parameters:enableAvalonInterface true parameters:resetOffset 0} -vlnv altera.com:ip:intel_niosv_m:26.0.0 cpu
vds::create_cell -properties [list parameters:memorySize 65536 parameters:initMemContent true parameters:useNonDefaultInitFile true parameters:initializationFileName [file join [get_project_directory] sw monitor.hex] parameters:copyInitFile true] -vlnv altera.com:ip:intel_onchip_memory:2.0.0 cpu_ram
vds::create_cell -properties {parameters:writeBufferDepth 4096 parameters:readBufferDepth 64} -vlnv altera.com:ip:altera_avalon_jtag_uart:19.3.2 jtag_uart
vds::create_cell -vlnv altera.com:ip:iq_transfer_monitor:1.0 transfer_monitor
vds::create_cell -properties {parameters:SYNCHRONOUS_EDGES both parameters:SYNC_RESET 1} -vlnv altera.com:ip:altera_reset_bridge:19.2.0 cpu_reset
vds::create_cell -vlnv altera.com:ip:iq_fir_capture:1.0 fir_capture
vds::create_cell -vlnv altera.com:ip:altera_fir_compiler_ii:19.3.8 -properties {parameters:deviceFamily {Agilex 3} parameters:clockRate 50 parameters:inputRate 50 parameters:inputChannelNum 2 parameters:coeffScaling none parameters:coeffType int parameters:coeffBitWidth 16 parameters:coeffSetRealValue {2048,2048,2048,2048,2048,2048,2048,2048,2048,2048,2048,2048,2048,2048,2048,2048} parameters:coeffReload true parameters:readWriteMode read_write parameters:busDataWidth 16 parameters:backPressure false parameters:resetRezero true parameters:symmetryMode nsym parameters:inputBitWidth 8} fir_ii
puts "INTERFACES [vds::get_interface_pins]"
puts "PINS [vds::get_pins]"
vds::save_system
project_close
