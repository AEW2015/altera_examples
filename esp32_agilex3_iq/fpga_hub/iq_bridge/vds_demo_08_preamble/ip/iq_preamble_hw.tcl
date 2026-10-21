package require -exact qsys 26.1
set_module_property NAME iq_preamble
set_module_property VERSION 1.0
set_module_property DISPLAY_NAME "Raw IQ QPSK preamble detector"
set_module_property GROUP "Atum IQ DSP"
set_module_property INSTANTIATE_IN_SYSTEM_MODULE true
add_fileset QUARTUS_SYNTH QUARTUS_SYNTH "" ""
set_fileset_property QUARTUS_SYNTH TOP_LEVEL iq_preamble
add_fileset_file iq_preamble.sv SYSTEM_VERILOG PATH ../rtl/iq_preamble.sv TOP_LEVEL_FILE
add_interface clock clock sink
add_interface_port clock clk clk Input 1
foreach r {reset bus_reset} {
 add_interface $r reset sink
 set_interface_property $r associatedClock clock
 set_interface_property $r synchronousEdges BOTH
 add_interface_port $r $r reset Input 1
}
add_interface csr avalon slave
set_interface_property csr associatedClock clock
set_interface_property csr associatedReset bus_reset
set_interface_property csr addressUnits WORDS
set_interface_property csr explicitAddressSpan 256
set_interface_property csr readLatency 0
add_interface_port csr avs_address address Input 6
add_interface_port csr avs_read read Input 1
add_interface_port csr avs_write write Input 1
add_interface_port csr avs_writedata writedata Input 32
add_interface_port csr avs_byteenable byteenable Input 4
add_interface_port csr avs_readdata readdata Output 32
add_interface_port csr avs_waitrequest waitrequest Output 1
add_interface capture conduit end
set_interface_property capture associatedClock clock
set_interface_property capture associatedReset reset
foreach {port role width} {cap_write write 1 cap_waddr waddr 15 cap_wdata wdata 16 cap_commit commit 1 cap_bank bank 1 cap_samples samples 15 cap_job job 32 cap_crc crc 32 cap_rate rate 32 cap_frequency frequency 32 cap_source source 2} {
 add_interface_port capture $port $role Input $width
}
