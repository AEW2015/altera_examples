// Standalone PMOD B SPI -> packet RAM -> host UART qualification image.
// Send ASCII C at 2 Mbaud for exactly one 1056-byte SPI transaction.
// Every other board IO remains reserved input/tri-state; no GPIO0 is driven.
module iq_spi_qualification_top(
 input logic CLOCK1_50,HOST_RX,SPI_MISO,SPI_READY,
 output wire HOST_TX,SPI_MOSI,SPI_SCK,SPI_CS_N
);
`ifdef IQ_SPI_SIM
 wire ninit_done=1'b0;
`else
 wire ninit_done;
 altera_agilex_config_reset_release_endpoint reset_release(.conf_reset(ninit_done));
`endif
 logic[7:0] powerup=0;wire reset=!(&powerup);
 always_ff @(posedge CLOCK1_50 or posedge ninit_done)
  if(ninit_done)powerup<=0;
  else if(reset)powerup<=powerup+1'b1;
 (* async_reg="true" *)logic ready_a,ready_b;
 always_ff @(posedge CLOCK1_50)begin ready_a<=SPI_READY;ready_b<=ready_a;end
 logic command_valid,framing_error;logic[7:0] command;
 uart_fractional_rx rx(.clk(CLOCK1_50),.reset(reset),.rx(HOST_RX),.baud(32'd2000000),
  .valid(command_valid),.data(command),.framing_error(framing_error));
 logic tx_start,tx_busy,tx_done;logic[7:0] tx_byte;
 uart_fractional_tx tx(.clk(CLOCK1_50),.reset(reset),.start(tx_start),.data(tx_byte),
  .baud(32'd2000000),.tx(HOST_TX),.busy(tx_busy),.done(tx_done));
 logic spi_tx_valid,spi_tx_ready,spi_rx_valid,spi_last,limit_error;
 logic[7:0] memory[0:1055];logic[10:0] requested,received,sent;
 logic[7:0] spi_byte,request_byte;
 iq_spi_master #(.MODE(1),.HALF_CYCLES(5),.MAX_BYTES(1056)) spi(
  .clk(CLOCK1_50),.reset(reset),.tx_data(requested==0 ? request_byte : 8'd0),.tx_valid(spi_tx_valid),
  .tx_last(spi_last),.tx_ready(spi_tx_ready),.rx_data(spi_byte),.rx_valid(spi_rx_valid),
  .rx_ready(1'b1),.miso(SPI_MISO),.mosi(SPI_MOSI),.sck(SPI_SCK),.cs_n(SPI_CS_N),.limit_error(limit_error));
 logic[25:0] timeout_count;logic failed,identity;
 function automatic logic[7:0] identity_byte(input logic[10:0] n);
  case(n)
   0:identity_byte="S";1:identity_byte="P";2:identity_byte="I";3:identity_byte="Q";
   7:identity_byte="1";default:identity_byte="0";
  endcase
 endfunction
 typedef enum logic[2:0]{IDLE,WAIT_READY,READ_SPI,DRAIN,UART_WAIT}state_t;
 state_t state;
 assign spi_tx_valid=state==READ_SPI && requested<1056;
 assign spi_last=requested==1055;
 always_ff @(posedge CLOCK1_50)begin
  tx_start<=0;
  if(reset)begin state<=IDLE;requested<=0;received<=0;sent<=0;timeout_count<=0;tx_byte<=0;failed<=0;identity<=0;request_byte<=0;end
  else case(state)
   IDLE:if(command_valid)begin
    if(command==8'h43 || command==8'h54 || command==8'h52)begin
     request_byte<=command==8'h43 ? 8'd0 : command;state<=WAIT_READY;timeout_count<=0;failed<=0;identity<=0;end
    else if(command==8'h49)begin identity<=1;sent<=0;state<=DRAIN;end
   end
   WAIT_READY:begin
    if(ready_b)begin requested<=0;received<=0;state<=READ_SPI;end
    else if(timeout_count==50000000)begin
     // Invalid fixed packet gives host a bounded, CRC-rejected timeout response.
     failed<=1;
     sent<=0;state<=DRAIN;
    end else timeout_count<=timeout_count+1'b1;
   end
   READ_SPI:begin
    if(spi_tx_valid && spi_tx_ready)requested<=requested+1'b1;
    if(spi_rx_valid)begin
     memory[received]<=spi_byte;received<=received+1'b1;
     if(received==1055)begin sent<=0;state<=DRAIN;end
    end
   end
   DRAIN:if(!tx_busy)begin tx_byte<=identity?identity_byte(sent):failed?8'd0:memory[sent];tx_start<=1;state<=UART_WAIT;end
   UART_WAIT:if(tx_done)begin
    if(sent==(identity?7:1055))state<=IDLE;
    else begin sent<=sent+1'b1;state<=DRAIN;end
   end
   default:state<=IDLE;
  endcase
 end
endmodule
