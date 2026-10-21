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
   // Constant CSR indices avoid a Questa 2025.3 vopt indexed-array NBA issue.
   snapshot[12]<=last_window[0];snapshot[25]<=totals[0][31:0];snapshot[26]<=totals[0][63:32];
   snapshot[13]<=last_window[1];snapshot[27]<=totals[1][31:0];snapshot[28]<=totals[1][63:32];
   snapshot[14]<=last_window[2];snapshot[29]<=totals[2][31:0];snapshot[30]<=totals[2][63:32];
   snapshot[15]<=last_window[3];snapshot[31]<=totals[3][31:0];snapshot[32]<=totals[3][63:32];
   snapshot[16]<=last_window[4];snapshot[33]<=totals[4][31:0];snapshot[34]<=totals[4][63:32];
   snapshot[17]<=last_window[5];snapshot[35]<=totals[5][31:0];snapshot[36]<=totals[5][63:32];
   snapshot[18]<=last_window[6];snapshot[37]<=totals[6][31:0];snapshot[38]<=totals[6][63:32];
   snapshot[19]<=last_window[7];snapshot[39]<=totals[7][31:0];snapshot[40]<=totals[7][63:32];
   snapshot[20]<=last_window[8];snapshot[41]<=totals[8][31:0];snapshot[42]<=totals[8][63:32];
   snapshot[21]<=last_window[9];snapshot[43]<=totals[9][31:0];snapshot[44]<=totals[9][63:32];
   snapshot[22]<=last_window[10];snapshot[45]<=totals[10][31:0];snapshot[46]<=totals[10][63:32];
   snapshot[23]<=last_window[11];snapshot[47]<=totals[11][31:0];snapshot[48]<=totals[11][63:32];
   snapshot[24]<=last_window[12];snapshot[49]<=totals[12][31:0];snapshot[50]<=totals[12][63:32];
   snapshot[51]<=last_window[13];snapshot[54]<=totals[13][31:0];snapshot[55]<=totals[13][63:32];
   snapshot[52]<=last_window[14];snapshot[56]<=totals[14][31:0];snapshot[57]<=totals[14][63:32];
   snapshot[53]<=last_window[15];snapshot[58]<=totals[15][31:0];snapshot[59]<=totals[15][63:32];
  end
 end
end
endmodule
