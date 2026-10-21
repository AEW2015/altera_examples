#!/usr/bin/env python3
"""Qualify checkpoint07's SPI radio proxy without accessing hardware."""
import subprocess,sys,zlib,fcntl,shutil
from common import ROOT,tool_command,tool_path,tool_exe,tool_env
sys.path.insert(0,str(ROOT/'cyberether'))
from spi_ci8 import encode,CHUNK
stage=ROOT/'fpga_hub/iq_bridge/vds_demo_07_spi_fir'
(stage/'run').mkdir(exist_ok=True)
# Generation replaces vendor HDL; refuse concurrent mutation during simulation.
project_lock=(stage/'run/build.lock').open('a')
fcntl.flock(project_lock,fcntl.LOCK_SH)
out=ROOT/'simulation/spi_pipeline';out.mkdir(parents=True,exist_ok=True)
simulation_lock=(out/'simulation.lock').open('a')
fcntl.flock(simulation_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
for library in ('work','fir_vendor'):shutil.rmtree(out/library,ignore_errors=True)
for name,start,seq,synth in [('synthetic',11,1,True),('rf',73,2,False)]:
 data=bytes((n*37+start)&255 for n in range(32760))
 print(name,'CRC',f'{zlib.crc32(data):08x}',flush=True)
 packets=b''.join(encode(2,seq,n,len(data),data[n:n+CHUNK],synthetic=synth) for n in range(0,len(data),CHUNK))
 (out/(name+'.hex')).write_text('\n'.join(f'{v:02x}' for v in packets)+'\n')
stage=ROOT/'fpga_hub/iq_bridge/vds_demo_07_spi_fir'
sources=[stage/'rtl'/n for n in ['iq_spi_master.sv','iq_spi_capture_meter.sv','iq_spi_radio_proxy.sv']]+[stage/'sim/tb_iq_spi_radio_proxy.sv']
script=out/'run.do';script.write_text('\n'.join(['onerror {quit -code 1}','vlib work','vlog -sv '+' '.join('{'+tool_path(s)+'}'for s in sources),'vsim -c work.tb_iq_spi_radio_proxy','run -all','quit -code 0'])+'\n')
subprocess.run(tool_command([str(tool_exe('vsim')),'-c','-do',tool_path(script)],cwd=out),cwd=out,env=tool_env(),check=True)
log=(out/'transcript').read_text();assert 'PASS SPI radio proxy' in log

# Controller text limits are separate from fixed SPI proxy controls.
sources=[stage/'rtl'/n for n in ['iq_bridge_controller.sv','sync_fifo.sv']]+[stage/'sim/tb_iq_controller_text.sv']
script=out/'text.do';script.write_text('\n'.join(['onerror {quit -code 1}','vlog -sv '+' '.join('{'+tool_path(s)+'}'for s in sources),'vsim -c work.tb_iq_controller_text','run -all','quit -code 0'])+'\n')
subprocess.run(tool_command([str(tool_exe('vsim')),'-c','-do',tool_path(script)],cwd=out),cwd=out,env=tool_env(),check=True)
assert 'PASS controller text' in (out/'transcript').read_text()

# Exercise timeout inside a physical transaction: CS must return inactive.
sources=[stage/'rtl'/n for n in ['iq_spi_master.sv','iq_spi_capture_meter.sv','iq_spi_radio_proxy.sv']]+[stage/'sim/tb_iq_spi_abort.sv']
script=out/'abort.do';script.write_text('\n'.join(['onerror {quit -code 1}','vlog -sv '+' '.join('{'+tool_path(s)+'}'for s in sources),'vsim -c work.tb_iq_spi_abort','run -all','quit -code 0'])+'\n')
subprocess.run(tool_command([str(tool_exe('vsim')),'-c','-do',tool_path(script)],cwd=out),cwd=out,env=tool_env(),check=True)
assert 'PASS SPI timeout abort' in (out/'transcript').read_text()

# Real generated Quartus FIR II, connected through SPI proxy/controller/RAM.
import re,shutil,struct,hashlib,json
import numpy as np
from iq_bridge import HEADER,decode_header,decode_frame
from nios_fir import fixed_reference
ip=stage/'gen/vds/iq_bridge_system/ip/iq_bridge_system_fir_ii'
qip=ip/'iq_bridge_system_fir_ii.qip'
if not qip.exists():raise RuntimeError('Generate checkpoint07 before end-to-end vendor FIR simulation')
files=[(kind,ip/name)for kind,name in re.findall(r'-name (VHDL_FILE|VERILOG_FILE) \[file join \$::quartus\(qip_path\) "([^"]+)"\]',qip.read_text())]
for p in ip.glob('**/*_rm.hex'):shutil.copy2(p,out/p.name)
commands=['onerror {quit -force -code 1}','vlib fir_vendor']
for kind,p in files:commands.append(('vcom -2008'if kind=='VHDL_FILE'else'vlog')+' -work fir_vendor {'+tool_path(p)+'}')
sources=[stage/'rtl'/n for n in ['iq_fir_capture.sv','iq_capture_memory.sv','iq_radio_uarts.sv','uart_dynamic.sv']]+[stage/'sim/tb_iq_spi_fir_pipeline.sv']
signals=['clk','reset','spi_ready','radios/spi_proxy/ready_low_seen','spi_cs_n','spi_sck','spi_mosi','spi_miso','cap_write','cap_waddr','cap_wdata','cap_commit','fir_valid','fir_data','fir_result_valid','fir_result','host_start','host_out','uart_done','uart_profile']
paths=' '.join('/tb_iq_spi_fir_pipeline/'+s for s in signals)
commands+=['vlog -sv '+' '.join('{'+tool_path(p)+'}'for p in sources),'vsim -c -voptargs=+acc -wlf pipeline.wlf -t ps -L work -L fir_vendor -L altera_mf -L altera_lnsim -L tennm work.tb_iq_spi_fir_pipeline','log '+paths,'run -all','quit -force -code 0']
gui=[line.replace('vsim -c ','vsim ')for line in commands if line not in ('run -all','quit -force -code 0')]
(out/'pipeline_gui.do').write_text('\n'.join(gui+['view wave','add wave '+paths,'run -all','wave zoom full'])+'\n')
(out/'view.do').write_text('view wave\nadd wave '+paths.replace('/tb_iq_spi_fir_pipeline/','wave:/tb_iq_spi_fir_pipeline/')+'\nwave zoom full\n')
script=out/'pipeline.do';script.write_text('\n'.join(commands)+'\n')
subprocess.run(tool_command([str(tool_exe('vsim')),'-c','-do',tool_path(script)],cwd=out),cwd=out,env=tool_env(),check=True)
assert 'PASS integrated SPI to actual FIR II' in (out/'transcript').read_text()
wire=(out/'pipeline.bin').read_bytes();frames=[]
while wire:
 f=decode_header(wire[:64]);size=68+f.length;frames.append(decode_frame(wire[:size]));wire=wire[size:]
controls={f.job:f for f in frames if f.kind in (2,5)}
for job,error in ((10,128),(11,128),(12,32)):
 assert (controls[job].kind,controls[job].error)==(5,error),('bounded control reject',job)
for job in (9,10,11,12,13,14):
 assert (controls[job].rate,controls[job].frequency)==(16000000,2447000000),('fixed SPI metadata',job)
assert controls[13].kind==controls[14].kind==2
assert controls[15].rate==40000000 and controls[15].kind==2
assert controls[16].frequency==2417000000 and controls[16].kind==2
raw,filtered=[f for f in frames if f.kind in (1,6)]
assert {(f.source,f.payload) for f in frames if f.kind==3}>={(0,b'RFS2!'),(1,b'TX A!')}
assert raw.kind==1 and filtered.kind==6
expected=bytes((n*37+11)&255 for n in range(32760))
assert raw.payload==expected
assert (raw.source,raw.job,raw.samples,raw.rate,raw.frequency,raw.capture_us)==(2,0x12345678,16380,16000000,2447000000,0)
for field in ('source','job','samples','rate','frequency','first_tick','last_tick','capture_us'):
 assert getattr(raw,field)==getattr(filtered,field),field
assert filtered.aux>>32==raw.raw_crc and filtered.aux&0xffffffff==0x80010100
assert np.array_equal(filtered.iq(),fixed_reference(raw.iq(),[16384,8192,-4096]+[0]*13,True))
result=dict(status='PASS',checkpoint=7,hardware_access=False,processor_simulated=False,actual_generated_fir_ii=True,samples=16380,custom_coefficients=[16384,8192,-4096]+[0]*13,round_nearest=True,raw_crc=f'{raw.raw_crc:08x}',filtered_crc=f'{filtered.raw_crc:08x}',matching_capture_metadata=True,ci8_bit_exact=True,tests=['exact_proxy_text','busy_command_queue','fixed_profile_gates','corrupt_capture_no_partial_publish','synthetic_and_rf_mode_boundary','READY_timeout','delayed_READY_low_high','missing_READY_low_timeout_recovery','midtransaction_timeout_abort','controller_text_127_128_255_256','controller_text_real_2M_back_to_back','controller_text_four_slot_FIFO_order_overflow','controller_text_atomic_full_pop_push','source2_fixed_metadata_and_sample_gates','SPI_controller_actual_FIR_II_IQB1_pair'],source_sha256={str(p.relative_to(stage)):hashlib.sha256(p.read_bytes()).hexdigest()for p in stage.glob('rtl/*.sv')})
result['vendor_files_sha256']={str(p.relative_to(stage)):hashlib.sha256(p.read_bytes()).hexdigest()for kind,p in files}
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print('PASS checkpoint07 SPI ingress → actual FIR II → same-capture IQB1 pair, independent Python integer reference',flush=True)
