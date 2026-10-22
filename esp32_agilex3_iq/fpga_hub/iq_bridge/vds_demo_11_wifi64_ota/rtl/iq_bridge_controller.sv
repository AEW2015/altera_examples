(* altera_ip="atum.local:ip:iq_bridge_controller:1.0" *)
module iq_bridge_controller #(
 parameter CLOCK_HZ=50000000, MAX_SAMPLES=16384, CAPTURE_TIMEOUT=250000000
)(
 (* altera_interface="altera.com:interfaces:altera_clock:1.0 in clk", altera_intf_port="clk clk clk" *) input logic clk,
 (* altera_interface="altera.com:interfaces:altera_reset:1.0 in reset", altera_intf_port="reset reset reset" *) input logic reset,
 (* altera_interface="atum.local:conduit:host_bytes:1.0 manager host_link", altera_intf_port="host_link baud host_baud", altera_port="clockref:clk, resetref:reset" *) output logic [31:0] host_baud,
 (* altera_interface="atum.local:conduit:host_bytes:1.0 manager host_link", altera_intf_port="host_link rx_valid host_valid" *) input logic host_valid,
 (* altera_interface="atum.local:conduit:host_bytes:1.0 manager host_link", altera_intf_port="host_link rx_data host_byte" *) input logic [7:0] host_byte,
 (* altera_interface="atum.local:conduit:host_bytes:1.0 manager host_link", altera_intf_port="host_link rx_error host_frame_error" *) input logic host_frame_error,
 (* altera_interface="atum.local:conduit:host_bytes:1.0 manager host_link", altera_intf_port="host_link tx_start host_start" *) output logic host_start,
 (* altera_interface="atum.local:conduit:host_bytes:1.0 manager host_link", altera_intf_port="host_link tx_data host_out" *) output logic [7:0] host_out,
 (* altera_interface="atum.local:conduit:host_bytes:1.0 manager host_link", altera_intf_port="host_link tx_busy host_busy" *) input logic host_busy,
 (* altera_interface="atum.local:conduit:host_bytes:1.0 manager host_link", altera_intf_port="host_link tx_done host_done" *) input logic host_done,
 (* altera_interface="atum.local:conduit:radio_bytes:1.0 manager radio_link", altera_intf_port="radio_link fast radio_fast", altera_port="clockref:clk, resetref:reset" *) output logic [2:0] radio_fast,
 (* altera_interface="atum.local:conduit:radio_bytes:1.0 manager radio_link", altera_intf_port="radio_link rx_valid rv" *) input logic [2:0] rv,
 (* altera_interface="atum.local:conduit:radio_bytes:1.0 manager radio_link", altera_intf_port="radio_link rx_data radio_rx_data" *) input logic [23:0] radio_rx_data,
 (* altera_interface="atum.local:conduit:radio_bytes:1.0 manager radio_link", altera_intf_port="radio_link rx_error re" *) input logic [2:0] re,
 (* altera_interface="atum.local:conduit:radio_bytes:1.0 manager radio_link", altera_intf_port="radio_link tx_start ts" *) output logic [2:0] ts,
 (* altera_interface="atum.local:conduit:radio_bytes:1.0 manager radio_link", altera_intf_port="radio_link tx_data radio_tx_data" *) output logic [23:0] radio_tx_data,
 (* altera_interface="atum.local:conduit:radio_bytes:1.0 manager radio_link", altera_intf_port="radio_link tx_busy tbusy" *) input logic [2:0] tbusy,
 (* altera_interface="atum.local:conduit:radio_bytes:1.0 manager radio_link", altera_intf_port="radio_link tx_done tdone" *) input logic [2:0] tdone,
 (* altera_interface="atum.local:conduit:capture_memory:1.0 manager capture_memory", altera_intf_port="capture_memory write mem_write", altera_port="clockref:clk, resetref:reset" *) output logic mem_write,
 (* altera_interface="atum.local:conduit:capture_memory:1.0 manager capture_memory", altera_intf_port="capture_memory waddr mem_waddr" *) output logic [14:0] mem_waddr,
 (* altera_interface="atum.local:conduit:capture_memory:1.0 manager capture_memory", altera_intf_port="capture_memory wdata mem_wdata" *) output logic [15:0] mem_wdata,
 (* altera_interface="atum.local:conduit:capture_memory:1.0 manager capture_memory", altera_intf_port="capture_memory raddr mem_raddr" *) output logic [14:0] mem_raddr,
 (* altera_interface="atum.local:conduit:capture_memory:1.0 manager capture_memory", altera_intf_port="capture_memory q mem_q" *) input logic [15:0] mem_q,
 (* altera_interface="atum.local:conduit:fir_capture:1.0 manager fir_capture", altera_intf_port="fir_capture write cap_write", altera_port="clockref:clk, resetref:reset" *) output wire cap_write,
 (* altera_interface="atum.local:conduit:fir_capture:1.0 manager fir_capture", altera_intf_port="fir_capture waddr cap_waddr" *) output wire [14:0] cap_waddr,
 (* altera_interface="atum.local:conduit:fir_capture:1.0 manager fir_capture", altera_intf_port="fir_capture wdata cap_wdata" *) output wire [15:0] cap_wdata,
 (* altera_interface="atum.local:conduit:fir_capture:1.0 manager fir_capture", altera_intf_port="fir_capture commit cap_commit" *) output wire cap_commit,
 (* altera_interface="atum.local:conduit:fir_capture:1.0 manager fir_capture", altera_intf_port="fir_capture bank cap_bank" *) output wire cap_bank,
 (* altera_interface="atum.local:conduit:fir_capture:1.0 manager fir_capture", altera_intf_port="fir_capture samples cap_samples" *) output wire [14:0] cap_samples,
 (* altera_interface="atum.local:conduit:fir_capture:1.0 manager fir_capture", altera_intf_port="fir_capture job cap_job" *) output wire [31:0] cap_job,
 (* altera_interface="atum.local:conduit:fir_capture:1.0 manager fir_capture", altera_intf_port="fir_capture crc cap_crc" *) output wire [31:0] cap_crc,
 (* altera_interface="atum.local:conduit:fir_capture:1.0 manager fir_capture", altera_intf_port="fir_capture rate cap_rate" *) output wire [31:0] cap_rate,
 (* altera_interface="atum.local:conduit:fir_capture:1.0 manager fir_capture", altera_intf_port="fir_capture frequency cap_frequency" *) output wire [31:0] cap_frequency,
 (* altera_interface="atum.local:conduit:fir_capture:1.0 manager fir_capture", altera_intf_port="fir_capture source cap_source" *) output wire [1:0] cap_source,
 (* altera_interface="atum.local:conduit:fir_uart:1.0 manager fir_uart", altera_intf_port="fir_uart enable uart_enable", altera_port="clockref:clk, resetref:reset" *) input wire uart_enable,
 (* altera_interface="atum.local:conduit:fir_uart:1.0 manager fir_uart", altera_intf_port="fir_uart available uart_available", altera_port="clockref:clk, resetref:reset" *) input wire uart_available,
 (* altera_interface="atum.local:conduit:fir_uart:1.0 manager fir_uart", altera_intf_port="fir_uart done uart_done", altera_port="clockref:clk, resetref:reset" *) input wire uart_done,
 (* altera_interface="atum.local:conduit:fir_uart:1.0 manager fir_uart", altera_intf_port="fir_uart fault uart_fault", altera_port="clockref:clk, resetref:reset" *) input wire uart_fault,
 (* altera_interface="atum.local:conduit:fir_uart:1.0 manager fir_uart", altera_intf_port="fir_uart q uart_q", altera_port="clockref:clk, resetref:reset" *) input wire [15:0] uart_q,
 (* altera_interface="atum.local:conduit:fir_uart:1.0 manager fir_uart", altera_intf_port="fir_uart crc uart_crc", altera_port="clockref:clk, resetref:reset" *) input wire [31:0] uart_crc,
 (* altera_interface="atum.local:conduit:fir_uart:1.0 manager fir_uart", altera_intf_port="fir_uart profile uart_profile", altera_port="clockref:clk, resetref:reset" *) input wire [31:0] uart_profile,
 (* altera_interface="atum.local:conduit:fir_uart:1.0 manager fir_uart", altera_intf_port="fir_uart arm uart_arm", altera_port="clockref:clk, resetref:reset" *) output logic uart_arm,
 (* altera_interface="atum.local:conduit:fir_uart:1.0 manager fir_uart", altera_intf_port="fir_uart owned uart_owned", altera_port="clockref:clk, resetref:reset" *) output wire uart_owned,
 (* altera_interface="atum.local:conduit:fir_uart:1.0 manager fir_uart", altera_intf_port="fir_uart index uart_index", altera_port="clockref:clk, resetref:reset" *) output wire [13:0] uart_index,
 (* altera_interface="atum.local:conduit:iq_monitor:1.0 manager telemetry", altera_intf_port="telemetry radio_byte mon_radio_byte", altera_port="clockref:clk, resetref:reset" *) output logic [2:0] mon_radio_byte,
 (* altera_interface="atum.local:conduit:iq_monitor:1.0 manager telemetry", altera_intf_port="telemetry radio_tx mon_radio_tx" *) output logic [2:0] mon_radio_tx,
 (* altera_interface="atum.local:conduit:iq_monitor:1.0 manager telemetry", altera_intf_port="telemetry iq_byte mon_iq_byte" *) output logic [2:0] mon_iq_byte,
 (* altera_interface="atum.local:conduit:iq_monitor:1.0 manager telemetry", altera_intf_port="telemetry capture_ok mon_capture_ok" *) output logic [2:0] mon_capture_ok,
 (* altera_interface="atum.local:conduit:iq_monitor:1.0 manager telemetry", altera_intf_port="telemetry host_rx mon_host_rx" *) output logic mon_host_rx,
 (* altera_interface="atum.local:conduit:iq_monitor:1.0 manager telemetry", altera_intf_port="telemetry host_tx mon_host_tx" *) output logic mon_host_tx,
 (* altera_interface="atum.local:conduit:iq_monitor:1.0 manager telemetry", altera_intf_port="telemetry host_iq mon_host_iq" *) output logic mon_host_iq,
 (* altera_interface="atum.local:conduit:iq_monitor:1.0 manager telemetry", altera_intf_port="telemetry host_capture mon_host_capture" *) output logic mon_host_capture,
 (* altera_interface="atum.local:conduit:iq_monitor:1.0 manager telemetry", altera_intf_port="telemetry command_errors mon_command_errors" *) output logic [31:0] mon_command_errors,
 (* altera_interface="atum.local:conduit:iq_monitor:1.0 manager telemetry", altera_intf_port="telemetry radio_errors mon_radio_errors" *) output logic [31:0] mon_radio_errors,
 (* altera_interface="atum.local:conduit:iq_monitor:1.0 manager telemetry", altera_intf_port="telemetry capture_errors mon_capture_errors" *) output logic [31:0] mon_capture_errors,
 (* altera_interface="atum.local:conduit:iq_monitor:1.0 manager telemetry", altera_intf_port="telemetry text_drops mon_text_drops" *) output logic [31:0] mon_text_drops,
 (* altera_interface="atum.local:conduit:iq_monitor:1.0 manager telemetry", altera_intf_port="telemetry state mon_state" *) output logic [31:0] mon_state
);
logic[63:0] ticks;
function automatic[31:0] crc_byte(input[31:0] crc,input[7:0] b);
 reg[31:0] c;begin c=crc^{24'b0,b};for(integer k=0;k<8;k=k+1)c=c[0]?(c>>1)^32'hedb88320:c>>1;crc_byte=c;end
endfunction
logic[31:0] new_host_baud;
logic[2:0] tpush,tpop,tfull,tempty;
wire[7:0] rb[0:2],tq[0:2];logic[7:0] tbyte[0:2],tinput[0:2];logic[1:0] tphase[0:2];
wire[7:0] tcount[0:2],thigh[0:2];
genvar g;generate for(g=0;g<3;g=g+1)begin:radios
 assign rb[g]=radio_rx_data[8*g+:8];
 assign radio_tx_data[8*g+:8]=tbyte[g];
 sync_fifo #(.WIDTH(8),.DEPTH(128)) tf(clk,reset,tpush[g],tpop[g],tinput[g],tq[g],tcount[g],tfull[g],tempty[g],thigh[g]);
end endgenerate
// Host command: IQBC,opcode,source,arg16,job32,value32,CRC32; exactly20bytes.
logic[7:0] command[0:15];logic[4:0] cmd_index;
logic[31:0] cmd_crc,cmd_rx_crc;logic[31:0] command_errors,radio_errors,protocol_errors,text_drops;
logic[31:0] config_rate[0:2],config_frequency[0:2];
wire[7:0] opcode=command[4],source=command[5];
wire[15:0] arg={command[7],command[6]};
wire[31:0] job={command[11],command[10],command[9],command[8]};
wire[31:0] value={command[15],command[14],command[13],command[12]};
// Control replies are one-deep; Python waits for each control transaction.
logic control_pending;logic[7:0] control_kind,control_source;
logic[31:0] control_job,control_error;
// Double-buffered sample memory: synchronous read, one write port.
logic[1:0] bank_ready;logic armed,binary_active,write_bank;logic[1:0] owner;
logic[31:0] capture_rate,capture_frequency;
logic[31:0] requested_samples,active_job,received_bytes,raw_crc,expected_crc,header_us,deadline;
logic[7:0] low_i;logic[63:0] receipt_tick;
logic[31:0] bank_job[0:1],bank_samples[0:1],bank_rate[0:1],bank_frequency[0:1],bank_crc[0:1],bank_us[0:1];
logic[1:0] bank_source[0:1];logic[63:0] bank_first[0:1],bank_last[0:1];
// Bounded text queues. During payload, every byte is binary, including newlines.
localparam integer TEXT_DEPTH=4;
logic[7:0] line[0:2][0:255],queued[0:2][0:TEXT_DEPTH-1][0:255];
logic[7:0] line_len[0:2],queued_len[0:2][0:TEXT_DEPTH-1];
logic[1:0] text_head[0:2],text_tail[0:2];logic[2:0] text_count[0:2];
logic[2:0] text_pending,line_overflow,text_push,text_pop,text_drop;
wire[2:0] text_drop_count={2'b0,text_drop[0]}+{2'b0,text_drop[1]}+{2'b0,text_drop[2]};
logic[2:0] header_active,header_bad;logic[1:0] header_field[0:2];logic[3:0] hex_digits[0:2];
logic[31:0] parsed_count[0:2],parsed_crc[0:2],parsed_us[0:2];
function automatic[4:0] hex(input[7:0] b);
 if(b>="0"&&b<="9")hex={1'b0,b[3:0]};else if(b>="a"&&b<="f")hex=5'(32'(b)-97+10);else if(b>="A"&&b<="F")hex=5'(32'(b)-65+10);else hex=31;
endfunction
// Response:64byte IQB1 header + payload + CRC32(header+payload).
// Header:<4sBBBB8IQQQ>. See Python protocol for names and strict validation.
logic pair_lock,capture_pair,tx_pair;logic[1:0] bank_pair;
logic[31:0] pair_wait;
logic[2:0] output_state;logic tx_bank,round_robin;
logic[7:0] tx_kind,tx_source;logic[31:0] tx_job,tx_samples,tx_rate,tx_frequency,tx_raw_crc,tx_us,tx_error,tx_length;
logic[63:0] tx_first,tx_last,tx_aux;
logic[31:0] output_index,output_crc;logic[7:0] next_out;
wire[31:0] total_bytes=64+tx_length+4;
wire[31:0] payload_index=output_index-64;
assign uart_owned=pair_lock;
assign uart_index=payload_index[14:1];
wire [15:0] output_word=tx_kind==6?uart_q:mem_q;
assign mem_raddr=$clog2(2*MAX_SAMPLES)'((tx_bank?MAX_SAMPLES:0)+(payload_index>>1));
function automatic[7:0] header_byte(input[5:0] n);
 reg[31:0] w;reg[63:0] q;
 begin
 if(n<4)case(n)0:header_byte="I";1:header_byte="Q";2:header_byte="B";default:header_byte="1";endcase
 else if(n==4)header_byte=1;else if(n==5)header_byte=tx_kind;else if(n==6)header_byte=tx_source;else if(n==7)header_byte=0;
 else if(n<40)begin
 case(n[5:2])2:w=tx_job;3:w=tx_samples;4:w=tx_rate;5:w=tx_frequency;6:w=tx_raw_crc;7:w=tx_us;8:w=tx_error;default:w=tx_length;endcase
 header_byte=8'(w>>(8*n[1:0]));end
 else begin case(n[5:3])5:q=tx_first;6:q=tx_last;default:q=tx_aux;endcase header_byte=8'(q>>(8*n[2:0]));end
 end
endfunction
always_comb begin
 if(output_index<64)next_out=header_byte(output_index[5:0]);
 else if(output_index<64+tx_length)begin
  if(tx_kind==1 || tx_kind==6)next_out=payload_index[0]?output_word[15:8]:output_word[7:0];
  else next_out=queued[tx_source[1:0]][text_head[tx_source[1:0]]][payload_index[7:0]];
 end else next_out=8'((~output_crc)>>(8*(output_index-64-tx_length)));
end
// The exporting head remains occupied until its final CRC byte completes.
// A simultaneous pop permits enqueue even at full occupancy without losing order.
for(genvar q=0;q<3;q=q+1)begin:text_queue_events
 assign text_pending[q]=text_count[q]!=0;
 assign text_pop[q]=output_state==2 && host_done && output_index+1==total_bytes && tx_kind==3 && tx_source==q;
 wire newline=rv[q] && !(binary_active && owner==2'(q)) && rb[q]==10;
 wire candidate=newline && !(armed && owner==2'(q) && header_active[q]) && line_len[q]!=0 && !line_overflow[q];
 assign text_push[q]=candidate && (text_count[q]<TEXT_DEPTH || text_pop[q]);
 assign text_drop[q]=newline && (line_overflow[q] || (candidate && !text_push[q]));
end
assign cap_write=mem_write;
assign cap_waddr=mem_waddr;
assign cap_wdata=mem_wdata;
assign cap_commit=|mon_capture_ok;
assign cap_bank=write_bank;
assign cap_samples=requested_samples[14:0];
assign cap_job=active_job;
assign cap_crc=expected_crc;
assign cap_rate=capture_rate;
assign cap_frequency=capture_frequency;
assign cap_source=owner;
// Passive fanout only: none of these signals feeds the IQ state machine.
assign mon_radio_byte=rv;
assign mon_radio_tx=tdone;
for(genvar m=0;m<3;m=m+1)begin:monitor_taps
 assign mon_iq_byte[m]=rv[m] && binary_active && owner==2'(m);
end
assign mon_host_rx=host_valid;
assign mon_host_tx=host_done;
assign mon_host_iq=output_state==2 && host_done && tx_kind==1 && output_index>=64 && output_index<64+tx_length;
assign mon_host_capture=output_state==2 && host_done && tx_kind==1 && output_index+1==total_bytes;
assign mon_command_errors=command_errors;
assign mon_radio_errors=radio_errors;
assign mon_capture_errors=protocol_errors;
assign mon_text_drops=text_drops;
assign mon_state={26'b0,binary_active,armed,bank_ready,owner};
always_ff @(posedge clk)begin
 mon_capture_ok<=0;uart_arm<=0;
 host_start<=0;mem_write<=0;tpush<=0;tpop<=0;ts<=0;
 if(reset)begin
 pair_lock<=0;capture_pair<=0;tx_pair<=0;bank_pair<=0;pair_wait<=0;
 ticks<=0;host_baud<=2000000;new_host_baud<=2000000;radio_fast<=0;cmd_index<=0;cmd_crc<=32'hffffffff;cmd_rx_crc<=0;
 command_errors<=0;radio_errors<=0;protocol_errors<=0;text_drops<=0;control_pending<=0;
 armed<=0;binary_active<=0;bank_ready<=0;write_bank<=0;owner<=0;deadline<=0;
 output_state<=0;output_index<=0;output_crc<=32'hffffffff;round_robin<=0;tx_kind<=0;tx_source<=0;tx_length<=0;tx_bank<=0;
 line_overflow<=0;header_active<=0;header_bad<=0;
 for(integer s=0;s<3;s=s+1)begin line_len[s]<=0;text_head[s]<=0;text_tail[s]<=0;text_count[s]<=0;header_field[s]<=0;hex_digits[s]<=0;parsed_count[s]<=0;parsed_crc[s]<=0;parsed_us[s]<=0;tphase[s]<=0;config_rate[s]<=16000000;config_frequency[s]<=2417000000;end
 end else begin
 ticks<=ticks+1'b1;
 text_drops<=text_drops+{29'b0,text_drop_count};
 for(integer q=0;q<3;q=q+1)begin
  case({text_push[q],text_pop[q]})
   2'b10:text_count[q]<=text_count[q]+1'b1;
   2'b01:text_count[q]<=text_count[q]-1'b1;
   default:begin end
  endcase
  if(text_pop[q])text_head[q]<=text_head[q]+1'b1;
  if(text_push[q])begin
   for(integer k=0;k<256;k=k+1)queued[q][text_tail[q]][k]<=line[q][k];
   queued_len[q][text_tail[q]]<=line_len[q];text_tail[q]<=text_tail[q]+1'b1;
  end
 end
 // TX queues permit full-duplex host readout and radio commands.
 for(integer s=0;s<3;s=s+1)begin
  case(tphase[s])
   0:if(!tempty[s]&&!tbusy[s])tphase[s]<=1;
   1:begin tbyte[s]<=tq[s];ts[s]<=1;tpop[s]<=1;tphase[s]<=2;end
   2:if(tdone[s])tphase[s]<=0;
   default:tphase[s]<=0;
  endcase
  if(re[s])radio_errors<=radio_errors+1'b1;
 end
 if(host_frame_error)command_errors<=command_errors+1'b1;
 if(host_valid)begin
  if(cmd_index<4)begin
   if(host_byte==((cmd_index==0)?"I":(cmd_index==1)?"Q":(cmd_index==2)?"B":"C"))begin
    command[cmd_index[3:0]]<=host_byte;cmd_crc<=crc_byte(cmd_crc,host_byte);cmd_index<=cmd_index+1'b1;
   end else begin cmd_index<=host_byte=="I"?1:0;cmd_crc<=host_byte=="I"?crc_byte(32'hffffffff,host_byte):32'hffffffff;command[0]<=host_byte;end
  end else if(cmd_index<16)begin command[cmd_index[3:0]]<=host_byte;cmd_crc<=crc_byte(cmd_crc,host_byte);cmd_index<=cmd_index+1'b1;end
  else if(cmd_index<19)begin cmd_rx_crc[8*(cmd_index-16)+:8]<=host_byte;cmd_index<=cmd_index+1'b1;end
  else begin
   cmd_index<=0;cmd_crc<=32'hffffffff;
   if({host_byte,cmd_rx_crc[23:0]}!=(~cmd_crc))command_errors<=command_errors+1'b1;
   else if(source>2 || (control_pending && opcode!=1))begin command_errors<=command_errors+1'b1;end
   else case(opcode)
    0:begin control_pending<=1;control_kind<=2;control_source<=source;control_job<=job;control_error<=0;end
    1:if(!tfull[source[1:0]])begin tpush[source[1:0]]<=1;tinput[source[1:0]]<=arg[7:0];end else command_errors<=command_errors+1'b1;
    2:if((value==115200||value==2000000)&&!tbusy[source[1:0]]&&tempty[source[1:0]])begin radio_fast[source[1:0]]<=value==2000000;control_pending<=1;control_kind<=2;control_source<=source;control_job<=job;control_error<=0;end else command_errors<=command_errors+1'b1;
    3:begin
     control_pending<=1;control_source<=source;control_job<=job;
     if(!armed && !pair_lock && (!uart_enable || (bank_ready==0 && uart_available)) && bank_ready!=3 && value>0 && value<=MAX_SAMPLES)begin
      capture_pair<=uart_enable;if(uart_enable)begin pair_lock<=1;uart_arm<=1;end
      write_bank<=bank_ready[0];armed<=1;binary_active<=0;owner<=source[1:0];requested_samples<=value;active_job<=job;capture_rate<=config_rate[source[1:0]];capture_frequency<=config_frequency[source[1:0]];deadline<=CAPTURE_TIMEOUT;
      header_active[source[1:0]]<=0;line_len[source[1:0]]<=0;header_bad[source[1:0]]<=0;control_kind<=2;control_error<=0;
     end else begin control_kind<=5;control_error<=32;protocol_errors<=protocol_errors+1'b1;end
    end
    4:if(value==16000000||value==40000000||value==80000000)begin config_rate[source[1:0]]<=value;control_pending<=1;control_kind<=2;control_source<=source;control_job<=job;control_error<=0;end
    5:begin config_frequency[source[1:0]]<=value;control_pending<=1;control_kind<=2;control_source<=source;control_job<=job;control_error<=0;end
    6:begin armed<=0;binary_active<=0;if(armed)pair_lock<=0;control_pending<=1;control_kind<=2;control_source<=source;control_job<=job;control_error<=0;end
    7:if(value==2000000||value==4000000)begin new_host_baud<=value;control_pending<=1;control_kind<=4;control_source<=source;control_job<=job;control_error<=0;end
    default:command_errors<=command_errors+1'b1;
   endcase
  end
 end
 if(armed)begin
  if(deadline!=0)deadline<=deadline-1'b1;
  else begin pair_lock<=0;armed<=0;binary_active<=0;protocol_errors<=protocol_errors+1'b1;control_pending<=1;control_kind<=5;control_source<={6'b0,owner};control_job<=active_job;control_error<=8;end
 end
 for(integer s=0;s<3;s=s+1)if(rv[s])begin
  if(binary_active && owner==2'(s))begin
   raw_crc<=crc_byte(raw_crc,rb[s]);received_bytes<=received_bytes+1'b1;
   if(!received_bytes[0])low_i<=rb[s];else begin mem_write<=1;mem_waddr<=$clog2(2*MAX_SAMPLES)'((write_bank?MAX_SAMPLES:0)+(received_bytes>>1));mem_wdata<={rb[s],low_i};end
   if(received_bytes+1==requested_samples*2)begin
    armed<=0;binary_active<=0;
    if((~crc_byte(raw_crc,rb[s]))==expected_crc)begin
     mon_capture_ok[s]<=1;
     bank_pair[write_bank]<=capture_pair;bank_ready[write_bank]<=1;bank_job[write_bank]<=active_job;bank_samples[write_bank]<=requested_samples;
     bank_rate[write_bank]<=capture_rate;bank_frequency[write_bank]<=capture_frequency;bank_crc[write_bank]<=expected_crc;bank_us[write_bank]<=header_us;bank_source[write_bank]<=owner;
     bank_first[write_bank]<=receipt_tick;bank_last[write_bank]<=ticks;
    end else begin pair_lock<=0;protocol_errors<=protocol_errors+1'b1;control_pending<=1;control_kind<=5;control_source<={6'b0,owner};control_job<=active_job;control_error<=1;end
   end
  end else begin
   if(rb[s]==10)begin
    if(armed && owner==2'(s) && header_active[s])begin
     if(!header_bad[s]&&header_field[s]==2&&hex_digits[s]==8&&parsed_count[s]==requested_samples)begin binary_active<=1;received_bytes<=0;raw_crc<=32'hffffffff;expected_crc<=parsed_crc[s];header_us<=parsed_us[s];receipt_tick<=ticks;end
     else begin pair_lock<=0;armed<=0;protocol_errors<=protocol_errors+1'b1;control_pending<=1;control_kind<=5;control_source<={6'b0,owner};control_job<=active_job;control_error<=4;end
    end
    line_len[s]<=0;line_overflow[s]<=0;header_active[s]<=0;header_bad[s]<=0;
   end else if(rb[s]!=13)begin
    if(line_len[s]!=255)begin line[s][line_len[s]]<=rb[s];line_len[s]<=line_len[s]+1'b1;end else line_overflow[s]<=1;
    if(line_len[s]==4&&line[s][0]=="D"&&line[s][1]=="A"&&line[s][2]=="T"&&line[s][3]=="A"&&rb[s]==32)begin
     header_active[s]<=1;header_field[s]<=0;parsed_count[s]<=0;parsed_crc[s]<=0;parsed_us[s]<=0;hex_digits[s]<=0;
    end else if(header_active[s])begin
     if(rb[s]==32)begin if(header_field[s]<2)header_field[s]<=header_field[s]+1'b1;else header_bad[s]<=1;end
     else case(header_field[s])
      0:if(rb[s]>="0"&&rb[s]<="9"&&parsed_count[s]<=MAX_SAMPLES)parsed_count[s]<=parsed_count[s]*10+(32'(rb[s])-48);else header_bad[s]<=1;
      1:if(hex(rb[s])<16&&hex_digits[s]<8)begin parsed_crc[s]<={parsed_crc[s][27:0],4'(hex(rb[s]))};hex_digits[s]<=hex_digits[s]+1'b1;end else header_bad[s]<=1;
      2:if(rb[s]>="0"&&rb[s]<="9"&&parsed_us[s]<429496729)parsed_us[s]<=parsed_us[s]*10+(32'(rb[s])-48);else header_bad[s]<=1;
      default:header_bad[s]<=1;
     endcase
    end
   end
  end
 end
 case(output_state)
  0:begin
   output_index<=0;output_crc<=32'hffffffff;
   if(control_pending)begin
    tx_pair<=0;control_pending<=0;tx_kind<=control_kind;tx_source<=control_source;tx_job<=control_job;tx_samples<=MAX_SAMPLES;tx_rate<=config_rate[control_source[1:0]];tx_frequency<=config_frequency[control_source[1:0]];tx_raw_crc<=command_errors;tx_us<=radio_errors;tx_error<=control_error;tx_length<=0;tx_first<=ticks;tx_last<={32'b0,protocol_errors};tx_aux<={text_drops,28'b0,binary_active,armed,bank_ready};output_state<=1;
   end else if(bank_ready!=0)begin
    if(bank_ready[round_robin])begin tx_bank<=round_robin;tx_source<={6'b0,bank_source[round_robin]};tx_job<=bank_job[round_robin];tx_samples<=bank_samples[round_robin];tx_rate<=bank_rate[round_robin];tx_frequency<=bank_frequency[round_robin];tx_raw_crc<=bank_crc[round_robin];tx_us<=bank_us[round_robin];tx_length<=bank_samples[round_robin]*2;tx_first<=bank_first[round_robin];tx_last<=bank_last[round_robin];end
    else begin tx_bank<=!round_robin;tx_source<={6'b0,bank_source[!round_robin]};tx_job<=bank_job[!round_robin];tx_samples<=bank_samples[!round_robin];tx_rate<=bank_rate[!round_robin];tx_frequency<=bank_frequency[!round_robin];tx_raw_crc<=bank_crc[!round_robin];tx_us<=bank_us[!round_robin];tx_length<=bank_samples[!round_robin]*2;tx_first<=bank_first[!round_robin];tx_last<=bank_last[!round_robin];end
    tx_pair<=bank_pair[bank_ready[round_robin]?round_robin:!round_robin];
    tx_kind<=1;tx_error<=0;tx_aux<=ticks;output_state<=1;
   end else if(text_pending!=0)begin
    if(text_pending[0])begin tx_source<=0;tx_length<={24'b0,queued_len[0][text_head[0]]};end
    else if(text_pending[1])begin tx_source<=1;tx_length<={24'b0,queued_len[1][text_head[1]]};end
    else begin tx_source<=2;tx_length<={24'b0,queued_len[2][text_head[2]]};end
    tx_pair<=0;tx_kind<=3;tx_job<=0;tx_samples<=0;tx_rate<=0;tx_frequency<=0;tx_raw_crc<=0;tx_us<=0;tx_error<=0;tx_first<=ticks;tx_last<=0;tx_aux<=0;output_state<=1;
   end
  end
  1:if(!host_busy)begin host_out<=next_out;host_start<=1;if(output_index<64+tx_length)output_crc<=crc_byte(output_crc,next_out);output_state<=2;end
  2:if(host_done)begin
   if(output_index+1==total_bytes)begin
    output_state<=0;
    if(tx_kind==1 && tx_pair)begin
     // Keep original bank and snapshot owned until the filtered frame is sent.
     pair_wait<=0;output_state<=4;
    end else if(tx_kind==1 || tx_kind==6 || (tx_kind==5 && tx_pair))begin
     bank_ready[tx_bank]<=0;round_robin<=!tx_bank;if(tx_pair)pair_lock<=0;
    end
    if(tx_kind==4)host_baud<=new_host_baud;
   end else begin output_index<=output_index+1'b1;output_state<=3;end
  end
  3:output_state<=1;
  4:begin
   pair_wait<=pair_wait+1'b1;
   if(uart_done)begin
    tx_kind<=6;tx_aux<={tx_raw_crc,uart_profile};tx_raw_crc<=uart_crc;
    output_index<=0;output_crc<=32'hffffffff;output_state<=1;
   end else if(uart_fault || pair_wait>20000000)begin
    tx_kind<=5;tx_error<=64;tx_length<=0;output_index<=0;output_crc<=32'hffffffff;output_state<=1;
   end
  end
  default:output_state<=0;
 endcase
 end
end

endmodule
