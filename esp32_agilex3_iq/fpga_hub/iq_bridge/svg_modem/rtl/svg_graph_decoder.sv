// Joint K7 / five-node graph Viterbi. Symbol-rate Euclidean decoding.
// Samples are signed CI16, nominal radius 8192. Not a timing synchronizer.
module svg_graph_decoder (
    input logic clk, reset, start,
    input logic [8:0] payload_count,
    input logic sample_valid,
    output logic sample_ready,
    input logic signed [15:0] sample_i, sample_q,
    output logic busy, done, error,
    input logic [8:0] read_address,
    output logic decoded_bit,
    output logic [2:0] decoded_node,
    output logic [47:0] final_metric,
    output logic nearest_valid,
    output logic [2:0] nearest_node
);
    localparam logic [47:0] INF = 48'hffffffffffff;
    typedef enum logic [3:0] {IDLE,INIT,WAIT_SAMPLE,DISTANCE,ACS_READ0,ACS_READ1,ACS,FINAL_FETCH,FINAL_SCAN,
                              TRACE_READ,TRACE_APPLY} state_t;
    state_t state = IDLE;
    (* ramstyle = "M20K" *) logic [47:0] paths [0:639];
    // Explicit one-bit packed word: a scalar unpacked array is flattened by
    // Quartus into an 83,840-bit logic vector instead of inferred block RAM.
    (* ramstyle = "M20K" *) logic [0:0] survivor [0:83839];
    logic [47:0] path_read_data, parent_metric0;
    logic [9:0] metric_address;
    logic metric_write;
    logic [9:0] metric_write_address;
    logic [47:0] metric_write_data, branch0, branch1;
    logic decoded [0:255];
    logic [2:0] nodes [0:261];
    logic [47:0] distances [0:4];
    logic signed [15:0] held_i, held_q;
    logic bank, trace_choice;
    logic [8:0] payload, steps, step_index, scan, trace_joint, trace_index, best_joint;
    logic [2:0] dist_index;
    logic [47:0] best_metric;
    logic [47:0] nearest_metric;
    logic [2:0] nearest_choice;

    function automatic logic signed [3:0] delta(input logic [1:0] pair);
        case (pair)
            0: delta=1;
            1: delta=2;
            2: delta=-1;
            default: delta=-2;
        endcase
    endfunction
    function automatic logic [1:0] pair_for(input integer memory_state, input integer bit_value);
        logic [6:0] reg7;
        begin
            reg7=7'((memory_state<<1)|bit_value);
            pair_for={^(reg7&7'o171),^(reg7&7'o133)};
        end
    endfunction
    function automatic logic [8:0] previous_joint(input logic [8:0] joint, input logic top);
        logic [5:0] previous_memory;
        logic [2:0] previous_node;
        logic signed [3:0] difference;
        begin
            previous_memory={top,joint[5:1]};
            difference=$signed({1'b0,joint[8:6]})-delta(pair_for(int'(previous_memory),int'(joint[0])));
            if(difference<0) previous_node=3'(difference+4'sd5);
            else if(difference>=5) previous_node=3'(difference-4'sd5);
            else previous_node=3'(difference);
            previous_joint={previous_node,previous_memory};
        end
    endfunction
    function automatic integer point_i(input integer node);
        case(node)
            0:point_i=0; 1:point_i=7791; 2:point_i=4815;
            3:point_i=-4815; default:point_i=-7791;
        endcase
    endfunction
    function automatic integer point_q(input integer node);
        case(node)
            0:point_q=8192; 1:point_q=2531; 2:point_q=-6627;
            3:point_q=-6627; default:point_q=2531;
        endcase
    endfunction
    function automatic logic [47:0] plus_distance(input logic [47:0] a,b);
        // 262 * max CI16 squared distance fits in 43 bits. INF is unreachable.
        plus_distance=a==INF ? INF : a+b;
    endfunction
    always_comb begin
        sample_ready=(state==WAIT_SAMPLE);
        decoded_bit=read_address<256 ? decoded[read_address] : 1'b0;
        decoded_node=read_address<262 ? nodes[read_address] : 3'b0;
        metric_address=0;
        if(state==ACS_READ0)metric_address=(bank ? 10'd320 : 10'd0)+10'(previous_joint(scan,0));
        if(state==ACS_READ1)metric_address=(bank ? 10'd320 : 10'd0)+10'(previous_joint(scan,1));
        if(state==FINAL_FETCH)metric_address=(bank ? 10'd320 : 10'd0)+10'({scan[2:0],6'b0});
        branch0=plus_distance(parent_metric0,distances[scan[8:6]]);
        branch1=plus_distance(path_read_data,distances[scan[8:6]]);
        metric_write=!reset && (state==INIT || state==ACS);
        metric_write_address=state==INIT ? 10'(scan) : (bank ? 10'd0 : 10'd320)+10'(scan);
        metric_write_data=state==INIT ? (scan==0 ? 48'b0 : INF) : (branch1<branch0 ? branch1 : branch0);
    end

    // One synchronous read port and one write port infer M20K metric RAM.
    // Two parent reads take two clocks; the ACS write uses a third clock.
    always_ff @(posedge clk) begin
        if(state==ACS_READ0 || state==ACS_READ1 || state==FINAL_FETCH)
            path_read_data<=paths[metric_address];
        if(metric_write)paths[metric_write_address]<=metric_write_data;
    end

    always_ff @(posedge clk) begin : engine
        integer previous;
        logic [47:0] m0,m1,candidate;
        longint signed di,dq;
        nearest_valid<=0;
        if(reset) begin
            state<=IDLE;busy<=0;done<=0;error<=0;final_metric<=0;
            bank<=0;payload<=0;steps<=0;step_index<=0;scan<=0;
            dist_index<=0;trace_joint<=0;trace_index<=0;
            best_joint<=0;best_metric<=INF;trace_choice<=0;
            held_i<=0;held_q<=0;
            nearest_node<=0;nearest_metric<=INF;nearest_choice<=0;
        end else case(state)
            IDLE: if(start) begin
                done<=0;error<=0;
                if(payload_count==0 || payload_count>256) begin
                    error<=1;done<=1;
                end else begin
                    payload<=int'(payload_count);steps<=int'(payload_count)+6;
                    step_index<=0;scan<=0;bank<=0;busy<=1;state<=INIT;
                end
            end
            INIT: begin
                if(scan==319) begin scan<=0;state<=WAIT_SAMPLE;end
                else scan<=scan+1;
            end
            WAIT_SAMPLE: if(sample_valid) begin
                held_i<=sample_i;held_q<=sample_q;dist_index<=0;state<=DISTANCE;
                nearest_metric<=INF;nearest_choice<=0;
            end
            DISTANCE: begin
                di=longint'(held_i)-point_i(dist_index);
                dq=longint'(held_q)-point_q(dist_index);
                candidate=48'(di*di+dq*dq);
                distances[dist_index]<=candidate;
                if(candidate<nearest_metric)begin nearest_metric<=candidate;nearest_choice<=dist_index;end
                if(dist_index==4) begin
                    nearest_valid<=1;
                    nearest_node<=candidate<nearest_metric ? dist_index : nearest_choice;
                    scan<=0;state<=ACS_READ0;
                end
                else dist_index<=dist_index+1;
            end
            ACS_READ0:state<=ACS_READ1;
            ACS_READ1:begin parent_metric0<=path_read_data;state<=ACS;end
            ACS: begin
                m0=plus_distance(parent_metric0,distances[scan[8:6]]);
                m1=plus_distance(path_read_data,distances[scan[8:6]]);
                survivor[step_index*320+scan]<=m1<m0;
                if(scan==319) begin
                    bank<=!bank;
                    if(step_index==steps-1) begin
                        scan<=0;best_metric<=INF;best_joint<=0;state<=FINAL_FETCH;
                    end else begin step_index<=step_index+1;state<=WAIT_SAMPLE;end
                end else begin scan<=scan+1;state<=ACS_READ0;end
            end
            FINAL_FETCH:state<=FINAL_SCAN;
            FINAL_SCAN: begin
                // Termination fixes encoder memory to zero; final node is free.
                candidate=path_read_data;
                if(candidate<best_metric) begin best_metric<=candidate;best_joint<=scan*64;end
                if(scan==4) begin
                    trace_joint<=candidate<best_metric ? scan*64 : best_joint;
                    final_metric<=candidate<best_metric ? candidate : best_metric;
                    trace_index<=steps-1;state<=TRACE_READ;
                end else begin scan<=scan+1;state<=FINAL_FETCH;end
            end
            TRACE_READ: begin
                trace_choice<=survivor[trace_index*320+trace_joint];
                state<=TRACE_APPLY;
            end
            TRACE_APPLY: begin
                if(trace_index<payload) decoded[trace_index]<=1'(trace_joint&1);
                nodes[trace_index]<=3'(trace_joint/64);
                previous=previous_joint(trace_joint,int'(trace_choice));
                trace_joint<=previous;
                if(trace_index==0) begin
                    if(previous!=0)error<=1;
                    busy<=0;done<=1;state<=IDLE;
                end else begin trace_index<=trace_index-1;state<=TRACE_READ;end
            end
            default:begin state<=IDLE;busy<=0;done<=1;error<=1;end
        endcase
    end
endmodule
