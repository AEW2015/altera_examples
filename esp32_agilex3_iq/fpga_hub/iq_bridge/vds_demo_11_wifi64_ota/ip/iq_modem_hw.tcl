package require -exact qsys 26.1
set_module_property NAME iq_modem
set_module_property VERSION 1.0
set_module_property GROUP "Atum RF Modem"
set_module_property DISPLAY_NAME "BPSK to 64-QAM + soft Viterbi burst modem"
set_module_property INSTANTIATE_IN_SYSTEM_MODULE true
set_module_property EDITABLE true
add_fileset QUARTUS_SYNTH QUARTUS_SYNTH "" ""
set_fileset_property QUARTUS_SYNTH TOP_LEVEL iq_modem
add_fileset_file iq_modem.sv SYSTEM_VERILOG PATH ../rtl/iq_modem.sv TOP_LEVEL_FILE
add_interface clock clock sink
set_interface_property clock clockRate 50000000
add_interface_port clock clk clk Input 1
add_interface reset reset sink
set_interface_property reset associatedClock clock
set_interface_property reset synchronousEdges BOTH
add_interface_port reset reset reset Input 1
add_interface csr avalon slave
set_interface_property csr associatedClock clock
set_interface_property csr associatedReset reset
set_interface_property csr addressUnits WORDS
set_interface_property csr readLatency 0
set_interface_property csr maximumPendingReadTransactions 0
add_interface_port csr avs_address address Input 4
add_interface_port csr avs_read read Input 1
add_interface_port csr avs_write write Input 1
add_interface_port csr avs_writedata writedata Input 32
add_interface_port csr avs_byteenable byteenable Input 4
add_interface_port csr avs_readdata readdata Output 32
add_interface_port csr avs_waitrequest waitrequest Output 1
