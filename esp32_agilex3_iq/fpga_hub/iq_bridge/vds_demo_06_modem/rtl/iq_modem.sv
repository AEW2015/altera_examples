// Buffered symbol-rate educational modem. No RF acquisition/timing recovery here.
// Avalon word addresses: 0 ID,1 command/status,2 bits/symbol,3 payload bits,
// 4 index,5 input bit RAM,6 CI16 IQ RAM,7 encoded bit,8 signed LLR,
// 9 decoded bit,10 symbols,11 cycles,12 raw decisions errors,13 decoded errors.
module iq_modem(input logic clk,reset,
 input logic [3:0] avs_address,input logic avs_read,avs_write,
 input logic [31:0] avs_writedata,input logic[3:0] avs_byteenable,
 output logic[31:0] avs_readdata,output wire avs_waitrequest);

localparam MAX_BITS=256,MAX_STEPS=262,MAX_CODED=528,MAX_SYMBOLS=528;
logic source_bits[0:MAX_BITS-1],coded[0:MAX_CODED-1],decoded[0:MAX_STEPS-1];
(* ramstyle="M20K" *) logic [31:0] iq[0:MAX_SYMBOLS-1];
logic[31:0] iq_q;
logic[9:0] iq_q_index;
logic[63:0] decision_word,survivor_q;
logic signed[7:0] llr[0:MAX_CODED-1];
logic signed[31:0] metric[0:63],next_metric[0:63];
(* ramstyle="M20K" *) logic[63:0] survivor[0:MAX_STEPS-1];
logic[9:0] index=0,payload=128,symbols=0,steps=0;
logic[2:0] bps=2;
logic[5:0] enc_state=0,trace_state=0;
logic[31:0] cycles=0,raw_errors=0,decoded_errors=0;
logic done=0,error=0;
typedef enum logic[3:0]{IDLE,ENCODE,MAP,DEMAP_INIT,DEMAP_SCAN,DEMAP_SAVE,VIT_INIT,VIT_STEP,VIT_COPY,TRACE_WAIT,TRACEBACK,COMPARE} state_t;
state_t state=IDLE;
integer pos=0,sym=0,point=0,k=0,vit_state=0,step=0;
logic signed[63:0] min0[0:5],min1[0:5];
wire busy=state!=IDLE;
function automatic logic parity7(input logic[6:0] x);parity7=^x;endfunction
function automatic integer gray_to_binary(input integer g);integer v;begin v=g;for(integer j=1;j<3;j++)v=v^(g>>j);return v;end endfunction
function automatic integer axis(input integer gray,input integer bits_axis,input integer mode);
 integer n,lev,mag;begin
 n=gray_to_binary(gray);lev=2*n-((1<<bits_axis)-1);mag=lev<0?-lev:lev;
 case(mode)
 2:mag=5793;
 4:case(mag)1:mag=2591;default:mag=7772;endcase
 6:case(mag)1:mag=1264;3:mag=3792;5:mag=6320;default:mag=8848;endcase
 default:mag=8192;
 endcase
 return lev<0?-mag:mag;
 end
endfunction
function automatic logic[31:0] mapped(input integer label,input integer mode);
 integer a,b,m;logic signed[15:0] ri,rq;begin
 if(mode==1)begin ri=label==0?8192:-8192;rq=0;end
 else begin m=mode/2;a=label>>m;b=label&((1<<m)-1);ri=16'(axis(a,m,mode));rq=16'(axis(b,m,mode));end
 return {rq,ri};end
endfunction
function automatic integer expected(input integer predecessor,input integer bit_in,input integer poly);
 return ^(((predecessor<<1)|bit_in)&poly);
