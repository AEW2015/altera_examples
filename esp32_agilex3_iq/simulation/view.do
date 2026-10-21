view wave
delete wave *
add wave -divider Control
add wave gain:/tb_gain_lesson/clk gain:/tb_gain_lesson/reset gain:/tb_gain_lesson/start gain:/tb_gain_lesson/bypass
add wave -radix unsigned gain:/tb_gain_lesson/gain_q8
add wave -divider IQ
add wave -radix decimal gain:/tb_gain_lesson/input_i gain:/tb_gain_lesson/input_q gain:/tb_gain_lesson/output_i gain:/tb_gain_lesson/output_q
add wave gain:/tb_gain_lesson/input_valid gain:/tb_gain_lesson/output_valid
add wave -divider Meters
add wave -radix unsigned gain:/tb_gain_lesson/samples gain:/tb_gain_lesson/pre_power gain:/tb_gain_lesson/post_power gain:/tb_gain_lesson/clips
update
wave zoom range 0ns 4600ns
puts "WAVE_VIEW_PASS: gain dataset signals loaded"
set f [open gui-view-pass.txt w]; puts $f PASS; close $f
