package require -exact qsys 26.1
set_module_property NAME iq_ddc_engine
set_module_property VERSION 1.0
set_module_property GROUP "Atum IQ Bridge"
set_module_property DISPLAY_NAME "DDC: NCO + complex mixer + decimator + CI16 RAM"
set_module_property INSTANTIATE_IN_SYSTEM_MODULE true
set_module_property EDITABLE true
set_module_property INTERNAL false
add_fileset QUARTUS_SYNTH QUARTUS_SYNTH "" ""
set_fileset_property QUARTUS_SYNTH TOP_LEVEL iq_ddc_engine
add_fileset_file iq_ddc_engine.sv SYSTEM_VERILOG PATH ../rtl/iq_ddc_engine.sv TOP_LEVEL_FILE
add_interface clock clock sink
set_interface_property clock clockRate 50000000
add_interface_port clock clk clk Input 1
add_interface reset reset sink
set_interface_property reset associatedClock clock
set_interface_property reset synchronousEdges NONE
add_interface_port reset reset reset Input 1
add_interface fir_reset reset source
set_interface_property fir_reset associatedClock clock
set_interface_property fir_reset synchronousEdges DEASSERT
add_interface_port fir_reset fir_reset_n reset_n Output 1
add_interface source conduit end
set_interface_property source associatedClock clock
set_interface_property source associatedReset reset
add_interface_port source source_ready ready Input 1
add_interface_port source source_meta meta Input 320
add_interface_port source source_epoch epoch Input 32
add_interface_port source source_q q Input 16
add_interface_port source exclusive exclusive Output 1
add_interface_port source source_addr addr Output 14
add_interface i_input avalon_streaming source
set_interface_property i_input associatedClock clock
set_interface_property i_input associatedReset reset
set_interface_property i_input dataBitsPerSymbol 16
set_interface_property i_input readyLatency 0
add_interface_port i_input i_data data Output 16
add_interface_port i_input in_valid valid Output 1
add_interface_port i_input in_error error Output 2
add_interface q_input avalon_streaming source
set_interface_property q_input associatedClock clock
set_interface_property q_input associatedReset reset
set_interface_property q_input dataBitsPerSymbol 16
set_interface_property q_input readyLatency 0
add_interface_port q_input q_data data Output 16
add_interface_port q_input q_in_valid valid Output 1
add_interface_port q_input q_in_error error Output 2
add_interface i_output avalon_streaming sink
set_interface_property i_output associatedClock clock
set_interface_property i_output associatedReset reset
set_interface_property i_output dataBitsPerSymbol 39
set_interface_property i_output readyLatency 0
add_interface_port i_output i_result data Input 39
add_interface_port i_output i_valid valid Input 1
add_interface_port i_output i_error error Input 2
add_interface q_output avalon_streaming sink
set_interface_property q_output associatedClock clock
set_interface_property q_output associatedReset reset
set_interface_property q_output dataBitsPerSymbol 39
set_interface_property q_output readyLatency 0
add_interface_port q_output q_result data Input 39
add_interface_port q_output q_valid valid Input 1
add_interface_port q_output q_error error Input 2
add_interface csr avalon slave
set_interface_property csr associatedClock clock
set_interface_property csr associatedReset reset
set_interface_property csr addressUnits WORDS
set_interface_property csr readLatency 0
set_interface_property csr readWaitTime 0
set_interface_property csr writeWaitTime 0
set_interface_property csr maximumPendingReadTransactions 0
add_interface_port csr address address Input 6
add_interface_port csr read read Input 1
add_interface_port csr write write Input 1
add_interface_port csr writedata writedata Input 32
add_interface_port csr readdata readdata Output 32


add_interface gain conduit end
set_interface_property gain associatedClock clock
set_interface_property gain associatedReset reset
add_interface_port gain gain_start start Output 1
add_interface_port gain gain_bypass bypass Output 1
add_interface_port gain gain_q8 q8 Output 13
add_interface_port gain gain_input_i input_i Output 16
add_interface_port gain gain_input_q input_q Output 16
add_interface_port gain gain_input_valid input_valid Output 1
add_interface_port gain gain_output_i output_i Input 16
add_interface_port gain gain_output_q output_q Input 16
add_interface_port gain gain_output_valid output_valid Input 1
add_interface_port gain gain_samples samples Input 32
add_interface_port gain gain_pre_peak pre_peak Input 32
add_interface_port gain gain_pre_rails pre_rails Input 32
add_interface_port gain gain_post_peak post_peak Input 32
add_interface_port gain gain_clips clips Input 32
add_interface_port gain gain_pre_power pre_power Input 64
add_interface_port gain gain_post_power post_power Input 64
