package require -exact qsys 26.1
set_module_property NAME iq_gain_meter
set_module_property VERSION 1.0
set_module_property GROUP "Atum IQ Bridge"
set_module_property DISPLAY_NAME "CI16 manual gain + pre/post power meters"
set_module_property INSTANTIATE_IN_SYSTEM_MODULE true
set_module_property EDITABLE true
set_module_property INTERNAL false
add_fileset QUARTUS_SYNTH QUARTUS_SYNTH "" ""
set_fileset_property QUARTUS_SYNTH TOP_LEVEL iq_gain_meter
add_fileset_file iq_gain_meter.sv SYSTEM_VERILOG PATH ../rtl/iq_gain_meter.sv TOP_LEVEL_FILE
add_interface clock clock sink
set_interface_property clock clockRate 50000000
add_interface_port clock clk clk Input 1
add_interface reset reset sink
set_interface_property reset associatedClock clock
set_interface_property reset synchronousEdges BOTH
add_interface_port reset reset reset Input 1
add_interface gain conduit end
set_interface_property gain associatedClock clock
set_interface_property gain associatedReset reset
add_interface_port gain start start Input 1
add_interface_port gain bypass bypass Input 1
add_interface_port gain gain_q8 q8 Input 13
add_interface_port gain input_i input_i Input 16
add_interface_port gain input_q input_q Input 16
add_interface_port gain input_valid input_valid Input 1
add_interface_port gain output_i output_i Output 16
add_interface_port gain output_q output_q Output 16
add_interface_port gain output_valid output_valid Output 1
add_interface_port gain samples samples Output 32
add_interface_port gain pre_peak pre_peak Output 32
add_interface_port gain pre_rails pre_rails Output 32
add_interface_port gain post_peak post_peak Output 32
add_interface_port gain clips clips Output 32
add_interface_port gain pre_power pre_power Output 64
add_interface_port gain post_power post_power Output 64