endfunction
always_comb begin
 avs_readdata=0;
 case(avs_address)
 0:avs_readdata=32'h4d440601;
 1:avs_readdata={29'd0,error,done,busy};
 2:avs_readdata={29'd0,bps};3:avs_readdata={22'd0,payload};4:avs_readdata={22'd0,index};
 5:if(index<MAX_BITS)avs_readdata={31'd0,source_bits[index]};
 6:if(index<MAX_SYMBOLS)avs_readdata=iq_q;
 7:if(index<MAX_CODED)avs_readdata={31'd0,coded[index]};
 8:if(index<MAX_CODED)avs_readdata={{24{llr[index][7]}},llr[index]};
 9:if(index<MAX_STEPS)avs_readdata={31'd0,decoded[index]};
 10:avs_readdata={22'd0,symbols};11:avs_readdata=cycles;
 12:avs_readdata=raw_errors;13:avs_readdata=decoded_errors;
 14:avs_readdata=32'd256;15:avs_readdata=32'd8192;
 endcase
end
wire[9:0] iq_read_index=busy?10'(sym):index;
assign avs_waitrequest=avs_read && avs_address==6 && iq_q_index!=index;
always_ff @(posedge clk)begin : block_memories
 integer tx_label,tx_bit;
 iq_q<=iq[iq_read_index];iq_q_index<=iq_read_index;
 survivor_q<=survivor[pos];
 if(!reset)begin
  if(state==MAP)begin
   tx_label=0;
   for(integer j=0;j<6;j++)if(j<int'(bps))begin
    tx_bit=sym*int'(bps)+j;
    tx_label=(tx_label<<1)|(tx_bit<int'(steps)*2?int'(coded[tx_bit]):0);
   end
   iq[sym]<=mapped(tx_label,int'(bps));
  end else if(avs_write&&!busy&&avs_byteenable==15&&avs_address==6&&index<MAX_SYMBOLS)iq[index]<=avs_writedata;
  if(state==VIT_COPY&&vit_state==0)survivor[step]<=decision_word;
 end
end
always_ff @(posedge clk)begin : engine
 integer reg7,label,base,count,bi,p0,p1,input_bit,out00,out01,out10,out11,diff_i,diff_q;
 logic signed[63:0] distance,reliability;
 logic signed[31:0] score0,score1;
 logic[31:0] candidate;
 if(reset)begin state<=IDLE;index<=0;payload<=128;bps<=2;done<=0;error<=0;cycles<=0;symbols<=0;raw_errors<=0;decoded_errors<=0;end
 else begin
  if(busy)cycles<=cycles+1;
  if(avs_write && !busy && avs_byteenable==4'hf)begin
   case(avs_address)
    2:if(avs_writedata==1||avs_writedata==2||avs_writedata==4||avs_writedata==6)bps<=avs_writedata[2:0];else error<=1;
    3:if(avs_writedata>0&&avs_writedata<=MAX_BITS)payload<=avs_writedata[9:0];else error<=1;
    4:index<=avs_writedata[9:0];
    5:if(index<MAX_BITS)source_bits[index]<=avs_writedata[0];

    1:begin
     done<=0;error<=0;cycles<=0;raw_errors<=0;decoded_errors<=0;
     // Division only by the four static selectable constants; synthesis mux.
     count=(int'(payload)+6)*2;
     case(bps)1:symbols<=10'(count);2:symbols<=10'((count+1)/2);4:symbols<=10'((count+3)/4);6:symbols<=10'((count+5)/6);default:symbols<=0;endcase
     steps<=payload+10'd6;
     if(avs_writedata==1)begin state<=ENCODE;pos<=0;enc_state<=0;end
     else if(avs_writedata==2)begin state<=DEMAP_INIT;sym<=0;end
     else error<=1;
    end
   endcase
  end
  case(state)
   IDLE:;
   ENCODE:begin
    reg7=(int'(enc_state)<<1)|(pos<int'(payload)?int'(source_bits[pos]):0);
    coded[pos*2]<=parity7(7'(reg7)&7'o171);coded[pos*2+1]<=parity7(7'(reg7)&7'o133);
    enc_state<=6'(reg7);pos<=pos+1;
    if(pos==int'(steps)-1)begin state<=MAP;sym<=0;end
   end
   MAP:begin
    label=0;for(integer j=0;j<6;j++)if(j<int'(bps))begin base=sym*int'(bps)+j;label=(label<<1)|(base<int'(steps)*2?int'(coded[base]):0);end
    sym<=sym+1;
    if(sym==int'(symbols)-1)begin state<=IDLE;done<=1;end
   end
   DEMAP_INIT:begin
    for(integer j=0;j<6;j++)begin min0[j]<=64'sh7fffffffffffffff;min1[j]<=64'sh7fffffffffffffff;end
    point<=0;state<=DEMAP_SCAN;
   end
   DEMAP_SCAN:begin
    candidate=mapped(point,int'(bps));
    diff_i=int'($signed(iq_q[15:0]))-int'($signed(candidate[15:0]));
    diff_q=int'($signed(iq_q[31:16]))-int'($signed(candidate[31:16]));
    distance=64'(diff_i)*64'(diff_i)+64'(diff_q)*64'(diff_q);
    for(integer j=0;j<6;j++)if(j<int'(bps))begin
     if((point>>(int'(bps)-1-j))&1)begin if(distance<min1[j])min1[j]<=distance;end
     else if(distance<min0[j])min0[j]<=distance;
    end
    point<=point+1;if(point==(1<<bps)-1)state<=DEMAP_SAVE;
   end
   DEMAP_SAVE:begin
    // Max-log bit reliability; positive favors bit0. Keep minimum nonzero
    // magnitude so high-order QAM reliability survives integer quantization.
    for(integer j=0;j<6;j++)if(j<int'(bps))begin
     base=sym*int'(bps)+j;reliability=(min1[j]-min0[j])>>>18;
     if(reliability>127)reliability=127;else if(reliability< -127)reliability=-127;
     if(base<int'(steps)*2)llr[base]<=8'(reliability);
    end
    sym<=sym+1;
    if(sym==int'(symbols)-1)begin state<=VIT_INIT;vit_state<=0;end else state<=DEMAP_INIT;
   end
   VIT_INIT:begin
    metric[vit_state]<=vit_state==0?0:-32'sd1000000;vit_state<=vit_state+1;
    if(vit_state==63)begin state<=VIT_STEP;vit_state<=0;step<=0;end
   end
   VIT_STEP:begin
    p0=vit_state>>1;p1=p0|32;input_bit=vit_state&1;
    out00=expected(p0,input_bit,'o171);out01=expected(p0,input_bit,'o133);
    out10=expected(p1,input_bit,'o171);out11=expected(p1,input_bit,'o133);
    score0=metric[p0]+(out00?-int'(llr[step*2]):int'(llr[step*2]))+(out01?-int'(llr[step*2+1]):int'(llr[step*2+1]));
    score1=metric[p1]+(out10?-int'(llr[step*2]):int'(llr[step*2]))+(out11?-int'(llr[step*2+1]):int'(llr[step*2+1]));
    next_metric[vit_state]<=score1>score0?score1:score0;
    decision_word[vit_state]<=score1>score0;
    vit_state<=vit_state+1;
    if(vit_state==63)begin state<=VIT_COPY;vit_state<=0;end
   end
   VIT_COPY:begin
    metric[vit_state]<=next_metric[vit_state];vit_state<=vit_state+1;
    if(vit_state==63)begin
     vit_state<=0;step<=step+1;
     if(step==int'(steps)-1)begin state<=TRACE_WAIT;pos<=int'(steps)-1;trace_state<=0;end else state<=VIT_STEP;
    end
   end
   TRACE_WAIT:state<=TRACEBACK;
   TRACEBACK:begin
    decoded[pos]<=trace_state[0];trace_state<={survivor_q[trace_state],trace_state[5:1]};pos<=pos-1;
    if(pos==0)begin state<=COMPARE;pos<=0;end else state<=TRACE_WAIT;
   end
   COMPARE:begin
    if((llr[pos]<0)!=coded[pos])raw_errors<=raw_errors+1;
    if(pos<int'(payload))if(decoded[pos]!=source_bits[pos])decoded_errors<=decoded_errors+1;
    pos<=pos+1;
    if(pos==int'(steps)*2-1)begin state<=IDLE;done<=1;end
   end
   default:state<=IDLE;
  endcase
 end
end
endmodule
