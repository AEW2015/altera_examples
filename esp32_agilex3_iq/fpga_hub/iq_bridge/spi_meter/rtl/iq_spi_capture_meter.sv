// IQS1 packet validator + atomic whole-capture CI8 integer meter.
// One accepted byte per clock; start/end delimit the physical SPI transaction.
module iq_spi_capture_meter(
 input logic clk,reset,packet_start,byte_valid,packet_end,
 input logic[7:0] byte_data,
 output logic result_valid,result_synthetic,
 output logic[31:0] result_sequence,commit_count,reject_count,result_samples,
 output logic[63:0] result_power,result_ingress_cycles,
 output logic[31:0] result_peak,result_clip_samples,result_clip_components,
 output logic[7:0] last_error,
 output logic[31:0] result_bytes,result_chunks
);
 function automatic logic[31:0] crc_byte(input logic[31:0] crc,input logic[7:0] value);
  logic[31:0] c;begin c=crc^{24'd0,value};
   for(integer n=0;n<8;n++)c=(c>>1)^(c[0]?32'hedb88320:32'd0);
   crc_byte=c;end
 endfunction
 logic active,overflow,have_capture,have_commit;
 logic[10:0] index;
 logic[31:0] tick,start_tick,magic,pkt_sequence,offset,total,length,payload_crc,header_crc;
 logic[7:0] version,source,flags,header_size;
 logic[31:0] hc,pc;
 logic[63:0] packet_power,capture_power,capture_cycles;
 logic[31:0] packet_peak,packet_clip,packet_component_clip,packet_samples;
 logic[31:0] capture_peak,capture_clip,capture_component_clip,capture_samples;
 logic[31:0] capture_pkt_sequence,next_offset,chunk_count;
 logic capture_synthetic;
 logic[15:0] i_square;
 logic i_clip;
 logic[31:0] count;
 wire payload_byte=index>=32 && {22'd0,index}<({1'b0,length}+33'd32);
 wire signed[15:0] signed_byte={{8{byte_data[7]}},byte_data};
 wire[15:0] square=unsigned'(signed_byte*signed_byte);
 wire component_clip=byte_data==8'h80 || byte_data==8'h7f;
 wire[16:0] pair_power={1'b0,i_square}+{1'b0,square};
 wire[63:0] merged_power=(offset==0?64'd0:capture_power)+packet_power;
 wire[63:0] merged_cycles=(offset==0?64'd0:capture_cycles)+{32'd0,(tick-start_tick)};
 wire[31:0] merged_peak=packet_peak>(offset==0?0:capture_peak)?packet_peak:(offset==0?0:capture_peak);
 wire[31:0] merged_clip=(offset==0?0:capture_clip)+packet_clip;
 wire[31:0] merged_component_clip=(offset==0?0:capture_component_clip)+packet_component_clip;
 wire[31:0] merged_samples=(offset==0?0:capture_samples)+packet_samples;
 wire[31:0] merged_chunks=(offset==0?0:chunk_count)+1;
 // Signed modulo32 forward window: permits wrap, rejects any backwards/replayed capture.
 wire signed[31:0] sequence_advance=$signed(pkt_sequence-result_sequence);
 logic[7:0] error;
 always_comb begin
  error=0;
  if(!active || count!=1056 || overflow)error=1; // truncation/overflow
  else if((~hc)!=header_crc)error=2;
  else if(magic!=32'h31535149 || version!=1 || source!=2 || header_size!=32 ||
     (flags&8'hfc)!=0 || total!=32760 || length!=((offset+1024>total)?total-offset:1024) ||
     offset>=total || offset[9:0]!=0 || length==0 || length>1024 || length[0] ||
     flags[0]!=(offset+length==total))error=3;
  else if((~pc)!=payload_crc)error=4;
  else if(offset!=0 && (!have_capture || pkt_sequence!=capture_pkt_sequence ||
     flags[1]!=capture_synthetic || offset!=next_offset))error=5;
  else if(offset==0 && have_commit && sequence_advance<=0)error=5;
 end
 always_ff @(posedge clk)begin
  tick<=tick+1'b1;
  if(reset)begin
   active<=0;overflow<=0;have_capture<=0;have_commit<=0;index<=0;count<=0;tick<=0;start_tick<=0;
   hc<=~32'd0;pc<=~32'd0;result_valid<=0;result_synthetic<=0;result_sequence<=0;
   commit_count<=0;reject_count<=0;last_error<=0;result_samples<=0;result_power<=0;
   result_peak<=0;result_clip_samples<=0;result_clip_components<=0;
   result_ingress_cycles<=0;result_bytes<=0;result_chunks<=0;
   packet_power<=0;packet_peak<=0;packet_clip<=0;packet_component_clip<=0;packet_samples<=0;
   capture_power<=0;capture_peak<=0;capture_clip<=0;capture_component_clip<=0;capture_samples<=0;
   capture_pkt_sequence<=0;next_offset<=0;chunk_count<=0;capture_cycles<=0;capture_synthetic<=0;
   i_square<=0;i_clip<=0;magic<=0;version<=0;source<=0;flags<=0;header_size<=0;
   pkt_sequence<=0;offset<=0;total<=0;length<=0;payload_crc<=0;header_crc<=0;
  end else begin
   if(packet_start)begin
    if(active)begin reject_count<=reject_count+1'b1;last_error<=1;have_capture<=0;end
    active<=1;overflow<=0;index<=0;count<=0;start_tick<=tick;
    hc<=~32'd0;pc<=~32'd0;packet_power<=0;packet_peak<=0;packet_clip<=0;
    packet_component_clip<=0;packet_samples<=0;i_square<=0;i_clip<=0;
    result_valid<=0;
   end
   if(byte_valid && active)begin
    count<=count+1'b1;
    if(count>=1056)overflow<=1;
    if(index<28)hc<=crc_byte(hc,byte_data);
    case(index)
     0,1,2,3:magic[index*8+:8]<=byte_data;
     4:version<=byte_data;5:source<=byte_data;6:flags<=byte_data;7:header_size<=byte_data;
     8,9,10,11:pkt_sequence[(index-8)*8+:8]<=byte_data;
     12,13,14,15:offset[(index-12)*8+:8]<=byte_data;
     16,17,18,19:total[(index-16)*8+:8]<=byte_data;
     20,21,22,23:length[(index-20)*8+:8]<=byte_data;
     24,25,26,27:payload_crc[(index-24)*8+:8]<=byte_data;
     28,29,30,31:header_crc[(index-28)*8+:8]<=byte_data;
     default:;
    endcase
    if(index<1056 && payload_byte)begin
     pc<=crc_byte(pc,byte_data);
     if(!index[0])begin i_square<=square;i_clip<=component_clip;end
     else begin
      packet_power<=packet_power+pair_power;
      if(pair_power>packet_peak)packet_peak<=pair_power;
      packet_samples<=packet_samples+1'b1;
      packet_clip<=packet_clip+(i_clip || component_clip);
      packet_component_clip<=packet_component_clip+{31'd0,i_clip}+{31'd0,component_clip};
     end
    end else if(index>=32 && index<1056 && byte_data!=0)overflow<=1; // padded tail must be zero
    if(index<2047)index<=index+1'b1;else overflow<=1;
   end
   if(packet_end)begin
    active<=0;
    if(error!=0)begin
     reject_count<=reject_count+1'b1;last_error<=error;have_capture<=0;result_valid<=0;
    end else begin
     // A new offset0 replaces an incomplete prior capture, never its measurements.
     if(offset==0 && have_capture)begin reject_count<=reject_count+1'b1;last_error<=5;end
     else last_error<=0;
     capture_pkt_sequence<=pkt_sequence;capture_synthetic<=flags[1];next_offset<=offset+length;
     capture_power<=merged_power;capture_peak<=merged_peak;capture_clip<=merged_clip;
     capture_component_clip<=merged_component_clip;capture_samples<=merged_samples;
     capture_cycles<=merged_cycles;chunk_count<=merged_chunks;
     have_capture<=!flags[0];
     if(flags[0])begin
      result_valid<=1;have_commit<=1;result_synthetic<=flags[1];result_sequence<=pkt_sequence;
      result_samples<=merged_samples;result_power<=merged_power;result_peak<=merged_peak;
      result_clip_samples<=merged_clip;result_clip_components<=merged_component_clip;
      result_ingress_cycles<=merged_cycles;result_bytes<=total;result_chunks<=merged_chunks;
      commit_count<=commit_count+1'b1;
     end
    end
   end
  end
 end
endmodule
