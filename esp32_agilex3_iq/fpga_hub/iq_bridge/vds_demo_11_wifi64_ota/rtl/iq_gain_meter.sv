// CI16 digital manual gain, Q8 unsigned 0..4096 (0..16x).
// Input/output power are summed over retained DDC samples only. No square roots
// or logarithms in hardware. CI16 container full scale is 32768 counts/lane.
module iq_gain_meter (
 input wire clk, reset, start,
 input wire bypass, input wire [12:0] gain_q8,
 input wire [15:0] input_i,input_q, input wire input_valid,
 output logic [15:0] output_i,output_q, output logic output_valid,
 output logic [31:0] samples,pre_peak,pre_rails,post_peak,clips,
 output logic [63:0] pre_power,post_power
);
wire signed [29:0] product_i=$signed(input_i)*$signed({1'b0,gain_q8});
wire signed [29:0] product_q=$signed(input_q)*$signed({1'b0,gain_q8});
wire signed [29:0] scaled_i=(product_i+30'sd128)>>>8;
wire signed [29:0] scaled_q=(product_q+30'sd128)>>>8;
function automatic [15:0] sat(input signed [29:0] x);
 sat=x>32767?16'h7fff:x< -32768?16'h8000:x[15:0];
endfunction
wire [15:0] applied_i=bypass?input_i:sat(scaled_i);
wire [15:0] applied_q=bypass?input_q:sat(scaled_q);
wire [31:0] pre_i2=$signed(input_i)*$signed(input_i);
wire [31:0] pre_q2=$signed(input_q)*$signed(input_q);
wire [31:0] post_i2=$signed(output_i)*$signed(output_i);
wire [31:0] post_q2=$signed(output_q)*$signed(output_q);
wire [31:0] pre_pair=pre_i2+pre_q2,post_pair=post_i2+post_q2;
// The maximum complex power is exactly 2^31; accumulators need at most 46 bits
// for 16384 samples. Separate pipeline stages keep multiply and accumulation apart.
logic [31:0] pending_pre;
logic pending_rail,pending_clip;
always_ff @(posedge clk)begin
 if(reset || start)begin
  output_i<=0;output_q<=0;output_valid<=0;samples<=0;
  pre_peak<=0;pre_rails<=0;post_peak<=0;clips<=0;pre_power<=0;post_power<=0;
  pending_pre<=0;pending_rail<=0;pending_clip<=0;
 end else begin
  output_valid<=input_valid;
  if(input_valid)begin
   output_i<=applied_i;output_q<=applied_q;pending_pre<=pre_pair;
   pending_rail<=input_i==16'h8000 || input_i==16'h7fff || input_q==16'h8000 || input_q==16'h7fff;
   pending_clip<=!bypass && (scaled_i>32767 || scaled_i< -32768 || scaled_q>32767 || scaled_q< -32768);
  end
  if(output_valid)begin
   samples<=samples+1'b1;pre_power<=pre_power+{32'b0,pending_pre};post_power<=post_power+{32'b0,post_pair};
   if(pending_pre>pre_peak)pre_peak<=pending_pre;
   if(post_pair>post_peak)post_peak<=post_pair;
   if(pending_rail)pre_rails<=pre_rails+1'b1;
   if(pending_clip)clips<=clips+1'b1;
  end
 end
end
endmodule
