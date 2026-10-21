`timescale 1ns/1ps
module tb_iq_controller_text;
 logic clk=0;always #10 clk=~clk;logic reset=1;
 logic[2:0]rv=0;logic[23:0]radio_rx_data=0;wire host_start;wire[7:0]host_out;logic host_done=0;
 wire[31:0]drops;logic[7:0]wire_bytes[0:1023];integer received=0;
 iq_bridge_controller dut(.clk(clk),.reset(reset),.host_valid(1'b0),.host_byte(8'd0),.host_frame_error(1'b0),.host_busy(1'b0),.host_done(host_done),.host_start(host_start),.host_out(host_out),
 .rv(rv),.radio_rx_data(radio_rx_data),.re(3'd0),.tbusy(3'd0),.tdone(3'd0),.mem_q(16'd0),
 .uart_enable(1'b0),.uart_available(1'b1),.uart_done(1'b0),.uart_fault(1'b0),.uart_q(16'd0),.uart_crc(32'd0),.uart_profile(32'd0),.mon_text_drops(drops));
 always @(posedge clk)begin host_done<=host_start;if(host_start)begin wire_bytes[received]=host_out;received++;end end
 function automatic logic[31:0]crc_byte(input logic[31:0]crc,input logic[7:0]b);
  logic[31:0]c;begin c=crc^b;for(integer n=0;n<8;n++)c=(c>>1)^(c[0]?32'hedb88320:0);return c;end
 endfunction
 task automatic feed(input byte value);begin @(negedge clk);rv=2;radio_rx_data={8'd0,value,8'd0};@(negedge clk);rv=0;end endtask
 task automatic line(input integer count,input bit accepted);
  logic[31:0]crc;begin
   received=0;for(integer n=0;n<count;n++)feed(8'(n%26+65));feed(10);
   if(accepted)begin wait(received==count+68);repeat(20)@(negedge clk);
    if(received!=count+68 || wire_bytes[5]!=3 || wire_bytes[6]!=1 || {wire_bytes[39],wire_bytes[38],wire_bytes[37],wire_bytes[36]}!=count)$fatal(1,"text envelope %0d",count);
    for(integer n=0;n<count;n++)if(wire_bytes[64+n]!==8'(n%26+65))$fatal(1,"text byte %0d/%0d",n,count);
    crc=~32'd0;for(integer n=0;n<count+64;n++)crc=crc_byte(crc,wire_bytes[n]);
    if({wire_bytes[count+67],wire_bytes[count+66],wire_bytes[count+65],wire_bytes[count+64]}!==~crc)$fatal(1,"text CRC");
   end else begin repeat(2000)@(negedge clk);if(received!=0 || drops!=1)$fatal(1,"overflow must drop bounded line and count it");end
  end
 endtask
 initial begin repeat(8)@(negedge clk);reset=0;
  line(127,1);line(128,1);line(255,1);line(256,0);line(5,1);
  $display("PASS controller text:127/128/255 exact CRC envelopes,256 dropped/counted,next line recovered");$finish;
 end
 initial begin #10000000;$fatal(1,"text watchdog");end
endmodule
