`timescale 1ns/1ps
module tb_iq_controller_text;
 logic clk=0;always #10 clk=~clk;logic reset=1;
 logic[2:0]rv=0;logic[23:0]radio_rx_data=0;wire host_start;wire[7:0]host_out;logic host_done=0;logic host_busy=0,stall=0;integer baud_cycles=1,remaining=0;
 wire[31:0]drops;logic[7:0]wire_bytes[0:8191];integer received=0;
 iq_bridge_controller dut(.clk(clk),.reset(reset),.host_valid(1'b0),.host_byte(8'd0),.host_frame_error(1'b0),.host_busy(host_busy|stall),.host_done(host_done),.host_start(host_start),.host_out(host_out),
 .rv(rv),.radio_rx_data(radio_rx_data),.re(3'd0),.tbusy(3'd0),.tdone(3'd0),.mem_q(16'd0),
 .uart_enable(1'b0),.uart_available(1'b1),.uart_done(1'b0),.uart_fault(1'b0),.uart_q(16'd0),.uart_crc(32'd0),.uart_profile(32'd0),.mon_text_drops(drops));
 always @(posedge clk)begin
  host_done<=0;
  if(host_start)begin wire_bytes[received]=host_out;received++;remaining=baud_cycles;host_busy<=1;end
  else if(remaining>0)begin remaining=remaining-1;if(remaining==0)begin host_done<=1;host_busy<=0;end end
 end
 function automatic logic[31:0]crc_byte(input logic[31:0]crc,input logic[7:0]b);
  logic[31:0]c;begin c=crc^b;for(integer n=0;n<8;n++)c=(c>>1)^(c[0]?32'hedb88320:0);return c;end
 endfunction
 task automatic feed(input byte value);begin @(negedge clk);rv=2;radio_rx_data={8'd0,value,8'd0};@(negedge clk);rv=0;end endtask
 task automatic check_frame(input integer start,input integer count,input byte seed);
  logic[31:0]crc;begin
   if(wire_bytes[start+5]!=3 || wire_bytes[start+6]!=1 || {wire_bytes[start+39],wire_bytes[start+38],wire_bytes[start+37],wire_bytes[start+36]}!=count)$fatal(1,"queue envelope");
   for(integer n=0;n<count;n++)if(wire_bytes[start+64+n]!==8'(seed+n%26))$fatal(1,"queue payload start=%0d byte=%0d",start,n);
   crc=~32'd0;for(integer n=0;n<count+64;n++)crc=crc_byte(crc,wire_bytes[start+n]);
   if({wire_bytes[start+count+67],wire_bytes[start+count+66],wire_bytes[start+count+65],wire_bytes[start+count+64]}!==~crc)$fatal(1,"queue CRC");
  end
 endtask
 task automatic send_line(input integer count,input byte seed,input integer spacing);
  begin for(integer n=0;n<count;n++)begin feed(8'(seed+n%26));repeat(spacing)@(negedge clk);end feed(10);end
 endtask
 task automatic drained;begin wait(dut.output_state==0 && dut.text_pending==0 && !host_busy);repeat(4)@(negedge clk);end endtask
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
  drained();received=0;baud_cycles=250;
  // Radio and host both2Mbaud: the second status line completes while the
  // first IQB1 envelope is still exporting. Neither line may be discarded.
  send_line(128,65,248);send_line(60,66,248);drained();
  if(received!=128+60+136 || drops!=1)$fatal(1,"back-to-back CFG/TX_ON lost");
  check_frame(0,128,65);check_frame(196,60,66);
  // Full queue drops a whole new line, then permits pop+push on the exact
  // terminal CRC acknowledgement edge, keeping the four surviving lines.
  received=0;stall=1;
  for(integer n=0;n<4;n++)send_line(8,8'(67+n),0);
  send_line(8,90,0);if(drops!=2)$fatal(1,"full queue drop counter");
  for(integer n=0;n<8;n++)feed(8'(71+n%26));
  stall=0;
  while(!(dut.output_state==2 && host_done && dut.output_index+1==dut.total_bytes))@(negedge clk);
  rv=2;radio_rx_data={8'd0,8'd10,8'd0};
  @(negedge clk);rv=0;
  if(dut.text_count[1]!=4 || drops!=2)$fatal(1,"simultaneous full pop/push occupancy");
  drained();if(received!=5*76)$fatal(1,"queue length/order");
  for(integer n=0;n<5;n++)check_frame(n*76,8,8'(67+n));
  $display("PASS controller text:127/128/255 bounds,256 rejection, real2M CFG/TX_ON, four-line FIFO order/overflow and atomic full pop+push");$finish;
 end
 initial begin #50000000;$fatal(1,"text watchdog");end
endmodule
