`timescale 1ns/1ps
module tb_iq_spi_capture_meter;
 logic clk=0;always #10 clk=~clk;
 logic reset=1,packet_start=0,byte_valid=0,packet_end=0;logic[7:0] byte_data=0;
 wire result_valid,result_synthetic;wire[31:0]result_sequence,commit_count,reject_count,result_samples;
 wire[63:0]result_power,result_ingress_cycles;wire[31:0]result_peak,result_clip_samples,result_clip_components;
 wire[7:0]last_error;wire[31:0]result_bytes,result_chunks;
 iq_spi_capture_meter dut(.*);
 logic[7:0] vectors[0:33791];
 logic[7:0] packet[0:1055];
 logic[63:0] expected_power,expected_cycles;
 logic[31:0] expected_peak,expected_clip,expected_component;
 integer last_reject=0;
 function automatic logic[31:0] crc_byte(input logic[31:0] v,input logic[7:0] b);
  logic[31:0] c;begin c=v^b;for(integer n=0;n<8;n++)c=(c>>1)^((c&1)?32'hedb88320:0);return c;end
 endfunction
 task automatic put32(input integer at,input logic[31:0] value);
  for(integer n=0;n<4;n++)packet[at+n]=8'(value>>(n*8));
 endtask
 task automatic header_crc;
  logic[31:0] c;begin c=~32'd0;for(integer n=0;n<28;n++)c=crc_byte(c,packet[n]);put32(28,~c);end
 endtask
 task automatic load(input integer chunk,input integer seq,input bit synthetic);
  begin
   for(integer n=0;n<1056;n++)packet[n]=vectors[chunk*1056+n];
   put32(8,32'(seq));packet[6][1]=synthetic;header_crc();
  end
 endtask
 task automatic send(input integer bytes,input bit finish_packet,input bit count_cycles);
  time began,ended;
  begin
   @(negedge clk);packet_start=1;@(posedge clk);began=$time;
   @(negedge clk);packet_start=0;
   for(integer n=0;n<bytes;n++)begin
    byte_valid=1;byte_data=n<1056?packet[n]:8'd0;@(negedge clk);byte_valid=0;@(negedge clk);
   end
   if(finish_packet)begin
    packet_end=1;@(posedge clk);ended=$time;
    @(negedge clk);packet_end=0;
    if(count_cycles)expected_cycles=expected_cycles+(ended-began)/20;
   end
   #1;
  end
 endtask
 task automatic rejected(input integer reason);
  begin
   if(result_valid || reject_count<=last_reject || last_error!=reason)
    $fatal(1,"rejection reason=%0d got%0d count%0d prior%0d valid%0b",reason,last_error,reject_count,last_reject,result_valid);
   last_reject=reject_count;
  end
 endtask
 task automatic good_capture(input integer seq);
  begin
   expected_cycles=0;
   for(integer chunk=0;chunk<32;chunk++)begin
    load(chunk,seq,1);send(1056,1,1);
    if(chunk<31 && result_valid)$fatal(1,"partial capture published");
   end
   if(!result_valid || !result_synthetic || result_sequence!=seq || result_samples!=16380 ||
      result_bytes!=32760 || result_chunks!=32 || result_power!=expected_power ||
      result_peak!=expected_peak || result_clip_samples!=expected_clip ||
      result_clip_components!=expected_component || result_ingress_cycles!=expected_cycles)
    $fatal(1,"meter mismatch sum=%0d/%0d samples%0d peak%0d clip%0d/%0d cycles%0d/%0d",result_power,expected_power,result_samples,result_peak,result_clip_samples,result_clip_components,result_ingress_cycles,expected_cycles);
  end
 endtask
 initial begin
  integer i,q,p;logic ci,cq;logic[31:0] crc;
  $readmemh("valid_capture.hex",vectors);
  expected_power=0;expected_peak=0;expected_clip=0;expected_component=0;
  for(integer n=0;n<16380;n++)begin
   i=((n*2*37+11)&255);if(i>127)i=i-256;
   q=(((n*2+1)*37+11)&255);if(q>127)q=q-256;
   p=i*i+q*q;expected_power+=p;if(p>expected_peak)expected_peak=p;
   ci=(i==-128 || i==127);cq=(q==-128 || q==127);
   expected_clip+=(ci||cq);expected_component+=integer'(ci)+integer'(cq);
  end
  repeat(5)@(negedge clk);reset=0;
  good_capture(10);if(commit_count!=1)$fatal(1,"first commit count");
  // Replayed whole captures cannot acquire a new commit number.
  load(0,10,1);send(1056,1,0);rejected(5);
  load(0,11,1);packet[8]^=1;send(1056,1,0);rejected(2);
  load(0,12,1);packet[55]^=1;send(1056,1,0);rejected(4);
  load(0,13,1);packet[0]^=1;header_crc();send(1056,1,0);rejected(3);
  load(0,13,1);packet[5]=1;header_crc();send(1056,1,0);rejected(3);
  load(0,13,1);packet[4]=2;header_crc();send(1056,1,0);rejected(3);
  load(1,14,1);send(1056,1,0);rejected(5);
  load(0,15,1);send(1056,1,0);load(2,15,1);send(1056,1,0);rejected(5);
  load(0,16,1);send(1056,1,0);load(1,17,1);send(1056,1,0);rejected(5);
  load(0,18,1);send(1056,1,0);load(1,18,0);send(1056,1,0);rejected(5);
  load(0,19,1);send(100,1,0);rejected(1);
  load(0,19,1);send(1057,1,0);rejected(1);
  load(0,20,1);send(1056,0,0);
  if(result_valid || commit_count!=1)$fatal(1,"no-end partial published");
  // New boundary drops unfinished transaction, then a fresh valid capture recovers.
  good_capture(21);
  if(commit_count!=2 || reject_count<10)$fatal(1,"recovery or counters");
  load(0,10,1);send(1056,1,0);rejected(5); // A,B,A backwards replay
  // Invalid padding in final chunk must reject instead of publishing old stats.
  for(integer n=0;n<32;n++)begin
   load(n,22,1);if(n==31)packet[1055]=1;send(1056,1,0);
  end
  rejected(1);if(commit_count!=2)$fatal(1,"bad final committed");
  // Both I and Q on rails: complex clipcount must differ from componentcount.
  expected_cycles=0;
  for(integer chunk=0;chunk<32;chunk++)begin
   load(chunk,23,1);
   for(integer n=32;n<1056;n++)packet[n]=0;
   if(chunk==0)begin
    packet[32]=128;packet[33]=128;packet[34]=127;packet[35]=127;
    packet[36]=128;packet[37]=127;packet[38]=127;packet[39]=128;
   end
   crc=~32'd0;
   for(integer n=0;n<(chunk==31?1016:1024);n++)crc=crc_byte(crc,packet[32+n]);
   put32(24,~crc);header_crc();send(1056,1,1);
  end
  if(!result_valid || result_power!=130052 || result_peak!=32768 || result_clip_samples!=4 ||
     result_clip_components!=8 || result_samples!=16380 || result_ingress_cycles!=expected_cycles || commit_count!=3)
   $fatal(1,"signed extreme/zero and componentclip reference mismatch");
  // Sequence wrap forwards is valid; backwards over wrap is rejected.
  @(negedge clk);reset=1;repeat(3)@(negedge clk);reset=0;last_reject=0;
  good_capture(32'hffffffff);good_capture(0);
  if(commit_count!=2)$fatal(1,"sequence wrap did not commit");
  load(0,32'hffffffff,1);send(1056,1,0);rejected(5);
  $display("PASS SPI capture meter: CRC/header/order/drop/mode/replay/truncation/no-end/recovery; atomic16380sample integerstats + ingress cycles");$finish;
 end
 initial begin #100000000;$fatal(1,"meter watchdog");end
endmodule
