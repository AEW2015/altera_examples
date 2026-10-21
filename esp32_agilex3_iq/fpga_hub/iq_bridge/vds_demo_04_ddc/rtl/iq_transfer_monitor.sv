// Passive one-second measurement windows + atomically snapshotted CPU registers.
module iq_transfer_monitor #(parameter CLOCK_HZ=50000000)(
 input wire clk,reset,bus_reset,
 input wire [2:0] mon_radio_byte,mon_radio_tx,mon_iq_byte,mon_capture_ok,
 input wire mon_host_rx,mon_host_tx,mon_host_iq,mon_host_capture,
 input wire [31:0] mon_command_errors,mon_radio_errors,mon_capture_errors,mon_text_drops,mon_state,
 input wire [5:0] avs_address,input wire avs_read,avs_write,
 input wire [31:0] avs_writedata,input wire [3:0] avs_byteenable,
 output logic [31:0] avs_readdata,output wire avs_waitrequest
);
localparam N=16;
wire [N-1:0] events={mon_radio_tx,mon_host_capture,mon_host_iq,mon_host_tx,mon_host_rx,mon_capture_ok,mon_iq_byte,mon_radio_byte};
logic [31:0] cycles,window_seq;
logic [63:0] ticks;
logic [63:0] totals[0:N-1];
logic [31:0] current_window[0:N-1],last_window[0:N-1];
logic [31:0] snapshot[0:63];
assign avs_waitrequest=1'b0;
always_comb begin
 case(avs_address)
  0:avs_readdata=32'h49514d31; // IQM1
  1:avs_readdata=window_seq;
  2:avs_readdata=CLOCK_HZ;
  default:avs_readdata=snapshot[avs_address];
 endcase
end
always_ff @(posedge clk)begin
 if(reset)begin
  cycles<=0;window_seq<=0;ticks<=0;
  for(integer i=0;i<N;i=i+1)begin totals[i]<=0;current_window[i]<=0;last_window[i]<=0;end
  for(integer i=0;i<64;i=i+1)snapshot[i]<=0;
 end else begin
  ticks<=ticks+1'b1;
  for(integer i=0;i<N;i=i+1)begin
   totals[i]<=totals[i]+64'(events[i]);
   if(cycles==CLOCK_HZ-1)begin last_window[i]<=current_window[i]+32'(events[i]);current_window[i]<=0;end
   else current_window[i]<=current_window[i]+32'(events[i]);
  end
  if(cycles==CLOCK_HZ-1)begin cycles<=0;window_seq<=window_seq+1'b1;end else cycles<=cycles+1'b1;
  // A CPU write takes one coherent snapshot; it cannot alter live counters.
  if(!bus_reset && avs_write && avs_address==3 && avs_byteenable[0] && avs_writedata[0])begin
   snapshot[4]<=window_seq;snapshot[5]<=ticks[31:0];snapshot[6]<=ticks[63:32];snapshot[7]<=mon_state;
   snapshot[60]<=N;snapshot[61]<=1; // Counter count and radio-TX extension feature bit.
   snapshot[8]<=mon_command_errors;snapshot[9]<=mon_radio_errors;snapshot[10]<=mon_capture_errors;snapshot[11]<=mon_text_drops;
   for(integer i=0;i<N;i=i+1)begin
    if(i<13)begin
     snapshot[12+i]<=last_window[i];
     snapshot[25+2*i]<=totals[i][31:0];snapshot[26+2*i]<=totals[i][63:32];
    end else begin
     snapshot[51+i-13]<=last_window[i];
     snapshot[54+2*(i-13)]<=totals[i][31:0];snapshot[55+2*(i-13)]<=totals[i][63:32];
    end
   end
  end
 end
end
endmodule
