package require -exact qsys 26.1
set_module_property NAME iq_fir_capture
set_module_property VERSION 1.0
set_module_property DISPLAY_NAME "IQ snapshot / FIR control / paired RAM"
set_module_property GROUP "Atum IQ DSP"
set_module_property INSTANTIATE_IN_SYSTEM_MODULE true
add_fileset QUARTUS_SYNTH QUARTUS_SYNTH "" ""
set_fileset_property QUARTUS_SYNTH TOP_LEVEL iq_fir_capture
add_fileset_file iq_fir_capture.sv SYSTEM_VERILOG PATH ../rtl/iq_fir_capture.sv TOP_LEVEL_FILE
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
add_interface filter_input avalon_streaming start
set_interface_property filter_input associatedClock clock
set_interface_property filter_input associatedReset reset
set_interface_property filter_input dataBitsPerSymbol 8
set_interface_property filter_input symbolsPerBeat 2
set_interface_property filter_input maxChannel 0
add_interface_port filter_input fir_data data Output 16
add_interface_port filter_input fir_valid valid Output 1
add_interface_port filter_input fir_error error Output 2
add_interface filter_output avalon_streaming end
set_interface_property filter_output associatedClock clock
set_interface_property filter_output associatedReset reset
set_interface_property filter_output dataBitsPerSymbol 28
set_interface_property filter_output symbolsPerBeat 2
set_interface_property filter_output maxChannel 0
add_interface_port filter_output fir_result data Input 56
add_interface_port filter_output fir_result_valid valid Input 1
add_interface_port filter_output fir_result_error error Input 2

add_interface uart conduit end
set_interface_property uart associatedClock clock
set_interface_property uart associatedReset reset
foreach {port role direction width} {uart_arm arm Input 1 uart_owned owned Input 1 uart_index index Input 14 uart_enable enable Output 1 uart_available available Output 1 uart_done done Output 1 uart_fault fault Output 1 uart_q q Output 16 uart_crc crc Output 32 uart_profile profile Output 32} {
 add_interface_port uart $port $role $direction $width
}
