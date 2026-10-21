// Byte-stream SPI master. Stalls between bytes for downstream backpressure.
// Mode 0..3, MSB-first only; divider >= 2 system clocks per SCK half-cycle.
module iq_spi_master #(
 parameter integer HALF_CYCLES=5, MODE=0, MAX_BYTES=1056
)(
 input logic clk, reset,
 input logic [7:0] tx_data, input logic tx_valid, tx_last,
 output wire tx_ready,
 output logic [7:0] rx_data, output logic rx_valid,
 input logic rx_ready,
 input logic miso,
 output logic mosi, sck, cs_n, output logic limit_error
);
 localparam bit CPOL=(MODE>=2), CPHA=(MODE%2)!=0;
 logic active, last_byte;
 logic [7:0] send_byte, receive_byte;
 integer timer, edge_count, bytes_sent;
 assign tx_ready=!active && !rx_valid;
 initial begin
  if(HALF_CYCLES<2 || MODE<0 || MODE>3 || MAX_BYTES<1)
   $error("invalid SPI parameters");
 end
 always_ff @(posedge clk) begin
  if(reset) begin
   active<=0;rx_valid<=0;rx_data<=0;mosi<=0;sck<=CPOL;cs_n<=1;
   limit_error<=0;timer<=0;edge_count<=0;bytes_sent<=0;
   send_byte<=0;receive_byte<=0;last_byte<=0;
  end else begin
   if(rx_valid && rx_ready) begin
    rx_valid<=0;
    if(last_byte) begin cs_n<=1;bytes_sent<=0;end
   end
   if(tx_valid && tx_ready) begin
    active<=1;cs_n<=0;sck<=CPOL;send_byte<=tx_data;receive_byte<=0;
    last_byte<=tx_last || bytes_sent==MAX_BYTES-1;
    if(bytes_sent==MAX_BYTES-1 && !tx_last) limit_error<=1;
    bytes_sent<=bytes_sent+1;timer<=HALF_CYCLES-1;edge_count<=0;
    if(!CPHA) mosi<=tx_data[7];
   end else if(active) begin
    if(timer!=0) timer<=timer-1;
    else begin
     timer<=HALF_CYCLES-1;sck<=~sck;
     // Even edge is leading; odd edge is trailing.
     if((edge_count%2)==(CPHA?1:0)) begin
      receive_byte<={receive_byte[6:0],miso};
      if(edge_count==15) rx_data<={receive_byte[6:0],miso};
     end else begin
      if(CPHA) mosi<=send_byte[7-edge_count/2];
      else if(edge_count<15) mosi<=send_byte[6-edge_count/2];
     end
     if(edge_count==15) begin
      active<=0;rx_valid<=1;
      if(!CPHA) rx_data<=receive_byte;
     end else edge_count<=edge_count+1;
    end
   end
  end
 end
endmodule
