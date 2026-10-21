package require ::quartus::project
project_open iq_bridge_vds
load_package vds
vds::open_system iq_bridge_system
vds::set_properties {parameters:EXPLICIT_CLOCK_RATE 50000000} clock50
vds::set_properties {parameters:SYNCHRONOUS_EDGES both parameters:SYNC_RESET 0} reset_bridge
vds::connect_interface_net -src capture_controller|host_link -dest host_uart|host_link
vds::connect_interface_net -src capture_controller|radio_link -dest radio_uarts|radio_link
vds::connect_interface_net -src capture_controller|capture_memory -dest capture_ram|capture_memory
foreach cell {capture_controller host_uart radio_uarts capture_ram} {
    vds::connect_net -src clock50|out_clk -dest $cell|clk
    vds::connect_net -src reset_bridge|out_reset -dest $cell|reset
}
vds::connect_net -src clock50|out_clk -dest reset_bridge|clk
vds::export_pins clock50|in_clk clk
vds::export_pins reset_bridge|in_reset reset
vds::export_interface_pins host_uart|serial host_serial
vds::export_interface_pins radio_uarts|uart0 radio0
vds::export_interface_pins radio_uarts|uart1 radio1
vds::export_interface_pins radio_uarts|spi spi
vds::connect_net -src clock50|out_clk -dest cpu_reset|clk
vds::export_pins cpu_reset|in_reset monitor_reset
vds::connect_net -src clock50|out_clk -dest cpu|clk
vds::connect_net -src clock50|out_clk -dest cpu_ram|clk1
vds::connect_net -src clock50|out_clk -dest jtag_uart|clk
vds::connect_net -src clock50|out_clk -dest transfer_monitor|clock
vds::connect_net -src cpu_reset|out_reset -dest cpu|reset
vds::connect_net -src cpu_reset|out_reset -dest cpu_ram|reset1
vds::connect_net -src cpu_reset|out_reset -dest jtag_uart|reset
vds::connect_net -src reset_bridge|out_reset -dest transfer_monitor|reset
vds::connect_net -src cpu_reset|out_reset -dest transfer_monitor|bus_reset
vds::connect_interface_net -src capture_controller|telemetry -dest transfer_monitor|telemetry
foreach manager {data_manager instruction_manager} {
 vds::connect_interface_net -src cpu|$manager -dest cpu_ram|s1
 vds::assign_base_address -connection cpu.$manager/cpu_ram.s1 0x00000000
 vds::connect_interface_net -src cpu|$manager -dest cpu|dm_agent
 vds::assign_base_address -connection cpu.$manager/cpu.dm_agent 0x00020000
}
vds::connect_interface_net -src cpu|data_manager -dest cpu|timer_sw_agent
vds::assign_base_address -connection cpu.data_manager/cpu.timer_sw_agent 0x00030000
vds::connect_interface_net -src cpu|data_manager -dest jtag_uart|avalon_jtag_slave
vds::assign_base_address -connection cpu.data_manager/jtag_uart.avalon_jtag_slave 0x10010000
vds::connect_interface_net -src cpu|data_manager -dest transfer_monitor|csr
vds::assign_base_address -connection cpu.data_manager/transfer_monitor.csr 0x10020000
vds::connect_interface_net -src jtag_uart|irq -dest cpu|platform_irq_rx
vds::set_interrupt_irq -connection cpu.platform_irq_rx/jtag_uart.irq 0
vds::connect_net -src clock50|out_clk -dest fir_capture|clock
vds::connect_net -src reset_bridge|out_reset -dest fir_capture|reset
vds::connect_net -src cpu_reset|out_reset -dest fir_capture|bus_reset
vds::connect_interface_net -src capture_controller|fir_capture -dest fir_capture|capture
vds::connect_net -src clock50|out_clk -dest fir_ii|clk
vds::connect_net -src clock50|out_clk -dest fir_ii|coeff_clock
vds::connect_net -src reset_bridge|out_reset -dest fir_ii|rst
vds::connect_net -src cpu_reset|out_reset -dest fir_ii|coeff_reset
vds::connect_interface_net -src fir_capture|filter_input -dest fir_ii|avalon_streaming_sink
vds::connect_interface_net -src fir_ii|avalon_streaming_source -dest fir_capture|filter_output
vds::connect_interface_net -src cpu|data_manager -dest fir_capture|csr
vds::assign_base_address -connection cpu.data_manager/fir_capture.csr 0x10030000
vds::connect_interface_net -src cpu|data_manager -dest fir_ii|avalon_mm_slave
vds::assign_base_address -connection cpu.data_manager/fir_ii.avalon_mm_slave 0x10040000
vds::connect_interface_net -src capture_controller|fir_uart -dest fir_capture|uart
puts "VALIDATION [vds::validate_system]"
vds::save_system
vds::update_project_setting
# Native update promotes the system to top; preserve board-level pins and POR.
set_global_assignment -name TOP_LEVEL_ENTITY iq_bridge_vds_top
remove_all_instance_assignments -name IO_STANDARD
foreach signal {CLOCK1_50 HOST_* RFS2_* PMOD0_* SPI_*} {
    set_instance_assignment -name IO_STANDARD "3.3-V LVCMOS" -to $signal
}
foreach file [glob rtl/*.sv] {if {[file tail $file] ni {iq_transfer_monitor.sv iq_fir_capture.sv}} {set_global_assignment -name SYSTEMVERILOG_FILE $file}}
export_assignments
vds::export_system -format tcl scripts/iq_bridge_system_export.tcl
vds::generate_system -synthesis VERILOG
puts [exec python3 scripts/patch_fir_reset.py]
project_close
