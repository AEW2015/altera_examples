(* altera_ip="atum.local:ip:iq_radio_uarts:1.0" *)
module iq_radio_uarts(
 (* altera_interface="altera.com:interfaces:altera_clock:1.0 in clk", altera_intf_port="clk clk clk" *) input logic clk,
 (* altera_interface="altera.com:interfaces:altera_reset:1.0 in reset", altera_intf_port="reset reset reset" *) input logic reset,
 (* altera_interface="atum.local:conduit:radio_bytes:1.0 subordinate radio_link", altera_intf_port="radio_link fast radio_fast", altera_port="clockref:clk, resetref:reset" *) input logic [2:0] radio_fast,
 (* altera_interface="atum.local:conduit:radio_bytes:1.0 subordinate radio_link", altera_intf_port="radio_link rx_valid rv" *) output logic [2:0] rv,
 (* altera_interface="atum.local:conduit:radio_bytes:1.0 subordinate radio_link", altera_intf_port="radio_link rx_data radio_rx_data" *) output logic [23:0] radio_rx_data,
 (* altera_interface="atum.local:conduit:radio_bytes:1.0 subordinate radio_link", altera_intf_port="radio_link rx_error re" *) output logic [2:0] re,
 (* altera_interface="atum.local:conduit:radio_bytes:1.0 subordinate radio_link", altera_intf_port="radio_link tx_start ts" *) input logic [2:0] ts,
 (* altera_interface="atum.local:conduit:radio_bytes:1.0 subordinate radio_link", altera_intf_port="radio_link tx_data radio_tx_data" *) input logic [23:0] radio_tx_data,
 (* altera_interface="atum.local:conduit:radio_bytes:1.0 subordinate radio_link", altera_intf_port="radio_link tx_busy tbusy" *) output logic [2:0] tbusy,
 (* altera_interface="atum.local:conduit:radio_bytes:1.0 subordinate radio_link", altera_intf_port="radio_link tx_done tdone" *) output logic [2:0] tdone,
 (* altera_interface="atum.local:conduit:uart:1.0 manager uart0", altera_intf_port="uart0 rx rx0", altera_port="clockref:clk, resetref:reset" *) input logic rx0,
 (* altera_interface="atum.local:conduit:uart:1.0 manager uart0", altera_intf_port="uart0 tx tx0" *) output logic tx0,
 (* altera_interface="atum.local:conduit:uart:1.0 manager uart1", altera_intf_port="uart1 rx rx1", altera_port="clockref:clk, resetref:reset" *) input logic rx1,
 (* altera_interface="atum.local:conduit:uart:1.0 manager uart1", altera_intf_port="uart1 tx tx1" *) output logic tx1,
 (* altera_interface="atum.local:conduit:spi:1.0 manager spi", altera_intf_port="spi miso spi_miso", altera_port="clockref:clk, resetref:reset" *) input logic spi_miso,
 (* altera_interface="atum.local:conduit:spi:1.0 manager spi", altera_intf_port="spi ready spi_ready" *) input logic spi_ready,
 (* altera_interface="atum.local:conduit:spi:1.0 manager spi", altera_intf_port="spi mosi spi_mosi" *) output wire spi_mosi,
 (* altera_interface="atum.local:conduit:spi:1.0 manager spi", altera_intf_port="spi sck spi_sck" *) output wire spi_sck,
 (* altera_interface="atum.local:conduit:spi:1.0 manager spi", altera_intf_port="spi cs_n spi_cs_n" *) output wire spi_cs_n
);
wire[1:0] rxs={rx1,rx0};wire[1:0] txs;assign {tx1,tx0}=txs;
wire[2:0] rx_busy;
genvar g;generate for(g=0;g<2;g=g+1)begin:radios
 uart_dynamic_rx urx(clk,reset,rxs[g],radio_fast[g]?16'd25:16'd434,rv[g],radio_rx_data[8*g+:8],re[g],rx_busy[g]);
 uart_dynamic_tx utx(clk,reset,ts[g],radio_tx_data[8*g+:8],radio_fast[g]?16'd25:16'd434,txs[g],tbusy[g],tdone[g]);
end endgenerate
 iq_spi_radio_proxy spi_proxy(.clk(clk),.reset(reset),.tx_start(ts[2]),.tx_data(radio_tx_data[23:16]),
 .tx_busy(tbusy[2]),.tx_done(tdone[2]),.rx_valid(rv[2]),.rx_data(radio_rx_data[23:16]),.rx_error(re[2]),
 .spi_miso(spi_miso),.spi_ready(spi_ready),.spi_mosi(spi_mosi),.spi_sck(spi_sck),.spi_cs_n(spi_cs_n));
endmodule
