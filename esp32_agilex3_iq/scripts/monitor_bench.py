#!/usr/bin/env python3
"""Counter window boundaries and coherent CSR snapshot, independent event sums."""
from pathlib import Path
import subprocess,json,hashlib
HERE=Path(__file__).resolve().parents[1]
patterns=[sum(int((i*7+j*3)%11 < j%4+1)<<j for j in range(16)) for i in range(113)]
totals=[sum((v>>j)&1 for v in patterns) for j in range(16)]
window=[sum((v>>j)&1 for v in patterns[100:110]) for j in range(16)]
expected={4:11,5:113,6:0,7:0x25,8:0x11,9:0x22,10:0x33,11:0x44}
for i in range(16):
 w=12+i if i<13 else 51+i-13
 low=25+2*i if i<13 else 54+2*(i-13)
 expected[w]=window[i];expected[low]=totals[i];expected[low+1]=0
expected[60]=16;expected[61]=1
assertions='\n'.join(f'@(negedge clk);addr=6\'d{address};#1;if(q!==32\'h{value:08x})$fatal(1,"CSR {address}: %h",q);' for address,value in expected.items())
bench='''`timescale 1ns/1ps
module tb_monitor;
integer integer_file;
logic clk=0;always #10 clk=~clk;
logic reset=1,bus_reset=0;logic[15:0] ev=0;logic[5:0] addr=0;logic rd=0,wr=0;wire[31:0]q;wire waitreq;
iq_transfer_monitor #(.CLOCK_HZ(10)) dut(.clk(clk),.reset(reset),.bus_reset(bus_reset),.mon_radio_byte(ev[2:0]),.mon_radio_tx(ev[15:13]),.mon_iq_byte(ev[5:3]),.mon_capture_ok(ev[8:6]),.mon_host_rx(ev[9]),.mon_host_tx(ev[10]),.mon_host_iq(ev[11]),.mon_host_capture(ev[12]),.mon_command_errors(32'h11),.mon_radio_errors(32'h22),.mon_capture_errors(32'h33),.mon_text_drops(32'h44),.mon_state(32'h25),.avs_address(addr),.avs_read(rd),.avs_write(wr),.avs_writedata(32'd1),.avs_byteenable(4'hf),.avs_readdata(q),.avs_waitrequest(waitreq));
initial begin
 repeat(3)@(negedge clk);reset=0;
 for(integer i=0;i<113;i=i+1)begin
  bus_reset=(i>=20 && i<40);
  for(integer j=0;j<16;j=j+1)ev[j]=((i*7+j*3)%11 < j%4+1);
  @(posedge clk);#1;@(negedge clk);
 end
 ev=0;addr=3;wr=1;@(posedge clk);#1;@(negedge clk);wr=0;rd=1;
'''+assertions+'''
 if(waitreq!==0)$fatal(1,"Unexpected waitrequest");
 addr=0;#1;if(q!==32'h49514d31)$fatal(1,"ID");
 addr=2;#1;if(q!==10)$fatal(1,"Clock");
 integer_file=$fopen("monitor.csv","w");addr=12;#1;$fwrite(integer_file,"window,%0d\\n",q);addr=25;#1;$fwrite(integer_file,"total,%0d\\n",q);$fclose(integer_file);
 $display("PASS monitor CSR snapshot, boundary-inclusive windows, all 16 event counters");$finish;
end
endmodule
'''
