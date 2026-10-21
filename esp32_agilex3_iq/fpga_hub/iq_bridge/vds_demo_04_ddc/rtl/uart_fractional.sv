// UART8N1 with fractional bit periods. Baud updates only between whole frames.
module uart_fractional_rx #(parameter CLOCK_HZ=50000000)(
 input logic clk,reset,rx,input logic[31:0] baud,
 output logic valid,output logic[7:0] data,output logic framing_error);
(* async_reg="true" *)logic a=1,b=1;
logic busy;logic[31:0] phase;logic[3:0] bitno;logic[7:0] shift;
wire[32:0] next_phase={1'b0,phase}+({1'b0,baud}<<1);
always_ff @(posedge clk)begin
 a<=rx;b<=a;valid<=0;framing_error<=0;
 if(reset)begin busy<=0;phase<=0;bitno<=0;end
 else if(!busy)begin if(!b)begin busy<=1;phase<=0;bitno<=0;end end
 else if(next_phase >= ((bitno==0)?CLOCK_HZ:2*CLOCK_HZ))begin
  phase<=32'(next_phase-((bitno==0)?CLOCK_HZ:2*CLOCK_HZ));
  if(bitno==0)begin if(b)busy<=0;else bitno<=1;end
  else if(bitno<=8)begin shift[bitno-1]<=b;bitno<=bitno+1'b1;end
  else begin busy<=0;if(b)begin data<=shift;valid<=1;end else framing_error<=1;end
 end else phase<=next_phase[31:0];
end
endmodule
module uart_fractional_tx #(parameter CLOCK_HZ=50000000)(
 input logic clk,reset,start,input logic[7:0] data,input logic[31:0] baud,
 output logic tx,busy,output logic done);
logic[9:0] shift;logic[31:0] phase;logic[3:0] bitno;
wire[32:0] next_phase={1'b0,phase}+{1'b0,baud};
assign tx=busy?shift[0]:1'b1;
always_ff @(posedge clk)begin
 done<=0;
 if(reset)begin busy<=0;shift<=10'h3ff;phase<=0;bitno<=0;end
 else if(!busy)begin if(start)begin busy<=1;shift<={1'b1,data,1'b0};phase<=0;bitno<=0;end end
 else if(next_phase>=CLOCK_HZ)begin
  phase<=32'(next_phase-CLOCK_HZ);shift<={1'b1,shift[9:1]};
  if(bitno==9)begin busy<=0;done<=1;end else bitno<=bitno+1'b1;
 end else phase<=next_phase[31:0];
end
endmodule
