package require -exact qsys 26.1
set_module_property NAME iq_transfer_monitor
set_module_property VERSION 1.0
set_module_property GROUP "Atum IQ Monitor"
set_module_property DISPLAY_NAME "IQ Transfer Monitor Registers"
set_module_property INSTANTIATE_IN_SYSTEM_MODULE true
add_fileset QUARTUS_SYNTH QUARTUS_SYNTH "" ""
set_fileset_property QUARTUS_SYNTH TOP_LEVEL iq_transfer_monitor
add_fileset_file iq_transfer_monitor.sv SYSTEM_VERILOG PATH ../rtl/iq_transfer_monitor.sv TOP_LEVEL_FILE
add_interface clock clock sink
add_interface_port clock clk clk Input 1
add_interface reset reset sink
set_interface_property reset associatedClock clock
set_interface_property reset synchronousEdges BOTH
add_interface_port reset reset reset Input 1
add_interface bus_reset reset sink
set_interface_property bus_reset associatedClock clock
set_interface_property bus_reset synchronousEdges BOTH
add_interface_port bus_reset bus_reset reset Input 1
add_interface csr avalon slave
set_interface_property csr associatedClock clock
set_interface_property csr associatedReset bus_reset
set_interface_property csr addressUnits WORDS
set_interface_property csr explicitAddressSpan 256
set_interface_property csr readLatency 0
set_interface_property csr minimumResponseLatency 1
add_interface_port csr avs_address address Input 6
add_interface_port csr avs_read read Input 1
add_interface_port csr avs_write write Input 1
add_interface_port csr avs_writedata writedata Input 32
add_interface_port csr avs_byteenable byteenable Input 4
add_interface_port csr avs_readdata readdata Output 32
add_interface_port csr avs_waitrequest waitrequest Output 1
add_interface telemetry conduit end
set_interface_property telemetry associatedClock clock
set_interface_property telemetry associatedReset reset
add_interface_port telemetry mon_radio_byte radio_byte Input 3
add_interface_port telemetry mon_radio_tx radio_tx Input 3
add_interface_port telemetry mon_iq_byte iq_byte Input 3
add_interface_port telemetry mon_capture_ok capture_ok Input 3
add_interface_port telemetry mon_host_rx host_rx Input 1
add_interface_port telemetry mon_host_tx host_tx Input 1
add_interface_port telemetry mon_host_iq host_iq Input 1
add_interface_port telemetry mon_host_capture host_capture Input 1
add_interface_port telemetry mon_command_errors command_errors Input 32
add_interface_port telemetry mon_radio_errors radio_errors Input 32
add_interface_port telemetry mon_capture_errors capture_errors Input 32
add_interface_port telemetry mon_text_drops text_drops Input 32
add_interface_port telemetry mon_state state Input 32
