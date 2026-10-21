`timescale 1ns/1ps
module tb_iq_preamble;
 logic clk=0;always #10 clk=~clk;logic reset=1,bus_reset=0;
 logic cap_write=0,cap_commit=0,cap_bank=0;logic[14:0]cap_waddr=0,cap_samples=0;logic[15:0]cap_wdata=0;
 logic[31:0]cap_job=77,cap_crc=0,cap_rate=16000000,cap_frequency=32'd2447000000;logic[1:0]cap_source=0;
 logic[5:0]address=0;logic rd=0,wr=0;logic[31:0]wd=0;logic[3:0]be=15;wire[31:0]q;wire waitreq;
 iq_preamble dut(.clk(clk),.reset(reset),.bus_reset(bus_reset),.cap_write(cap_write),.cap_commit(cap_commit),.cap_bank(cap_bank),.cap_waddr(cap_waddr),.cap_wdata(cap_wdata),.cap_samples(cap_samples),.cap_job(cap_job),.cap_crc(cap_crc),.cap_rate(cap_rate),.cap_frequency(cap_frequency),.cap_source(cap_source),.avs_address(address),.avs_read(rd),.avs_write(wr),.avs_writedata(wd),.avs_byteenable(be),.avs_readdata(q),.avs_waitrequest(waitreq));
 logic[15:0]iq[0:16383],scores[0:16383];logic[31:0]summary[0:15];
 integer n,sps,count,step,saved_n;string dir;logic[31:0]v,crc;
 function automatic[31:0]cb(input[31:0]c0,input[7:0]b);logic[31:0]c;begin c=c0^b;for(integer j=0;j<8;j++)c=(c>>1)^(c[0]?32'hedb88320:0);return c;end endfunction
 task automatic write(input integer a,input logic[31:0]d);begin @(negedge clk);address=6'(a);wd=d;wr=1;@(negedge clk);wr=0;end endtask
 task automatic read(input integer a,output logic[31:0]d);begin
  @(negedge clk);address=6'(a);rd=1;#1;
  while(waitreq)@(negedge clk);
  @(posedge clk);#1;d=q;@(negedge clk);rd=0;
 end endtask
 task automatic expect_reg(input integer a,input logic[31:0]d);logic[31:0]actual;begin read(a,actual);if(actual!==d)$fatal(1,"reg%0d expected%h got%h",a,d,actual);end endtask
 task automatic configure;begin write(1,1);write(2,n);write(3,sps);write(4,step);write(5,24576);write(6,7936);end endtask
 task automatic hostload;begin
  write(1,2);crc=32'hffffffff;
  for(integer k=0;k<n;k++)begin write(8,{16'd0,iq[k]});crc=cb(cb(crc,iq[k][7:0]),iq[k][15:8]);end
  write(1,3);expect_reg(16,~crc);expect_reg(27,n);expect_reg(18,3);expect_reg(17,0);expect_reg(19,16000000);expect_reg(20,0);
  read(1,v);if(!v[1]||v[4])$fatal(1,"host load not ready");
  write(7,0);read(8,v);if(v[15:0]!==iq[0])$fatal(1,"sync CI8 read");
 end endtask
 task automatic scan;begin
  write(1,4);wait(dut.done);read(1,v);if(v[0]||!v[2]||v[4]||v[5]!==summary[7][0])$fatal(1,"final status%h",v);
  expect_reg(10,summary[0]);expect_reg(11,summary[1]);expect_reg(14,count);expect_reg(23,summary[2]);expect_reg(26,summary[3]);expect_reg(24,summary[4]);expect_reg(25,summary[5]);
  for(integer k=0;k<count;k++)begin write(12,k);read(13,v);if(v!=={16'd0,scores[k]})$fatal(1,"trace%0d expected%h got%h",k,scores[k],v);end
 end endtask
 task automatic physical(input integer fault);begin
  write(1,5);cap_source=1;cap_commit=1;@(negedge clk);cap_commit=0;repeat(3)@(negedge clk);
  if(!dut.armed||dut.ready)$fatal(1,"wrong source changed arm");
  cap_source=0;cap_bank=1;crc=32'hffffffff;
  for(integer k=0;k<n-(fault==3?1:0);k++)begin @(negedge clk);cap_write=1;cap_waddr={1'b1,14'(k)};cap_wdata=iq[k];crc=cb(cb(crc,iq[k][7:0]),iq[k][15:8]);end
  @(negedge clk);cap_write=0;cap_samples=15'(n);cap_crc=(~crc)^(fault==1?1:0);cap_bank=fault==2?0:1;cap_commit=1;
  @(negedge clk);cap_commit=0;repeat(4)@(negedge clk);
  if(fault!=0)begin if(dut.ready||dut.armed||dut.errors==0)$fatal(1,"badCRC/bank/count accepted fault%0d",fault);end
  else begin expect_reg(16,~crc);expect_reg(17,77);expect_reg(18,0);expect_reg(19,16000000);expect_reg(20,32'd2447000000);if(!dut.ready)$fatal(1,"physical valid capture rejected");end
 end endtask
 initial begin
  if(!$value$plusargs("DIR=%s",dir))$fatal(1,"DIR missing");
  if(!$value$plusargs("N=%d",n))n=5120;
  if(!$value$plusargs("SPS=%d",sps))sps=128;
  if(!$value$plusargs("COUNT=%d",count))count=72;
  if(!$value$plusargs("STEP=%d",step))step=16;
  $readmemh({dir,"/iq.hex"},iq,0,n-1);$readmemh({dir,"/scores.hex"},scores,0,count-1);$readmemh({dir,"/summary.hex"},summary,0,7);
  repeat(5)@(negedge clk);reset=0;
  expect_reg(0,32'h50520801);expect_reg(21,16);expect_reg(22,1);
  write(1,4);if(dut.ready||dut.errors==0)$fatal(1,"run without ready accepted");
  configure();write(3,127);expect_reg(3,sps);if(dut.errors==0)$fatal(1,"bad SPS accepted");
  configure();write(4,0);expect_reg(4,step);write(4,17);expect_reg(4,step);write(5,32769);expect_reg(5,24576);
  configure();write(1,2);write(7,1);write(8,123);if(dut.written!=0||dut.errors==0||dut.ready)$fatal(1,"nonsequential load accepted");write(1,3);if(dut.ready)$fatal(1,"incomplete load ready");
  configure();write(2,0);expect_reg(2,n);write(2,16385);expect_reg(2,n);
  configure();be=3;write(2,n+1);be=15;expect_reg(2,n);if(dut.errors==0)$fatal(1,"partial CSR write accepted");
  configure();write(1,2);write(7,16384);write(8,123);if(dut.written!=0||dut.ready||dut.errors==0)$fatal(1,"host memory overflow accepted");
  saved_n=n;n=32;configure();hostload();write(1,4);if(dut.busy||dut.done||dut.errors==0)$fatal(1,"undersized training RUN accepted");n=saved_n;
  configure();hostload();scan();
  // Busy config writes cannot change the immutable run configuration.
  write(1,4);write(3,129);expect_reg(3,sps);if(dut.errors==0)$fatal(1,"busy config not rejected");write(1,6);if(dut.busy||!dut.ready)$fatal(1,"cancel preserve failed");
  configure();physical(1);configure();physical(2);configure();physical(3);configure();physical(0);scan();
  configure();write(1,5);cap_source=0;@(negedge clk);cap_write=1;cap_waddr=1;cap_wdata=0;@(negedge clk);cap_write=0;repeat(2)@(negedge clk);if(dut.armed||dut.ready||dut.errors==0)$fatal(1,"noncontiguous physical accepted");
  write(1,1);write(1,99);if(dut.ready||dut.errors==0)$fatal(1,"unknown command");
  write(1,1);write(7,0);@(negedge clk);address=8;rd=1;#1;if(!waitreq)$fatal(1,"synchronous RAM read failed to stall");
  @(negedge clk);bus_reset=1;@(negedge clk);rd=0;bus_reset=0;repeat(3)@(negedge clk);expect_reg(1,0);expect_reg(2,16380);
  $display("PASS preamble fixture %s: complete trace+best integer reference, host/physical CRC, replay provenance, bounds/config lock, wrong-source/bank/count/noncontiguous/CRC rejection, cancel/reset, synchronous CSR reads",dir);$finish;
 end
 initial begin #200000000;$fatal(1,"watchdog");end
endmodule
