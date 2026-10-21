# Read-only post-fit evidence, including the actual forwarded SPI clock.
package require ::quartus::project
package require ::quartus::sta
project_open iq_bridge_vds
create_timing_netlist
read_sdc
update_timing_netlist
report_clocks -file run/clocks.rpt
report_clock_fmax_summary -file run/fmax.rpt
report_ucp -file run/unconstrained.rpt
report_timing -setup -npaths 5 -detail full_path -file run/setup_paths.rpt
report_timing -hold -npaths 5 -detail full_path -file run/hold_paths.rpt
check_timing -include {no_clock multiple_clock no_input_delay no_output_delay} -file run/check_timing.rpt
delete_timing_netlist
project_close
