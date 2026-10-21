// Runtime baud divisor; change only while idle. Divisors at50MHz:434,25.
module uart_dynamic_rx(input logic clk,reset,rx,input logic[15:0] divisor,
 output logic valid,output logic[7:0] data,output logic framing_error,output logic busy);
(* async_reg="true" *)logic a=1,b=1;logic[15:0] timer;logic[3:0] bitno;logic[7:0] shift;
always_ff @(posedge clk)begin
 a<=rx;b<=a;valid<=0;framing_error<=0;
 if(reset)begin busy<=0;timer<=0;bitno<=0;end
 else if(!busy)begin if(!b)begin busy<=1;timer<=divisor/2;bitno<=0;end end
 else if(timer!=0)timer<=timer-1'b1;
 else begin timer<=divisor-1'b1;
 if(bitno==0)begin if(b)busy<=0;else bitno<=1;end
 else if(bitno<=8)begin shift[bitno-1]<=b;bitno<=bitno+1'b1;end
 else begin busy<=0;if(b)begin data<=shift;valid<=1;end else framing_error<=1;end
 end
end
endmodule
module uart_dynamic_tx(input logic clk,reset,start,input logic[7:0] data,
 input logic[15:0] divisor,output logic tx,busy,output logic done);
logic[9:0] shift;logic[15:0] timer;logic[3:0] bitno;
assign tx=busy?shift[0]:1'b1;
always_ff @(posedge clk)begin
 done<=0;
 if(reset)begin busy<=0;shift<=10'h3ff;timer<=0;bitno<=0;end
 else if(!busy)begin if(start)begin busy<=1;shift<={1'b1,data,1'b0};timer<=divisor-1'b1;bitno<=0;end end
 else if(timer!=0)timer<=timer-1'b1;
 else begin timer<=divisor-1'b1;shift<={1'b1,shift[9:1]};if(bitno==9)begin busy<=0;done<=1;end else bitno<=bitno+1'b1;end
end
endmodule
