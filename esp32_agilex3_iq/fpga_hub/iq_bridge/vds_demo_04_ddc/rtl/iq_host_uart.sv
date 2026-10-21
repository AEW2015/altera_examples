(* altera_ip="atum.local:ip:iq_host_uart:1.0" *)
module iq_host_uart(
 (* altera_interface="altera.com:interfaces:altera_clock:1.0 in clk", altera_intf_port="clk clk clk" *) input logic clk,
 (* altera_interface="altera.com:interfaces:altera_reset:1.0 in reset", altera_intf_port="reset reset reset" *) input logic reset,
 (* altera_interface="atum.local:conduit:host_bytes:1.0 subordinate host_link", altera_intf_port="host_link baud host_baud", altera_port="clockref:clk, resetref:reset" *) input logic [31:0] host_baud,
 (* altera_interface="atum.local:conduit:host_bytes:1.0 subordinate host_link", altera_intf_port="host_link rx_valid host_valid" *) output logic host_valid,
 (* altera_interface="atum.local:conduit:host_bytes:1.0 subordinate host_link", altera_intf_port="host_link rx_data host_byte" *) output logic [7:0] host_byte,
 (* altera_interface="atum.local:conduit:host_bytes:1.0 subordinate host_link", altera_intf_port="host_link rx_error host_frame_error" *) output logic host_frame_error,
 (* altera_interface="atum.local:conduit:host_bytes:1.0 subordinate host_link", altera_intf_port="host_link tx_start host_start" *) input logic host_start,
 (* altera_interface="atum.local:conduit:host_bytes:1.0 subordinate host_link", altera_intf_port="host_link tx_data host_out" *) input logic [7:0] host_out,
 (* altera_interface="atum.local:conduit:host_bytes:1.0 subordinate host_link", altera_intf_port="host_link tx_busy host_busy" *) output logic host_busy,
 (* altera_interface="atum.local:conduit:host_bytes:1.0 subordinate host_link", altera_intf_port="host_link tx_done host_done" *) output logic host_done,
 (* altera_interface="atum.local:conduit:uart:1.0 manager serial", altera_intf_port="serial rx rx", altera_port="clockref:clk, resetref:reset" *) input logic rx,
 (* altera_interface="atum.local:conduit:uart:1.0 manager serial", altera_intf_port="serial tx tx" *) output logic tx
);
uart_fractional_rx hr(clk,reset,rx,host_baud,host_valid,host_byte,host_frame_error);
uart_fractional_tx ht(clk,reset,host_start,host_out,host_baud,tx,host_busy,host_done);
endmodule
