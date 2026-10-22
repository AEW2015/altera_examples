package require ::quartus::project
project_open iq_bridge_vds
foreach file [glob rtl/*.sv] {if {[file tail $file] ni {iq_transfer_monitor.sv iq_fir_capture.sv iq_ddc_engine.sv iq_gain_meter.sv iq_modem.sv}} {set_global_assignment -name SYSTEMVERILOG_FILE $file}}
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
vds::create_cell -properties [list parameters:memorySize 262144 parameters:initMemContent true parameters:useNonDefaultInitFile true parameters:initializationFileName [file join [get_project_directory] sw monitor.hex] parameters:copyInitFile true] -vlnv altera.com:ip:intel_onchip_memory:2.0.0 cpu_ram
vds::create_cell -properties {parameters:writeBufferDepth 4096 parameters:readBufferDepth 64} -vlnv altera.com:ip:altera_avalon_jtag_uart:19.3.2 jtag_uart
vds::create_cell -vlnv altera.com:ip:iq_transfer_monitor:1.0 transfer_monitor
vds::create_cell -properties {parameters:SYNCHRONOUS_EDGES both parameters:SYNC_RESET 1} -vlnv altera.com:ip:altera_reset_bridge:19.2.0 cpu_reset
vds::create_cell -vlnv altera.com:ip:iq_fir_capture:1.0 fir_capture
vds::create_cell -vlnv altera.com:ip:altera_fir_compiler_ii:19.3.8 -properties {parameters:deviceFamily {Agilex 3} parameters:clockRate 50 parameters:inputRate 50 parameters:inputChannelNum 2 parameters:coeffScaling none parameters:coeffType int parameters:coeffBitWidth 16 parameters:coeffSetRealValue {2048,2048,2048,2048,2048,2048,2048,2048,2048,2048,2048,2048,2048,2048,2048,2048} parameters:coeffReload true parameters:readWriteMode read_write parameters:busDataWidth 16 parameters:backPressure false parameters:resetRezero true parameters:symmetryMode nsym parameters:inputBitWidth 8} fir_ii
vds::create_cell -vlnv altera.com:ip:iq_ddc_engine:1.0 ddc_engine
vds::create_cell -vlnv altera.com:ip:altera_fir_compiler_ii:19.3.8 -properties {parameters:deviceFamily {Agilex 3} parameters:clockRate 50 parameters:inputRate 1 parameters:inputBitWidth 16 parameters:coeffBitWidth 16 parameters:coeffType int parameters:coeffScaling none parameters:coeffSetRealValue {0,0,0,1,2,2,2,1,-2,-5,-7,-8,-6,0,8,15,20,18,8,-8,-25,-38,-41,-29,-4,30,62,78,71,36,-20,-81,-127,-137,-101,-22,81,176,229,211,116,-37,-208,-340,-378,-292,-88,189,456,619,600,366,-53,-559,-999,-1207,-1038,-418,630,1980,3421,4701,5584,5898,5584,4701,3421,1980,630,-418,-1038,-1207,-999,-559,-53,366,600,619,456,189,-88,-292,-378,-340,-208,-37,116,211,229,176,81,-22,-101,-137,-127,-81,-20,36,71,78,62,30,-4,-29,-41,-38,-25,-8,8,18,20,15,8,0,-6,-8,-7,-5,-2,1,2,2,2,1,0,0,0} parameters:resetRezero true parameters:backPressure false} ddc_fir_i
vds::create_cell -vlnv altera.com:ip:altera_fir_compiler_ii:19.3.8 -properties {parameters:deviceFamily {Agilex 3} parameters:clockRate 50 parameters:inputRate 1 parameters:inputBitWidth 16 parameters:coeffBitWidth 16 parameters:coeffType int parameters:coeffScaling none parameters:coeffSetRealValue {0,0,0,1,2,2,2,1,-2,-5,-7,-8,-6,0,8,15,20,18,8,-8,-25,-38,-41,-29,-4,30,62,78,71,36,-20,-81,-127,-137,-101,-22,81,176,229,211,116,-37,-208,-340,-378,-292,-88,189,456,619,600,366,-53,-559,-999,-1207,-1038,-418,630,1980,3421,4701,5584,5898,5584,4701,3421,1980,630,-418,-1038,-1207,-999,-559,-53,366,600,619,456,189,-88,-292,-378,-340,-208,-37,116,211,229,176,81,-22,-101,-137,-127,-81,-20,36,71,78,62,30,-4,-29,-41,-38,-25,-8,8,18,20,15,8,0,-6,-8,-7,-5,-2,1,2,2,2,1,0,0,0} parameters:resetRezero true parameters:backPressure false} ddc_fir_q
vds::create_cell -vlnv altera.com:ip:iq_gain_meter:1.0 gain_meter
vds::create_cell -vlnv altera.com:ip:iq_modem:1.0 modem
puts "INTERFACES [vds::get_interface_pins]"
puts "PINS [vds::get_pins]"
vds::save_system
project_close
