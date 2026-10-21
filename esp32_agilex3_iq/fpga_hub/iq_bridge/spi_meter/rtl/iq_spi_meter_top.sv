// Standalone PMOD B SPI -> packet RAM -> host UART qualification image.
// Send ASCII C at 2 Mbaud for exactly one 1056-byte SPI transaction.
// Every other board IO remains reserved input/tri-state; no GPIO0 is driven.
module iq_spi_meter_top(
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
 logic[7:0] memory[0:1055];logic[10:0] requested,received,sent,reply_length;
 logic[7:0] spi_byte,request_byte;
 iq_spi_master #(.MODE(1),.HALF_CYCLES(5),.MAX_BYTES(1056)) spi(
  .clk(CLOCK1_50),.reset(reset),.tx_data(requested==0 ? request_byte : 8'd0),.tx_valid(spi_tx_valid),
  .tx_last(spi_last),.tx_ready(spi_tx_ready),.rx_data(spi_byte),.rx_valid(spi_rx_valid),
  .rx_ready(1'b1),.miso(SPI_MISO),.mosi(SPI_MOSI),.sck(SPI_SCK),.cs_n(SPI_CS_N),.limit_error(limit_error));
 logic[25:0] timeout_count;logic failed,identity;
 function automatic logic[7:0] identity_byte(input logic[10:0] n);
  case(n)
   0:identity_byte="S";1:identity_byte="P";2:identity_byte="I";3:identity_byte="Q";
   7:identity_byte="2";default:identity_byte="0";
  endcase
 endfunction
 typedef enum logic[2:0]{IDLE,WAIT_READY,READ_SPI,DRAIN,UART_WAIT,PREP_SUM}state_t;
 state_t state;
 logic previous_cs;
 always_ff @(posedge CLOCK1_50)if(reset)previous_cs<=1;else previous_cs<=SPI_CS_N;
 wire meter_start=spi_tx_valid && spi_tx_ready && requested==0;
 wire meter_end=!previous_cs && SPI_CS_N;
 wire meter_valid,meter_synthetic;
 wire[31:0] meter_sequence,meter_commits,meter_rejects,meter_samples;
 wire[63:0] meter_power,meter_cycles;
 wire[31:0] meter_peak,meter_clip,meter_components,meter_bytes,meter_chunks;
 wire[7:0] meter_error;
 logic[31:0] summary_crc;
 iq_spi_capture_meter meter(.clk(CLOCK1_50),.reset(reset),.packet_start(meter_start),
  .byte_valid(spi_rx_valid),.packet_end(meter_end),.byte_data(spi_byte),
  .result_valid(meter_valid),.result_synthetic(meter_synthetic),.result_sequence(meter_sequence),
  .commit_count(meter_commits),.reject_count(meter_rejects),.result_samples(meter_samples),
  .result_power(meter_power),.result_ingress_cycles(meter_cycles),.result_peak(meter_peak),
  .result_clip_samples(meter_clip),.result_clip_components(meter_components),
  .last_error(meter_error),.result_bytes(meter_bytes),.result_chunks(meter_chunks));
 function automatic logic[31:0] crc_byte(input logic[31:0] crc,input logic[7:0] value);
  logic[31:0] c;begin c=crc^{24'd0,value};
   for(integer n=0;n<8;n++)c=(c>>1)^(c[0]?32'hedb88320:32'd0);
   crc_byte=c;end
 endfunction
 function automatic logic[7:0] summary_byte(input logic[10:0] n);
  case(n)
   0:summary_byte="S";1:summary_byte="P";2:summary_byte="M";3:summary_byte="1";
   4:summary_byte=1;5:summary_byte={6'd0,meter_synthetic,meter_valid};
   6:summary_byte=meter_error;7:summary_byte=0;
   8,9,10,11:summary_byte=8'(meter_sequence>>((n-8)*8));
   12,13,14,15:summary_byte=8'(meter_commits>>((n-12)*8));
   16,17,18,19:summary_byte=8'(meter_rejects>>((n-16)*8));
   20,21,22,23:summary_byte=8'(meter_samples>>((n-20)*8));
   24,25,26,27,28,29,30,31:summary_byte=8'(meter_power>>((n-24)*8));
   32,33,34,35:summary_byte=8'(meter_peak>>((n-32)*8));
   36,37,38,39:summary_byte=8'(meter_clip>>((n-36)*8));
   40,41,42,43:summary_byte=8'(meter_components>>((n-40)*8));
   44,45,46,47,48,49,50,51:summary_byte=8'(meter_cycles>>((n-44)*8));
   52,53,54,55:summary_byte=8'(meter_bytes>>((n-52)*8));
   56,57,58,59:summary_byte=8'(meter_chunks>>((n-56)*8));
   default:summary_byte=0;
  endcase
 endfunction

 // One explicit RAM write port shared by mutually exclusive raw/summary states.
 wire memory_write=(state==READ_SPI && spi_rx_valid) || state==PREP_SUM;
 wire[10:0] memory_address=state==READ_SPI ? received : sent;
 wire[7:0] memory_data=state==READ_SPI ? spi_byte :
  sent<60 ? summary_byte(sent) : 8'((~summary_crc)>>((sent-60)*8));
 always_ff @(posedge CLOCK1_50)if(memory_write)memory[memory_address]<=memory_data;
 assign spi_tx_valid=state==READ_SPI && requested<1056;
 assign spi_last=requested==1055;
 always_ff @(posedge CLOCK1_50)begin
  tx_start<=0;
  if(reset)begin state<=IDLE;requested<=0;received<=0;sent<=0;timeout_count<=0;tx_byte<=0;failed<=0;identity<=0;request_byte<=0;reply_length<=1056;summary_crc<=~32'd0;end
  else case(state)
   IDLE:if(command_valid)begin
    if(command==8'h43 || command==8'h54 || command==8'h52)begin
     reply_length<=1056;request_byte<=command==8'h43 ? 8'd0 : command;state<=WAIT_READY;timeout_count<=0;failed<=0;identity<=0;end
    else if(command==8'h49)begin identity<=1;reply_length<=8;sent<=0;state<=DRAIN;end
    else if(command==8'h4d)begin identity<=0;failed<=0;reply_length<=64;sent<=0;summary_crc<=~32'd0;state<=PREP_SUM;end
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
     received<=received+1'b1;
     if(received==1055)begin sent<=0;state<=DRAIN;end
    end
   end
   DRAIN:if(!tx_busy)begin tx_byte<=identity?identity_byte(sent):failed?8'd0:memory[sent];tx_start<=1;state<=UART_WAIT;end
   UART_WAIT:if(tx_done)begin
    if(sent==reply_length-1'b1)state<=IDLE;
    else begin sent<=sent+1'b1;state<=DRAIN;end
   end
   PREP_SUM:begin
    if(sent<60)summary_crc<=crc_byte(summary_crc,summary_byte(sent));
    if(sent==63)begin sent<=0;state<=DRAIN;end
    else sent<=sent+1'b1;
   end
   default:state<=IDLE;
  endcase
 end
endmodule
