`timescale 1ns/1ps
module spi_case #(parameter MODE=0)(output logic done=0);
 logic clk=0,reset=1;always #10 clk=~clk;
 logic[7:0] tx_data=0,rx_data;logic tx_valid=0,tx_last=0,tx_ready;
 logic rx_valid,rx_ready=0,miso=0,mosi,sck,cs_n,limit_error;
 iq_spi_master #(.MODE(MODE),.HALF_CYCLES(3),.MAX_BYTES(3)) dut(.*);
 localparam bit CPOL=(MODE>=2), CPHA=(MODE%2)!=0;
 integer edge_n=0, samples=0;logic[7:0] seen=0;
 always @(negedge cs_n) begin edge_n=0;samples=0;seen=0;miso=CPHA?0:1;end
 always @(sck) if(!reset && !cs_n) begin
  if(sck!=CPOL) begin // leading
   if(CPHA) miso=(8'hd3>>(7-(edge_n/2)))&1;
   else begin seen={seen[6:0],mosi};samples=samples+1;end
  end else begin // trailing
   if(CPHA) begin seen={seen[6:0],mosi};samples=samples+1;end
   else if((edge_n/2)<7) miso=(8'hd3>>(6-(edge_n/2)))&1;
  end
  edge_n=edge_n+1;
 end
 task automatic transfer(input byte value,input bit final_byte,input bit frame_start);
  begin
   if(!frame_start) begin edge_n=0;samples=0;seen=0;miso=CPHA?0:1;end
   @(negedge clk);tx_data=value;tx_last=final_byte;tx_valid=1;
   do @(posedge clk);while(!tx_ready);
   @(negedge clk);tx_valid=0;
   wait(rx_valid);#1;
   if(rx_data!==8'hd3 || seen!==value || samples!=8)
    $fatal(1,"mode%0d got rx=%h tx=%h samples=%0d",MODE,rx_data,seen,samples);
   // RX backpressure must preserve data, CS and idle clock, refusing next TX.
   repeat(7) begin @(posedge clk);#1;if(rx_data!==8'hd3 || tx_ready || cs_n || sck!==CPOL)$fatal(1,"stall");end
   @(negedge clk);rx_ready=1;@(negedge clk);rx_ready=0;
   if(cs_n!==(final_byte || limit_error))$fatal(1,"CS frame boundary");
  end
 endtask
 initial begin
  repeat(5)@(negedge clk);reset=0;
  transfer(8'h96,0,1);transfer(8'h01,1,0);
  transfer(8'h80,0,1);transfer(8'h02,0,0);transfer(8'hff,0,0);
  if(!limit_error || !cs_n)$fatal(1,"missing bounded frame termination");
  // Reset in the middle of a byte must release CS and clear status.
  @(negedge clk);tx_valid=1;tx_data=8'hab;
  repeat(5)@(negedge clk);reset=1;tx_valid=0;
  repeat(2)@(negedge clk);if(!cs_n || sck!==CPOL || rx_valid || limit_error)$fatal(1,"reset abort");
  reset=0;transfer(8'h53,1,1);done=1;
 end
endmodule
module tb_iq_spi_master;
 wire[3:0] done;
 for(genvar m=0;m<4;m++)begin:cases spi_case #(.MODE(m)) test(done[m]);end
 initial begin wait(&done);$display("PASS SPI modes0-3 MSB-first, CS, byte backpressure, limit, reset");$finish;end
 initial begin #1000000;$fatal(1,"watchdog");end
endmodule
