onerror {quit -force -code 1}
vlib work
vlog -sv rtl/iq_gain_meter.sv tb_gain_lesson.sv
vsim -voptargs=+acc -wlf gain.wlf work.tb_gain_lesson
log -r /*
run -all
quit -force -code 0
