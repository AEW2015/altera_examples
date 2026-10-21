// Frozen, CRC-qualified RF snapshot -> FIR II -> paired raw/filtered CI8 RAM.
// This observation branch cannot stall the original IQ UART transport.
module iq_fir_capture(
 input wire clk,reset,bus_reset,
 input wire cap_write,input wire [14:0] cap_waddr,input wire [15:0] cap_wdata,
 input wire uart_arm,uart_owned,
 input wire [13:0] uart_index,
 output wire uart_enable,uart_available,uart_done,uart_fault,
 output wire [15:0] uart_q,
 output wire [31:0] uart_crc,uart_profile,
 input wire cap_commit,cap_bank,input wire [14:0] cap_samples,
 input wire [31:0] cap_job,cap_crc,cap_rate,cap_frequency,input wire [1:0] cap_source,
 output wire [15:0] fir_data,output wire fir_valid,output wire [1:0] fir_error,
 input wire [55:0] fir_result,input wire fir_result_valid,input wire [1:0] fir_result_error,
 input wire [5:0] avs_address,input wire avs_read,avs_write,
 input wire [31:0] avs_writedata,input wire [3:0] avs_byteenable,
 output logic [31:0] avs_readdata,output wire avs_waitrequest
);
localparam ID=32'h46495231;
(* ramstyle="M20K, no_rw_check" *) logic [15:0] raw_memory[0:16383],filtered_memory[0:16383];
logic armed,ready,done,busy,candidate,candidate_bank,pending,pending_bank;
logic [14:0] written,samples,index,pending_samples;
logic [13:0] cpu_index;
logic [15:0] raw_q,filtered_q;
logic [31:0] job,raw_crc,filtered_crc,rate,frequency,errors,cycles,crc_state;
logic [1:0] source;
logic mode,run_mode;
logic pair_enable,round_nearest,run_round,auto_run;
logic [7:0] profile,run_profile;
logic [31:0] clips;
assign uart_enable=pair_enable;
assign uart_available=!busy && !armed;
assign uart_done=done;
assign uart_fault=!busy && !done && !armed && !pending && !auto_run;
assign uart_q=filtered_q;
assign uart_crc=filtered_crc;
// Versioned descriptor: marker 0x8001, rounding bit8, profile 0=custom,1=boxcar,2=Hamming.
assign uart_profile=32'h80010000 | {23'b0,run_round,run_profile};
logic [4:0] flush_count;
logic [2:0] state;
logic [1:0] pattern_kind;
localparam IDLE=0,PREP=1,SEND=2,WAIT_RESULT=3,COPY_WAIT=4,COPY_WRITE=5,GENERATE=6;
wire [13:0] raw_address=busy?index[13:0]:cpu_index;
wire [15:0] capture_state={8'b0,uart_owned,run_mode,mode,candidate,busy,done,ready,armed};
function automatic [31:0] crc_byte(input [31:0] crc,input [7:0] b);
 reg[31:0] c;begin c=crc^{24'b0,b};for(integer k=0;k<8;k++)c=c[0]?(c>>1)^32'hedb88320:c>>1;crc_byte=c;end
endfunction
function automatic [7:0] quantize(input signed [27:0] value);
 reg signed[28:0] scaled;
 begin scaled=($signed({value[27],value})+(run_round?29'sd16384:29'sd0))>>>15;
 if(scaled>127)quantize=8'h7f;else if(scaled < -128)quantize=8'h80;else quantize=scaled[7:0];end
endfunction
function automatic [15:0] pattern_word(input [1:0] kind,input [13:0] n);
 begin
 if(kind==1)pattern_word=n==0?16'h2040:0;
 else case(n[4:0])
 5'd0:pattern_word=16'h2030;
 5'd1:pattern_word=16'h4f06;
 5'd2:pattern_word=16'h1edc;
 5'd3:pattern_word=16'heb12;
 5'd4:pattern_word=16'h1747;
 5'd5:pattern_word=16'h421b;
 5'd6:pattern_word=16'h0cee;
 5'd7:pattern_word=16'hd61f;
 5'd8:pattern_word=16'h0050;
 5'd9:pattern_word=16'h2a1f;
 5'd10:pattern_word=16'hf4ee;
 5'd11:pattern_word=16'hbe1b;
 5'd12:pattern_word=16'he947;
 5'd13:pattern_word=16'h1512;
 5'd14:pattern_word=16'he2dc;
 5'd15:pattern_word=16'hb106;
 5'd16:pattern_word=16'he030;
 5'd17:pattern_word=16'h11fa;
 5'd18:pattern_word=16'he2c4;
 5'd19:pattern_word=16'hb5ee;
 5'd20:pattern_word=16'he919;
 5'd21:pattern_word=16'h1ee5;
 5'd22:pattern_word=16'hf4b2;
 5'd23:pattern_word=16'hcae1;
 5'd24:pattern_word=16'h0010;
 5'd25:pattern_word=16'h36e1;
 5'd26:pattern_word=16'h0cb2;
 5'd27:pattern_word=16'he2e5;
 5'd28:pattern_word=16'h1719;
 5'd29:pattern_word=16'h4bee;
 5'd30:pattern_word=16'h1ec4;
 5'd31:pattern_word=16'heffa;
 endcase
 end
endfunction
wire [15:0] generated_word=pattern_word(pattern_kind,index[13:0]);
wire observed_write=armed && cap_write && (cap_waddr[13:0]==0 || (candidate && candidate_bank==cap_waddr[14] && cap_waddr[13:0]==written[13:0]));
wire raw_we=observed_write || (busy && state==GENERATE);
wire [13:0] raw_waddr=state==GENERATE?index[13:0]:cap_waddr[13:0];
wire [15:0] raw_wdata=state==GENERATE?generated_word:cap_wdata;
wire signed [28:0] scaled_i=($signed({fir_result[27],fir_result[27:0]})+(run_round?29'sd16384:29'sd0))>>>15;
wire signed [28:0] scaled_q=($signed({fir_result[55],fir_result[55:28]})+(run_round?29'sd16384:29'sd0))>>>15;
wire result_clip=(scaled_i>127 || scaled_i < -128 || scaled_q>127 || scaled_q < -128);
wire [15:0] result_word={quantize($signed(fir_result[55:28])),quantize($signed(fir_result[27:0]))};
assign fir_data=flush_count<16?16'b0:raw_q;
assign fir_valid=state==SEND;
assign fir_error=0;
assign avs_waitrequest=0;
always_comb begin
 avs_readdata=0;
 case(avs_address)
  0:avs_readdata=ID;
  1:avs_readdata={16'b0,capture_state};
  2:avs_readdata={31'b0,mode};
  3:avs_readdata={17'b0,samples};
  4:avs_readdata=job;
  5:avs_readdata={30'b0,source};
  6:avs_readdata={18'b0,cpu_index};
  7:avs_readdata={16'b0,raw_q};
  8:avs_readdata={16'b0,filtered_q};
  9:avs_readdata=cycles;
  10:avs_readdata=errors;
  11:avs_readdata=raw_crc;
  12:avs_readdata=filtered_crc;
  13:avs_readdata=rate;
  14:avs_readdata=frequency;
  17:avs_readdata=clips;
  18:avs_readdata={31'b0,pair_enable};
  19:avs_readdata={31'b0,round_nearest};
  20:avs_readdata={24'b0,profile};
  21:avs_readdata={31'b0,run_round};
  22:avs_readdata={24'b0,run_profile};
  15:avs_readdata=16; // taps; fixed Q15 scale, lane0 I, lane1 Q
 endcase
end
always_ff @(posedge clk)begin
 if(!reset && raw_we)raw_memory[raw_waddr]<=raw_wdata;
 raw_q<=raw_memory[raw_address];
 filtered_q<=filtered_memory[uart_owned?uart_index:cpu_index];
 if(reset)begin
  armed<=0;ready<=0;done<=0;busy<=0;candidate<=0;candidate_bank<=0;pending<=0;pending_bank<=0;pattern_kind<=0;written<=0;pending_samples<=0;
  samples<=0;index<=0;cpu_index<=0;job<=0;source<=0;raw_crc<=0;filtered_crc<=0;rate<=0;frequency<=0;
  pair_enable<=0;round_nearest<=0;run_round<=0;auto_run<=0;profile<=1;run_profile<=1;clips<=0;
  errors<=0;cycles<=0;crc_state<=32'hffffffff;mode<=0;run_mode<=0;flush_count<=0;state<=IDLE;
 end else begin
  if(uart_arm && !busy)begin
   armed<=1;ready<=0;done<=0;candidate<=0;pending<=0;written<=0;auto_run<=1;
  end
  if(auto_run && !uart_owned && !uart_arm && !busy)begin armed<=0;auto_run<=0;candidate<=0;pending<=0;end
  if(armed && cap_write)begin
   if(cap_waddr[13:0]==0)begin candidate<=1;candidate_bank<=cap_waddr[14];written<=1;end
   else if(candidate && candidate_bank==cap_waddr[14] && cap_waddr[13:0]==written[13:0])begin
    written<=written+1'b1;
   end
  end
  if(armed && cap_commit)begin
   pending<=1;pending_samples<=cap_samples;pending_bank<=cap_bank;
   samples<=cap_samples;job<=cap_job;source<=cap_source;raw_crc<=cap_crc;rate<=cap_rate;frequency<=cap_frequency;
  end
  if(pending)begin
   pending<=0;
   if(candidate && candidate_bank==pending_bank && written==pending_samples && pending_samples!=0)begin
    ready<=1;armed<=0;
    if(auto_run)begin
     auto_run<=0;busy<=1;done<=0;index<=0;cycles<=0;clips<=0;flush_count<=0;
     crc_state<=32'hffffffff;run_mode<=1;run_round<=round_nearest;run_profile<=profile;state<=SEND;
    end
   end
   else begin errors<=errors+1'b1;candidate<=0;auto_run<=0;armed<=0;end
  end
  if(!bus_reset && avs_write && avs_byteenable==4'hf && !uart_owned)begin
   if(!busy && !armed)begin
    if(avs_address==18)pair_enable<=avs_writedata[0];
    if(avs_address==19)round_nearest<=avs_writedata[0];
    if(avs_address==20)profile<=avs_writedata[7:0];
   end
   if(avs_address==6 && !busy)cpu_index<=avs_writedata[13:0];
   if(avs_address==2 && !busy)mode<=avs_writedata[0];
   if(avs_address==16 && !busy && (avs_writedata==1 || avs_writedata==2))begin
    armed<=0;ready<=0;done<=0;candidate<=0;pending<=0;busy<=1;state<=GENERATE;pattern_kind<=avs_writedata[1:0];
    index<=0;samples<=128;source<=3;job<=32'hffff0000|avs_writedata;rate<=16000000;frequency<=0;cycles<=0;crc_state<=32'hffffffff;
   end
   if(avs_address==1)begin
    if(avs_writedata[0] && !busy)begin armed<=1;ready<=0;done<=0;candidate<=0;pending<=0;written<=0;end
    if(avs_writedata[2] && !busy)begin armed<=0;ready<=0;done<=0;candidate<=0;pending<=0;end
    if(avs_writedata[1])begin
     if(ready && !busy)begin
      busy<=1;done<=0;index<=0;cycles<=0;clips<=0;flush_count<=0;crc_state<=32'hffffffff;run_mode<=mode;run_round<=round_nearest;run_profile<=profile;
      state<=mode?SEND:COPY_WAIT;
     end else errors<=errors+1'b1;
    end
   end
  end
  if(busy)begin
   cycles<=cycles+1'b1;
   case(state)
    GENERATE:begin
     crc_state<=crc_byte(crc_byte(crc_state,generated_word[7:0]),generated_word[15:8]);
     if(index==127)begin raw_crc<=~crc_byte(crc_byte(crc_state,generated_word[7:0]),generated_word[15:8]);busy<=0;ready<=1;state<=IDLE;end
     else index<=index+1'b1;
    end
    PREP:state<=SEND;
    SEND:state<=WAIT_RESULT;
    WAIT_RESULT:if(fir_result_valid)begin
     if(flush_count<16)begin flush_count<=flush_count+1'b1;state<=flush_count==15?PREP:SEND;end
     else begin
      filtered_memory[index[13:0]]<=result_word;
      if(result_clip)clips<=clips+1'b1;
      crc_state<=crc_byte(crc_byte(crc_state,result_word[7:0]),result_word[15:8]);
      if(index+1==samples)begin done<=1;busy<=0;state<=IDLE;filtered_crc<=~crc_byte(crc_byte(crc_state,result_word[7:0]),result_word[15:8]);end
      else begin index<=index+1'b1;state<=PREP;end
     end
    end
    COPY_WAIT:state<=COPY_WRITE;
    COPY_WRITE:begin
     filtered_memory[index[13:0]]<=raw_q;crc_state<=crc_byte(crc_byte(crc_state,raw_q[7:0]),raw_q[15:8]);
     if(index+1==samples)begin done<=1;busy<=0;state<=IDLE;filtered_crc<=~crc_byte(crc_byte(crc_state,raw_q[7:0]),raw_q[15:8]);end
     else begin index<=index+1'b1;state<=COPY_WAIT;end
    end
   endcase
   if(cycles>20000000 || (fir_result_valid && fir_result_error!=0))begin busy<=0;done<=0;state<=IDLE;errors<=errors+1'b1;end
  end
 end
end
endmodule
