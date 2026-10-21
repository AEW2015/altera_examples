`timescale 1ns/1ps
module tb_iq_spi_meter_top;
 logic CLOCK1_50=0;always #10 CLOCK1_50=~CLOCK1_50;
 logic HOST_RX=1,SPI_MISO=0,SPI_READY=1;wire HOST_TX,SPI_MOSI,SPI_SCK,SPI_CS_N;
 iq_spi_meter_top dut(.*);
 logic[7:0] vectors[0:33791],summary[0:63];
 integer bits=0,packets=0,received=0,phase=0;
 time cs_began;
 logic[63:0] expected_cycles=0,expected_power=0;
 integer expected_peak=0,expected_clip=0,expected_components=0;
 function automatic logic[31:0] crc_byte(input logic[31:0] v,input logic[7:0] b);
  logic[31:0] c;begin c=v^b;for(integer n=0;n<8;n++)c=(c>>1)^((c&1)?32'hedb88320:0);return c;end
 endfunction
 function automatic byte response(input integer n);
  byte value;begin value=vectors[((packets-1)%32)*1056+n];
   if(packets==33 && n==55)value^=1;
   return value;end
 endfunction
 function automatic logic[31:0] u32(input integer at);
  return {summary[at+3],summary[at+2],summary[at+1],summary[at]};
 endfunction
 function automatic logic[63:0] u64(input integer at);
  return {u32(at+4),u32(at)};
 endfunction
 always @(negedge SPI_CS_N)begin bits=0;packets++;cs_began=$time;end
 always @(posedge SPI_SCK)if(!SPI_CS_N)SPI_MISO=(response(bits/8)>>(7-bits%8))&1;
 always @(negedge SPI_SCK)if(!SPI_CS_N)begin
  if(SPI_MOSI!==(bits<8?((8'h54>>(7-bits))&1):0))$fatal(1,"MOSI T command");bits++;
 end
 always @(posedge SPI_CS_N)if(packets)begin
  if(bits!=8448)$fatal(1,"fixedSPIpacketlength");
  if(packets<=32)expected_cycles+=($time-cs_began)/20+1;
 end
 logic valid,framing;logic[7:0] data;
 uart_fractional_rx monitor(.clk(CLOCK1_50),.reset(dut.reset),.rx(HOST_TX),
  .baud(32'd2000000),.valid(valid),.data(data),.framing_error(framing));
 always @(posedge CLOCK1_50)begin
  if(framing)$fatal(1,"UART framing");
  if(valid)begin
   if(phase==0 && data!==8'(64'h5350495130303032>>(56-received*8)))$fatal(1,"SPIQ0002 identity");
   if(phase==1 && data!==response(received))$fatal(1,"rawUARTbyte%0d",received);
   if(phase==2)summary[received]=data;
   received++;
  end
 end
 task automatic command(input byte value);
  begin HOST_RX=0;#500;for(integer b=0;b<8;b++)begin HOST_RX=(value>>b)&1;#500;end HOST_RX=1;#500;end
 endtask
 task automatic get_summary(input bit good);
  logic[31:0] crc;begin
   phase=2;received=0;command(8'h4d);wait(received==64);#10000;
   crc=~32'd0;for(integer n=0;n<60;n++)crc=crc_byte(crc,summary[n]);
   if(u32(60)!=(~crc) || u32(0)!=32'h314d5053 || summary[4]!=1)$fatal(1,"summary CRC/header");
   if(summary[5]!=(good?3:2) || summary[6]!=(good?0:4) || u32(12)!=1 || u32(16)!=(good?0:1))$fatal(1,"summary valid/error/counters");
   if(u32(8)!=0 || u32(20)!=16380 || u64(24)!=expected_power || u32(32)!=expected_peak ||
      u32(36)!=expected_clip || u32(40)!=expected_components || u64(44)!=expected_cycles ||
      u32(52)!=32760 || u32(56)!=32)$fatal(1,"summary stats/cycles got%0d expected%0d",u64(44),expected_cycles);
  end
 endtask
 initial begin
  integer i,q,p;logic ci,cq;
  $readmemh("valid_capture.hex",vectors);
  for(integer n=0;n<16380;n++)begin
   i=((n*2*37+11)&255);if(i>127)i-=256;
   q=(((n*2+1)*37+11)&255);if(q>127)q-=256;
   p=i*i+q*q;expected_power+=p;if(p>expected_peak)expected_peak=p;
   ci=(i==-128||i==127);cq=(q==-128||q==127);expected_clip+=(ci||cq);expected_components+=integer'(ci)+integer'(cq);
  end
  wait(!dut.reset);#1000;command(8'h49);wait(received==8);#10000;
  for(integer n=0;n<32;n++)begin phase=1;received=0;command(8'h54);wait(received==1056);#10000;end
  get_summary(1);
  // A corrupt next packet invalidates the view while retaining the old commit number.
  phase=1;received=0;command(8'h54);wait(received==1056);#10000;get_summary(0);
  if(packets!=33)$fatal(1,"M query accessed SPI unexpectedly");
  $display("PASS SPI meter board: SPIQ0002,32validchunks,atomicintegerstats,actualingresscycles,CRC-protectedM,corruptpacketinvalidatesview");$finish;
 end
 initial begin #500000000;$fatal(1,"meter board watchdog");end
endmodule
