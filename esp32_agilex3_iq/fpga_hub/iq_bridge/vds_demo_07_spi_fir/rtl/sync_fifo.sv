// Single-clock bounded FIFO. Head read is synchronous; consumers allow2clks
// after a pop before using the new head. Full pushes are never silently accepted.
module sync_fifo #(parameter WIDTH=8,DEPTH=4096,AW=$clog2(DEPTH))(
 input logic clk,reset,push,pop,input logic[WIDTH-1:0] data,
 output logic[WIDTH-1:0] head,output logic[AW:0] count,
 output logic full,empty,output logic[AW:0] highwater);
(* ramstyle="M20K, no_rw_check" *)logic[WIDTH-1:0] memory[0:DEPTH-1];
logic[AW-1:0] wp,rp;wire put=push&&!full;wire take=pop&&!empty;
assign full=(count==DEPTH);assign empty=(count==0);
always_ff @(posedge clk)begin
 if(put)memory[wp]<=data;
 head<=memory[rp];
 if(reset)begin wp<=0;rp<=0;count<=0;highwater<=0;end
 else begin
 if(put)wp<=wp+1'b1;if(take)rp<=rp+1'b1;
 case({put,take})2'b10:begin count<=count+1'b1;if(count+1'b1>highwater)highwater<=count+1'b1;end
 2'b01:count<=count-1'b1;default:begin end endcase
 end
end
endmodule
