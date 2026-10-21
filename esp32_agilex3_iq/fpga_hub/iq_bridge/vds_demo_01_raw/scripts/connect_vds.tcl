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
vds::export_interface_pins radio_uarts|uart2 radio2
puts "VALIDATION [vds::validate_system]"
vds::save_system
vds::update_project_setting
# Native update promotes the system to top; preserve board-level pins and POR.
set_global_assignment -name TOP_LEVEL_ENTITY iq_bridge_vds_top
remove_all_instance_assignments -name IO_STANDARD
foreach signal {CLOCK1_50 HOST_* RFS2_* PMOD0_* PMOD1_*} {
    set_instance_assignment -name IO_STANDARD "3.3-V LVCMOS" -to $signal
}
foreach file [glob rtl/*.sv] {set_global_assignment -name SYSTEMVERILOG_FILE $file}
export_assignments
vds::export_system -format tcl scripts/iq_bridge_system_export.tcl
vds::generate_system -synthesis VERILOG
project_close
