// Fixed-profile SPI radio backend on the existing IQB1 radio-byte interface.
// Does not emulate unsupported ESP32 controls. Receipt ticks are not RF clocks.
module iq_spi_radio_proxy #(
 parameter integer READY_TIMEOUT=50000000,CAPTURE_TIMEOUT=200000000
)(input logic clk,reset,input logic tx_start,input logic[7:0]tx_data,
 output wire tx_busy,output logic tx_done,
 output logic rx_valid,output logic[7:0]rx_data,output wire rx_error,
 input logic spi_miso,spi_ready,output wire spi_mosi,spi_sck,spi_cs_n);
 assign rx_error=0;
 (* async_reg="true" *)logic ready_a,ready_b;
 always_ff @(posedge clk)begin ready_a<=spi_ready;ready_b<=ready_a;end
 logic spi_tx_valid,spi_tx_ready,spi_rx_valid,spi_last,limit_error,spi_abort;
 logic[7:0]spi_byte,request_byte;
 logic[10:0]requested,received;
 iq_spi_master #(.MODE(1),.HALF_CYCLES(5),.MAX_BYTES(1056)) spi(
 .clk(clk),.reset(reset || spi_abort),.tx_data(requested==0 ? request_byte : 8'd0),
 .tx_valid(spi_tx_valid),.tx_last(spi_last),.tx_ready(spi_tx_ready),
 .rx_data(spi_byte),.rx_valid(spi_rx_valid),.rx_ready(1'b1),.miso(spi_miso),
 .mosi(spi_mosi),.sck(spi_sck),.cs_n(spi_cs_n),.limit_error(limit_error));
 logic previous_cs;
 always_ff @(posedge clk)if(reset)previous_cs<=1;else previous_cs<=spi_cs_n;
 wire packet_start=spi_tx_valid && spi_tx_ready && requested==0;
 wire packet_end=!previous_cs && spi_cs_n;
 wire observed_valid,observed_synthetic;
 wire[31:0]observed_sequence,commits,rejects,observed_samples;
 wire[63:0]power_sum,ingress_cycles;
 wire[31:0]peak,clipped,components,observed_bytes,observed_chunks;
 wire[7:0]last_error;
 iq_spi_capture_meter validator(.clk(clk),.reset(reset),.packet_start(packet_start),
 .byte_valid(spi_rx_valid),.packet_end(packet_end),.byte_data(spi_byte),
 .result_valid(observed_valid),.result_synthetic(observed_synthetic),.result_sequence(observed_sequence),
 .commit_count(commits),.reject_count(rejects),.result_samples(observed_samples),
 .result_power(power_sum),.result_ingress_cycles(ingress_cycles),.result_peak(peak),
 .result_clip_samples(clipped),.result_clip_components(components),.last_error(last_error),
 .result_bytes(observed_bytes),.result_chunks(observed_chunks));
 function automatic logic[31:0] crc_byte(input logic[31:0] crc,input logic[7:0] value);
  logic[31:0]c;begin c=crc^{24'd0,value};for(integer n=0;n<8;n++)c=(c>>1)^(c[0]?32'hedb88320:0);return c;end
 endfunction
 function automatic logic[63:0] hex8(input logic[31:0] value);
  logic[63:0]s;logic[3:0]nibble;begin
   for(integer n=0;n<8;n++)begin nibble=4'(value>>(28-4*n));s[63-n*8-:8]=nibble<10 ? 8'(48+nibble) : 8'(87+nibble);end
   return s;end
 endfunction
 // Reconstruct candidate CI8 only; validator alone authorizes publication.
 logic[10:0]packet_index;
 logic[31:0]packet_offset,packet_length,whole_crc;
 logic[7:0]low_i;
 wire payload_byte=packet_index>=32 && {22'd0,packet_index}<({1'b0,packet_length}+33'd32);
 wire[32:0]sample_address=({1'b0,packet_offset}>>1)+(({22'd0,packet_index}-33'd32)>>1);
 wire raw_write=spi_rx_valid && payload_byte && packet_index[0] && sample_address<16380;
 (* ramstyle="M20K, no_rw_check" *)logic[15:0]raw_memory[0:16379];
 logic[15:0]raw_q;
 logic[14:0]output_index;
 always_ff @(posedge clk)begin
  if(raw_write)raw_memory[sample_address[13:0]]<={spi_byte,low_i};
  raw_q<=raw_memory[output_index[14:1]];
 end
 always_ff @(posedge clk)begin
  if(reset)begin packet_index<=0;packet_offset<=0;packet_length<=0;low_i<=0;whole_crc<=~32'd0;end
  else begin
   if(packet_start)packet_index<=0;
   if(spi_rx_valid)begin
    case(packet_index)
     12,13,14,15:packet_offset[(packet_index-12)*8+:8]<=spi_byte;
     20,21,22,23:packet_length[(packet_index-20)*8+:8]<=spi_byte;
     default:;
    endcase
    if(payload_byte && packet_index<1056)begin
     whole_crc<=crc_byte((packet_offset==0 && packet_index==32)?~32'd0:whole_crc,spi_byte);
     if(!packet_index[0])low_i<=spi_byte;
    end
    packet_index<=packet_index+1'b1;
   end
  end
 end
 logic desired_synthetic,force_boundary;
 logic first_packet,ready_low_seen;
 logic[767:0]line_shift,response;
 logic[6:0]line_length,response_length,response_index;
 logic overflow;
 logic[31:0]capture_deadline,ready_deadline,base_commit;
 logic[6:0]transactions;
 logic[1:0]pace,settle;
 typedef enum logic[3:0]{IDLE,TEXT,SPI_WAIT,SPI_READ,SPI_SETTLE,EMIT_HEADER,EMIT_RAW}state_t;
 state_t state;
 assign tx_busy=state!=IDLE;
 assign spi_tx_valid=state==SPI_READ && requested<1056;
 assign spi_last=requested==1055;
 task automatic reply(input logic[767:0] text,input logic[6:0] length);
  begin response<=text;response_length<=length;response_index<=0;pace<=0;state<=TEXT;end
 endtask
 always_ff @(posedge clk)begin
  tx_done<=tx_start;rx_valid<=0;spi_abort<=0;
  if(reset)begin
   first_packet<=1;ready_low_seen<=0;spi_abort<=0;tx_done<=0;rx_data<=0;desired_synthetic<=1;force_boundary<=0;line_shift<=0;line_length<=0;
   response<=0;response_length<=0;response_index<=0;overflow<=0;state<=IDLE;
   capture_deadline<=0;ready_deadline<=0;base_commit<=0;transactions<=0;
   requested<=0;received<=0;request_byte<=0;pace<=0;settle<=0;output_index<=0;
  end else begin
   // post_trans ISR can deassert READY several us AFTER CS rises. A high
   // level left over from the consumed DMA buffer is not a new reservation.
   // Latch the low anywhere after packet_start, then wait for armed-high.
   if(packet_start)begin first_packet<=0;ready_low_seen<=0;end
   else if(!ready_b)ready_low_seen<=1;
   if(tx_start && state==IDLE)begin
    if(tx_data==10)begin
     line_shift<=0;line_length<=0;overflow<=0;
     if(overflow)reply("ERR line_too_long\n",18);
     else if(line_length==0)begin end
     else if(line_shift=="SPI_MODE SYNTH")begin desired_synthetic<=1;reply("OK SPI_MODE SYNTH\n",18);end
     else if(line_shift=="SPI_MODE RF")begin desired_synthetic<=0;reply("OK SPI_MODE RF\n",15);end
     else if(line_shift=="SPI?")begin
      reply({"SPI 00030001 ",hex8({31'd0,desired_synthetic})," ",hex8({30'd0,observed_synthetic,observed_valid})," ",hex8(observed_sequence)," ",hex8(commits)," ",hex8(rejects)," ",hex8(ingress_cycles[31:0])," ",hex8(ingress_cycles[63:32]),"\n"},76);
     end
     else if(line_shift=="MODE?")reply("RF_MODE,SDR,baud=2000000,transport=SPI\n",39);
     else if(line_shift=="INFO")reply("ESP32SDR SPI_PROXY source2 fixedfreq2447 rate16000000\n",54);
     else if(line_shift=="RELEASE")reply("OK RELEASE\n",11);
     else if(line_length>=5 && (line_shift>>(8*(line_length-5)))=="SYNC ")reply({line_shift[759:0],8'd10},line_length+1'b1);
     else if(line_shift=="FREQ 2447")reply("OK\n",3);
     else if(line_shift=="CAP16 16380 6")begin
      first_packet<=1;ready_low_seen<=0;base_commit<=commits;capture_deadline<=0;ready_deadline<=0;transactions<=0;
      force_boundary<=!desired_synthetic;request_byte<=8'h54;state<=SPI_WAIT;
     end
     else reply("ERR unsupported_spi_control\n",28);
    end else if(tx_data!=13)begin
     if(line_length<95)begin line_shift<={line_shift[759:0],tx_data};line_length<=line_length+1'b1;end
     else overflow<=1;
    end
   end
   if(state==TEXT || state==EMIT_HEADER || state==EMIT_RAW)begin
    pace<=pace+1'b1;
    if(pace==3)begin
     rx_valid<=1;
     if(state==EMIT_RAW)begin
      rx_data<=output_index[0]?raw_q[15:8]:raw_q[7:0];
      if(output_index==32759)begin state<=IDLE;output_index<=0;end
      else output_index<=output_index+1'b1;
     end else begin
      rx_data<=8'(response>>(8*(response_length-1-response_index)));
      if(response_index==response_length-1'b1)begin
       response_index<=0;
       if(state==EMIT_HEADER)begin state<=EMIT_RAW;output_index<=0;end
       else state<=IDLE;
      end else response_index<=response_index+1'b1;
     end
    end
   end
   if(state==SPI_WAIT || state==SPI_READ || state==SPI_SETTLE)begin
    capture_deadline<=capture_deadline+1'b1;
    if(capture_deadline>=CAPTURE_TIMEOUT)begin spi_abort<=1;reply("ERR spi_capture_timeout\n",24);end
    else case(state)
     SPI_WAIT:begin
      if(ready_b && (first_packet || ready_low_seen))begin requested<=0;received<=0;state<=SPI_READ;end
      else if(ready_deadline>=READY_TIMEOUT)reply("ERR spi_ready_timeout\n",22);
      else ready_deadline<=ready_deadline+1'b1;
     end
     SPI_READ:begin
      if(spi_tx_valid && spi_tx_ready)requested<=requested+1'b1;
      if(spi_rx_valid)begin received<=received+1'b1;if(received==1055)begin settle<=0;state<=SPI_SETTLE;end end
     end
     SPI_SETTLE:begin
      settle<=settle+1'b1;
      if(settle==3)begin
       transactions<=transactions+1'b1;
       if(force_boundary)begin force_boundary<=0;request_byte<=8'h52;ready_deadline<=0;state<=SPI_WAIT;end
       else if(observed_valid && observed_synthetic==desired_synthetic && commits!=base_commit && observed_samples==16380)begin
        // Actual RF exposure time is unknown to the FPGA proxy, encoded as0.
        response<={"DATA 16380 ",hex8(~whole_crc)," 0\n"};response_length<=22;response_index<=0;
        output_index<=0;pace<=0;state<=EMIT_HEADER;
       end else if(transactions>=95)reply("ERR spi_capture_invalid\n",24);
       else begin request_byte<=desired_synthetic?8'h54:8'h52;ready_deadline<=0;state<=SPI_WAIT;end
      end
     end
     default:;
    endcase
   end
  end
 end
endmodule
