(* altera_ip="atum.local:ip:iq_capture_memory:1.0" *)
module iq_capture_memory(
 (* altera_interface="altera.com:interfaces:altera_clock:1.0 in clk", altera_intf_port="clk clk clk" *) input logic clk,
 (* altera_interface="altera.com:interfaces:altera_reset:1.0 in reset", altera_intf_port="reset reset reset" *) input logic reset,
 (* altera_interface="atum.local:conduit:capture_memory:1.0 subordinate capture_memory", altera_intf_port="capture_memory write mem_write", altera_port="clockref:clk, resetref:reset" *) input logic mem_write,
 (* altera_interface="atum.local:conduit:capture_memory:1.0 subordinate capture_memory", altera_intf_port="capture_memory waddr mem_waddr" *) input logic [14:0] mem_waddr,
 (* altera_interface="atum.local:conduit:capture_memory:1.0 subordinate capture_memory", altera_intf_port="capture_memory wdata mem_wdata" *) input logic [15:0] mem_wdata,
 (* altera_interface="atum.local:conduit:capture_memory:1.0 subordinate capture_memory", altera_intf_port="capture_memory raddr mem_raddr" *) input logic [14:0] mem_raddr,
 (* altera_interface="atum.local:conduit:capture_memory:1.0 subordinate capture_memory", altera_intf_port="capture_memory q mem_q" *) output logic [15:0] mem_q
);
// Same two16K sample banks and synchronous one-cycle read as qualified bridge.
(* ramstyle="M20K, no_rw_check" *)logic[15:0] memory[0:32767];
always_ff @(posedge clk)begin
 if(mem_write)memory[mem_waddr]<=mem_wdata;
 mem_q<=memory[mem_raddr];
end
endmodule
