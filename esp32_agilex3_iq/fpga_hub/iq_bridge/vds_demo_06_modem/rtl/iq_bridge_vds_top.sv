// Atum A3 Nano board wrapper for the native Visual Designer Studio system.
// Preserve qualified IQ bridge pin directions and reset/POR behavior.
module iq_bridge_vds_top(
 input logic CLOCK1_50, HOST_RX, RFS2_TX, PMOD0_TX, PMOD1_TX,
 output wire HOST_TX, RFS2_RX, PMOD0_RX, PMOD1_RX
);
`ifdef VERILATOR
 wire ninit_done=1'b0;
`else
 wire ninit_done;
 altera_agilex_config_reset_release_endpoint reset_release(.conf_reset(ninit_done));
`endif
logic [7:0] por=0;
wire reset=!(&por);
always_ff @(posedge CLOCK1_50 or posedge ninit_done)
 if(ninit_done) por<=0;
 else if(!(&por)) por<=por+1'b1;

iq_bridge_system system(
 .clk_clk(CLOCK1_50), .reset_reset(reset), .monitor_reset_reset(reset),
 .host_serial_rx(HOST_RX), .host_serial_tx(HOST_TX),
 .radio0_rx(RFS2_TX), .radio0_tx(RFS2_RX),
 .radio1_rx(PMOD0_TX), .radio1_tx(PMOD0_RX),
 .radio2_rx(PMOD1_TX), .radio2_tx(PMOD1_RX)
);
endmodule
