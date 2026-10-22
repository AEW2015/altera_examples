package require -exact qsys 26.1

set_module_property NAME svg_modem_mm
set_module_property VERSION 1.0
set_module_property DISPLAY_NAME "SVG graph modem register interface"
set_module_property DESCRIPTION "Avalon-MM wrapper for internal five-point SVG modem tests."
set_module_property GROUP "Atum IQ DSP"
set_module_property INSTANTIATE_IN_SYSTEM_MODULE true

add_fileset QUARTUS_SYNTH QUARTUS_SYNTH "" ""
set_fileset_property QUARTUS_SYNTH TOP_LEVEL svg_modem_mm
add_fileset_file svg_modem_mm.sv SYSTEM_VERILOG PATH ../rtl/svg_modem_mm.sv TOP_LEVEL_FILE
add_fileset_file svg_graph_encoder.sv SYSTEM_VERILOG PATH ../rtl/svg_graph_encoder.sv
add_fileset_file svg_graph_decoder.sv SYSTEM_VERILOG PATH ../rtl/svg_graph_decoder.sv
add_fileset_file svg_edge_waveform.sv SYSTEM_VERILOG PATH ../rtl/svg_edge_waveform.sv

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
set_interface_property csr explicitAddressSpan 256
set_interface_property csr readLatency 1
set_interface_property csr maximumPendingReadTransactions 0
add_interface_port csr avs_address address Input 6
add_interface_port csr avs_read read Input 1
add_interface_port csr avs_write write Input 1
add_interface_port csr avs_writedata writedata Input 32
add_interface_port csr avs_readdata readdata Output 32
add_interface_port csr avs_waitrequest waitrequest Output 1
