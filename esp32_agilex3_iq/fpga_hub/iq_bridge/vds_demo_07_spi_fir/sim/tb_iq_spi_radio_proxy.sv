`timescale 1ns/1ps
module tb_iq_spi_radio_proxy;
 logic clk=0;always #10 clk=~clk;
 logic reset=1,tx_start=0;logic[7:0]tx_data;wire tx_busy,tx_done,rx_valid,rx_error;
 wire[7:0]rx_data;logic spi_miso=0,spi_ready=1;wire spi_mosi,spi_sck,spi_cs_n;
 iq_spi_radio_proxy #(.READY_TIMEOUT(10000),.CAPTURE_TIMEOUT(15000000))dut(.*);
 logic[7:0]synthetic[0:33791],rf[0:33791],output_bytes[0:40000];
 integer bits=0,packets=0,chunk=0,received=0;bit source_rf=0,dma_armed=1,hang_rearm=0;logic[7:0]command_byte;
 // MODE1 slave: packet being clocked was armed before its MOSI request.
 always @(negedge spi_cs_n)begin
  if(!dma_armed || !spi_ready)$fatal(1,"early CS on stale READY before DMA rearmed");
  bits=0;packets++;command_byte=0;
 end
 function automatic byte response(input integer index);
  byte v;begin v=source_rf?rf[chunk*1056+index]:synthetic[chunk*1056+index];
   if(packets==2 && index==55)v^=1;return v;end
 endfunction
 always @(posedge spi_sck)if(!spi_cs_n)spi_miso=(response(bits/8)>>(7-bits%8))&1;
 always @(negedge spi_sck)if(!spi_cs_n)begin
  if(bits<8)command_byte={command_byte[6:0],spi_mosi};else if(spi_mosi)$fatal(1,"nonzero padding MOSI");bits++;
 end
 always @(posedge spi_cs_n)if(packets)begin
  if(bits!=8448)$fatal(1,"packet length");
  if(packets==33 && (received!=0 || dut.commits!=0))$fatal(1,"corrupt partial capture leaked data");
  if(command_byte!=8'h54 && command_byte!=8'h52)$fatal(1,"selector command");
  if((command_byte==8'h52)!=source_rf)begin source_rf=command_byte==8'h52;chunk=0;end
  else chunk=(chunk+1)%32;
  dma_armed=0;
  // Model delayed ESP32 post_trans ISR: old READY remains HIGH for4us.
  if(!hang_rearm)fork begin
   #4000;spi_ready=0;#6000;dma_armed=1;spi_ready=1;
  end join_none
 end
 always @(posedge clk)if(rx_valid)begin output_bytes[received]=rx_data;received++;end
 task automatic send(input string s);
  begin for(integer n=0;n<s.len();n++)begin
   wait(!tx_busy);@(negedge clk);tx_data=s[n];tx_start=1;@(negedge clk);tx_start=0;wait(tx_done);@(negedge clk);
  end end
 endtask
 task automatic expect_line(input string s);
  begin wait(received>=s.len());#100;
   if(received!=s.len())$fatal(1,"line length %0d != %0d",received,s.len());
   for(integer n=0;n<s.len();n++)if(output_bytes[n]!==s[n])$fatal(1,"text[%0d] got%h expected%h",n,output_bytes[n],s[n]);
   received=0;
  end
 endtask
 task automatic capture(input bit want_rf);
  integer header_length;logic[31:0]crc;string expected;
  begin
   send("CAP16 16380 6\n");wait(received==32782);#100;
   expected=want_rf?"DATA 16380 5b2da3a8 0\n":"DATA 16380 a43e1701 0\n";
   // CRC header independently produced by Python fixture generator.
   for(integer n=0;n<22;n++)if(output_bytes[n]!==expected[n])$fatal(1,"capture header[%0d] got%h expected%h",n,output_bytes[n],expected[n]);
   for(integer n=0;n<32760;n++)if(output_bytes[n+22]!==8'((n*37+(want_rf?73:11))&255))$fatal(1,"CI8[%0d]",n);
   if(!dut.observed_valid || dut.observed_synthetic==want_rf || dut.observed_samples!=16380)$fatal(1,"observed metadata");
   received=0;
  end
 endtask
 initial begin
  $readmemh("synthetic.hex",synthetic);$readmemh("rf.hex",rf);
  repeat(4)@(negedge clk);reset=0;
  send("MODE?\n");expect_line("RF_MODE,SDR,baud=2000000,transport=SPI\n");
  send("INFO\n");expect_line("ESP32SDR SPI_PROXY source2 fixedfreq2447 rate16000000\n");
  // Back-to-back commands exercise busy: SYNC may queue while RELEASE replies.
  send("RELEASE\nSYNC test\n");wait(received==21);#100;
  for(integer n=0;n<21;n++)if(output_bytes[n]!==8'("OK RELEASE\nSYNC test\n" >> ((20-n)*8)))$fatal(1,"back-to-back reply");received=0;
  send("FREQ 2447\n");expect_line("OK\n");send("FREQ 2417\n");expect_line("ERR unsupported_spi_control\n");
  send("CAP16 1000 6\n");expect_line("ERR unsupported_spi_control\n");
  // Missing post_trans low must timeout instead of reusing the old high.
  hang_rearm=1;send("CAP16 16380 6\n");expect_line("ERR spi_ready_timeout\n");
  if(packets!=1 || dut.commits || dut.observed_valid)$fatal(1,"missing-low timeout published/reused DMA");
  hang_rearm=0;spi_ready=0;chunk=0;#10000;dma_armed=1;spi_ready=1;
  capture(0);
  send("SPI_MODE RF\n");expect_line("OK SPI_MODE RF\n");capture(1);
  send("SPI?\n");wait(received==76);#100;
  if(output_bytes[0]!="S" || output_bytes[75]!=10 || dut.commits!=2)$fatal(1,"SPI status");received=0;
  spi_ready=0;send("CAP16 16380 6\n");expect_line("ERR spi_ready_timeout\n");
  $display("PASS SPI radio proxy: exact text, busy command queue, fixed-control gates, whole synthetic/RF CI8+CRC, corrupt capture rejected+retried, fresh boundary, status, delayed READY low/high, missing-low timeout+recovery");$finish;
 end
 initial begin #500000000;$fatal(1,"proxy watchdog state%0d bytes%0d packets%0d commits%0d rejects%0d",dut.state,received,packets,dut.commits,dut.rejects);end
endmodule
