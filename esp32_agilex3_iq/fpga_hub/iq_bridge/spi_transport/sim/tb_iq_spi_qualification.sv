`timescale 1ns/1ps
module tb_iq_spi_qualification;
 logic CLOCK1_50=0;always #10 CLOCK1_50=~CLOCK1_50;
 logic HOST_RX=1,SPI_MISO=0,SPI_READY=0;
 wire HOST_TX,SPI_MOSI,SPI_SCK,SPI_CS_N;
 iq_spi_qualification_top dut(.*);
 integer bits=0,packets=0,received=0;logic id_phase=1;
 function automatic byte fixture(input integer n);fixture=8'(n)^8'ha5;endfunction
 always @(negedge SPI_CS_N)begin bits=0;packets=packets+1;end
 always @(posedge SPI_SCK)if(!SPI_CS_N)SPI_MISO=(fixture(bits/8)>>(7-bits%8))&1;
 always @(negedge SPI_SCK)if(!SPI_CS_N)begin
  if(SPI_MOSI!==(bits<8?((8'(packets==1?8'h52:8'h54)>>(7-bits))&1):0))
   $fatal(1,"bounded T/R MOSI command differs atbit%0d",bits);
  bits=bits+1;
 end
 always @(posedge SPI_CS_N)if(packets && bits!=1056*8)$fatal(1,"wrong fixed packet length %0d",bits);
 logic valid,framing;logic[7:0] data;
 uart_fractional_rx monitor(.clk(CLOCK1_50),.reset(dut.reset),.rx(HOST_TX),
  .baud(32'd2000000),.valid(valid),.data(data),.framing_error(framing));
 always @(posedge CLOCK1_50)begin
  if(framing)$fatal(1,"UART framing");
  if(valid)begin
   if(data!==(id_phase?8'(64'h5350495130303031 >> (56-received*8)):fixture(received)))$fatal(1,"packet byte %0d got%h expected%h",received,data,fixture(received));
   received=received+1;
  end
 end
 task automatic command(input byte value);
  begin
   HOST_RX=0;#500;
   for(integer b=0;b<8;b++)begin HOST_RX=(value>>b)&1;#500;end
   HOST_RX=1;#500;
  end
 endtask
 initial begin
  wait(!dut.reset);#1000;command(8'h49);wait(received==8);#10000;
  if(packets)$fatal(1,"identity query accessed SPI");
  id_phase=0;received=0;command(8'h52);#10000;
  if(!SPI_CS_N || packets)$fatal(1,"transaction began without READY");
  SPI_READY=1;wait(received==1056);#10000;
  if(packets!=1 || !SPI_CS_N)$fatal(1,"packet transaction count");
  received=0;command(8'h54);wait(received==1056);#10000;
  if(packets!=2 || !SPI_CS_N)$fatal(1,"second packet transaction count");
  $display("PASS SPI board top: READY wait, 1056 CI8 bytes at5MHz, RAM, UART2M exact");$finish;
 end
 initial begin #20000000;$fatal(1,"board watchdog");end
endmodule
