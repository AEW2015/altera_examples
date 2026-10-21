// Raw CI8 -> floor16 means -> training-rotated differential coherence.
// Sequential unsigned64 divider; no host DSP and no combinational division.
module iq_preamble(
 input wire clk,reset,bus_reset,
 input wire cap_write,input wire[14:0]cap_waddr,input wire[15:0]cap_wdata,
 input wire cap_commit,cap_bank,input wire[14:0]cap_samples,
 input wire[31:0]cap_job,cap_crc,cap_rate,cap_frequency,input wire[1:0]cap_source,
 input wire[5:0]avs_address,input wire avs_read,avs_write,
 input wire[31:0]avs_writedata,input wire[3:0]avs_byteenable,
 output logic[31:0]avs_readdata,output wire avs_waitrequest
);
 (* ramstyle="M20K, no_rw_check" *) logic[15:0]iq_ram[0:16383];
 (* ramstyle="M20K, no_rw_check" *) logic[15:0]trace_ram[0:16383];
 logic[13:0]ram_address,trace_address,ram_waddr,trace_waddr;
 logic[15:0]ram_q,trace_q,ram_wdata,trace_wdata;logic ram_we,trace_we;
 always_ff @(posedge clk)begin
  ram_q<=iq_ram[ram_address];trace_q<=trace_ram[trace_address];
  if(ram_we)iq_ram[ram_waddr]<=ram_wdata;
  if(trace_we)trace_ram[trace_waddr]<=trace_wdata;
 end
 logic busy,ready,done,armed,loading,detected,bank_seen,candidate_bank,commit_pending;
 logic[31:0]samples,sps,stride,threshold,min_energy,host_index,trace_index,source_filter;
 logic[31:0]cycles,best_start,best_score,candidate_count,errors,written,crc_state;
 logic[31:0]raw_crc,job,source,rate,frequency;
 logic[14:0]pending_samples;logic pending_bank;logic[31:0]pending_crc,pending_job,pending_rate,pending_frequency;
 logic[1:0]pending_source;
 logic[63:0]best_energy,energy;logic signed[31:0]best_r,best_i,sum_r,sum_i;
 logic[31:0]start,last_start,score;logic[5:0]symbol;logic[4:0]offset;
 logic signed[12:0]mean_r,mean_i;
 logic signed[8:0]previous_r,previous_i,current_r,current_i;
 logic signed[17:0]diff_r,diff_i,rot_r,rot_i;
 logic[63:0]div_numerator,div_denominator,div_quotient;logic[64:0]div_remainder;
 logic[6:0]div_count;
 localparam IDLE=0,MEAN_REQ=1,MEAN_WAIT=2,MEAN_ACC=3,DIFF=4,ACC=5,PREP=6,DIVIDE=7,BEST=8,FINISH=9;
 logic[3:0]state;
 logic read_active,read_ready;logic[1:0]read_delay;logic[31:0]read_value;
 wire special_read=avs_address==8 || avs_address==13;
 assign avs_waitrequest=avs_read && special_read && !read_ready;
 wire frozen=busy||armed||loading;
 wire[31:0]span=(sps<<5)-sps+16;
 function automatic[31:0]crc_byte(input[31:0]crc,input[7:0]b);
  logic[31:0]c;begin c=crc^{24'b0,b};for(integer k=0;k<8;k++)c=(c>>1)^(c[0]?32'hedb88320:0);return c;end
 endfunction
 function automatic[1:0]training(input[5:0]n);
  case(n)
   0:training=0;1:training=1;2:training=3;3:training=2;4:training=0;5:training=3;6:training=1;7:training=2;
   8:training=0;9:training=2;10:training=3;11:training=1;12:training=1;13:training=0;14:training=2;15:training=3;
   16:training=3;17:training=0;18:training=1;19:training=2;20:training=0;21:training=3;22:training=2;23:training=1;
   24:training=2;25:training=0;26:training=3;27:training=1;28:training=0;29:training=3;30:training=0;default:training=2;
  endcase
 endfunction
 wire[1:0]delta=training(symbol)-training(symbol-1'b1);
 always_comb begin
  diff_r=$signed(current_r)*$signed(previous_r)+$signed(current_i)*$signed(previous_i);
  diff_i=$signed(current_i)*$signed(previous_r)-$signed(current_r)*$signed(previous_i);
  case(delta)
   0:begin rot_r=diff_r;rot_i=diff_i;end
   1:begin rot_r=-diff_i;rot_i=diff_r;end
   2:begin rot_r=-diff_r;rot_i=-diff_i;end
   default:begin rot_r=diff_i;rot_i=-diff_r;end
  endcase
 end
 wire signed[63:0]square_r=$signed(sum_r)*$signed(sum_r),square_i=$signed(sum_i)*$signed(sum_i);
 wire[63:0]square_diff_r=$signed(diff_r)*$signed(diff_r),square_diff_i=$signed(diff_i)*$signed(diff_i);
 wire[64:0]trial={div_remainder[63:0],div_numerator[63]};
 wire div_bit=trial>={1'b0,div_denominator};
 wire[63:0]quotient_next={div_quotient[62:0],div_bit};
 always_comb begin
  avs_readdata=0;
  case(avs_address)
   0:avs_readdata=32'h50520801;
   1:avs_readdata={26'd0,detected,(errors!=0),armed,done,ready,busy};
   2:avs_readdata=samples;3:avs_readdata=sps;4:avs_readdata=stride;5:avs_readdata=threshold;6:avs_readdata=min_energy;
   7:avs_readdata=host_index;8:avs_readdata=read_value;9:avs_readdata=cycles;
   10:avs_readdata=best_start;11:avs_readdata=best_score;12:avs_readdata=trace_index;13:avs_readdata=read_value;
   14:avs_readdata=candidate_count;15:avs_readdata=errors;16:avs_readdata=raw_crc;17:avs_readdata=job;
   18:avs_readdata=source;19:avs_readdata=rate;20:avs_readdata=frequency;21:avs_readdata=16;22:avs_readdata=1;
   23:avs_readdata=best_energy[31:0];24:avs_readdata=best_r;25:avs_readdata=best_i;26:avs_readdata=best_energy[63:32];
   27:avs_readdata=written;28:avs_readdata=~crc_state;31:avs_readdata=source_filter;
   default:begin end
  endcase
 end
 always_ff @(posedge clk)begin
  ram_we<=0;trace_we<=0;
  if(reset||bus_reset)begin
   busy<=0;ready<=0;done<=0;armed<=0;loading<=0;detected<=0;bank_seen<=0;commit_pending<=0;
   samples<=16380;sps<=160;stride<=4;threshold<=24576;min_energy<=7936;host_index<=0;trace_index<=0;source_filter<=0;
   cycles<=0;best_start<=0;best_score<=0;candidate_count<=0;errors<=0;written<=0;crc_state<=32'hffffffff;
   raw_crc<=0;job<=0;source<=3;rate<=16000000;frequency<=0;best_energy<=0;best_r<=0;best_i<=0;
   state<=IDLE;ram_address<=0;trace_address<=0;read_active<=0;read_ready<=0;read_delay<=0;read_value<=0;
  end else begin
   if(busy)cycles<=cycles+1'b1;
   // Synchronous memory reads complete under an explicit Avalon read stall.
   if(avs_read&&special_read&&!read_active&&(!busy||avs_address==13))begin
    read_active<=1;read_ready<=0;read_delay<=2;
    if(avs_address==8 && !busy)ram_address<=host_index[13:0];
    if(avs_address==13)trace_address<=trace_index[13:0];
   end else if(read_active&&!read_ready)begin
    if(read_delay==1)begin read_value<=avs_address==8 ? {16'd0,ram_q}:{16'd0,trace_q};read_ready<=1;end
    else read_delay<=read_delay-1'b1;
   end
   if(read_ready&&avs_read)begin read_active<=0;read_ready<=0;end
   if(!avs_read)begin read_active<=0;read_ready<=0;end
   // Physical branch is passive and never exerts backpressure on raw transport.
   if(armed&&cap_write&&{30'd0,cap_source}==source_filter)begin
    if(cap_waddr[13:0]==written && written<samples && (!bank_seen||candidate_bank==cap_waddr[14]))begin
     ram_we<=1;ram_waddr<=cap_waddr[13:0];ram_wdata<=cap_wdata;
     written<=written+1'b1;crc_state<=crc_byte(crc_byte(crc_state,cap_wdata[7:0]),cap_wdata[15:8]);
     bank_seen<=1;candidate_bank<=cap_waddr[14];
    end else begin errors<=errors|4;armed<=0;ready<=0;end
   end
   if(armed&&cap_commit&&{30'd0,cap_source}==source_filter)begin
    commit_pending<=1;pending_bank<=cap_bank;pending_samples<=cap_samples;pending_crc<=cap_crc;
    pending_job<=cap_job;pending_rate<=cap_rate;pending_frequency<=cap_frequency;pending_source<=cap_source;
   end
   if(commit_pending)begin
    commit_pending<=0;armed<=0;
    if(bank_seen && candidate_bank==pending_bank && written==samples && {17'd0,pending_samples}==samples && ~crc_state==pending_crc && errors==0)begin
     ready<=1;raw_crc<=pending_crc;job<=pending_job;rate<=pending_rate;frequency<=pending_frequency;source<={30'd0,pending_source};
    end else begin ready<=0;errors<=errors|8;end
   end
   case(state)
    MEAN_REQ:begin ram_address<=14'(start+symbol*sps+offset);state<=MEAN_WAIT;end
    MEAN_WAIT:state<=MEAN_ACC;
    MEAN_ACC:begin
     if(offset==15)begin
      current_r<=($signed(mean_r)+$signed(ram_q[7:0]))>>>4;
      current_i<=($signed(mean_i)+$signed(ram_q[15:8]))>>>4;
      if(symbol==0)begin
       previous_r<=($signed(mean_r)+$signed(ram_q[7:0]))>>>4;previous_i<=($signed(mean_i)+$signed(ram_q[15:8]))>>>4;
       symbol<=1;offset<=0;mean_r<=0;mean_i<=0;state<=MEAN_REQ;
      end else state<=DIFF;
     end else begin mean_r<=mean_r+$signed(ram_q[7:0]);mean_i<=mean_i+$signed(ram_q[15:8]);offset<=offset+1'b1;state<=MEAN_REQ;end
    end
    DIFF:state<=ACC;
    ACC:begin
     sum_r<=sum_r+rot_r;sum_i<=sum_i+rot_i;energy<=energy+square_diff_r+square_diff_i;
     previous_r<=current_r;previous_i<=current_i;
     if(symbol==31)state<=PREP;
     else begin symbol<=symbol+1'b1;offset<=0;mean_r<=0;mean_i<=0;state<=MEAN_REQ;end
    end
    PREP:begin
     if(energy==0 || energy<{32'd0,min_energy})begin score<=0;state<=BEST;end
     else begin div_numerator<=(square_r+square_i)<<15;div_denominator<=(energy<<5)-energy;div_quotient<=0;div_remainder<=0;div_count<=0;state<=DIVIDE;end
    end
    DIVIDE:begin
     div_numerator<=div_numerator<<1;div_quotient<=quotient_next;div_remainder<=div_bit?trial-{1'b0,div_denominator}:trial;
     if(div_count==63)begin score<=quotient_next>32768?32768:quotient_next[31:0];state<=BEST;end
     else div_count<=div_count+1'b1;
    end
    BEST:begin
     trace_we<=1;trace_waddr<=candidate_count[13:0];trace_wdata<=score[15:0];candidate_count<=candidate_count+1'b1;
     if(candidate_count==0 || score>best_score)begin best_start<=start;best_score<=score;best_energy<=energy;best_r<=sum_r;best_i<=sum_i;end
     if(start+stride>last_start)state<=FINISH;
     else begin start<=start+stride;symbol<=0;offset<=0;mean_r<=0;mean_i<=0;sum_r<=0;sum_i<=0;energy<=0;state<=MEAN_REQ;end
    end
    FINISH:begin busy<=0;done<=1;detected<=errors==0 && best_energy!=0 && best_energy>={32'd0,min_energy} && best_score>=threshold;state<=IDLE;end
    default:begin end
   endcase
   if(avs_write)begin
    if(avs_byteenable!=4'hf)begin errors<=errors|2;end
    else if(avs_address==1)begin
     case(avs_writedata)
      1:begin busy<=0;ready<=0;done<=0;armed<=0;loading<=0;detected<=0;errors<=0;commit_pending<=0;state<=IDLE;written<=0;candidate_count<=0;end
      6:begin busy<=0;armed<=0;loading<=0;done<=0;detected<=0;commit_pending<=0;state<=IDLE;end
      2:if(!frozen)begin ready<=0;done<=0;detected<=0;loading<=1;errors<=0;written<=0;host_index<=0;crc_state<=32'hffffffff;end else errors<=errors|1;
      3:if(loading && written==samples && errors==0)begin loading<=0;ready<=1;raw_crc<=~crc_state;source<=3;job<=0;rate<=16000000;frequency<=0;end else begin loading<=0;ready<=0;errors<=errors|4;end
      4:if(ready&&!frozen&&errors==0&&samples>=span)begin
       busy<=1;done<=0;detected<=0;cycles<=0;candidate_count<=0;best_score<=0;best_start<=0;best_energy<=0;best_r<=0;best_i<=0;
       last_start<=samples-span;start<=0;symbol<=0;offset<=0;mean_r<=0;mean_i<=0;sum_r<=0;sum_i<=0;energy<=0;state<=MEAN_REQ;
      end else begin errors<=errors|1;done<=0;detected<=0;end
      5:if(!frozen)begin armed<=1;ready<=0;done<=0;detected<=0;errors<=0;written<=0;crc_state<=32'hffffffff;bank_seen<=0;commit_pending<=0;end else errors<=errors|1;
      default:begin errors<=errors|1;done<=0;detected<=0;end
     endcase
    end else if(avs_address==7)host_index<=avs_writedata;
    else if(avs_address==8)begin
     if(loading&&host_index==written&&written<samples&&written<16384)begin
      ram_we<=1;ram_waddr<=host_index[13:0];ram_wdata<=avs_writedata[15:0];host_index<=host_index+1'b1;written<=written+1'b1;
      crc_state<=crc_byte(crc_byte(crc_state,avs_writedata[7:0]),avs_writedata[15:8]);
     end else begin errors<=errors|4;ready<=0;end
    end else if(frozen)errors<=errors|2;
    else case(avs_address)
     2:if(avs_writedata>=1&&avs_writedata<=16384)begin samples<=avs_writedata;ready<=0;done<=0;end else errors<=errors|2;
     3:if(avs_writedata>=128&&avs_writedata<=240)begin sps<=avs_writedata;done<=0;end else errors<=errors|2;
     4:if(avs_writedata>=1&&avs_writedata<=16)begin stride<=avs_writedata;done<=0;end else errors<=errors|2;
     5:if(avs_writedata<=32768)threshold<=avs_writedata;else errors<=errors|2;
     6:min_energy<=avs_writedata;
     12:if(avs_writedata<16384)trace_index<=avs_writedata;else errors<=errors|2;
     31:if(avs_writedata<=2)source_filter<=avs_writedata;else errors<=errors|2;
     default:errors<=errors|1;
    endcase
   end
  end
 end
endmodule
