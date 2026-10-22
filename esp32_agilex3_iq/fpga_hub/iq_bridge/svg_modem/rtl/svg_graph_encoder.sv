// Symbol-rate K=7 encoder and five-node SVG graph mapper.
// This block emits one quantized endpoint per coded pair. It does not generate
// the oversampled waveform between endpoints or perform noise/RX processing.
module svg_graph_encoder (
    input  logic               clk,
    input  logic               reset,
    input  logic               start,
    input  logic        [8:0]  payload_count,
    input  logic               bit_valid,
    output logic               bit_ready,
    input  logic               bit_in,
    output logic               valid,
    input  logic               ready,
    output logic signed [15:0] iq_i,
    output logic signed [15:0] iq_q,
    output logic        [2:0]  node,
    output logic        [1:0]  coded_pair,
    output logic               done,
    output logic               busy,
    output logic               error
);

    logic [5:0] encoder_state;
    logic [2:0] current_node;
    logic [8:0] payload_left;
    logic [2:0] tail_left;

    logic [6:0] encoder_register;
    logic [1:0] next_pair;
    logic [2:0] next_node;
    logic signed [15:0] next_i;
    logic signed [15:0] next_q;
    logic signed [3:0] node_delta;
    logic output_slot;
    logic accept_payload;
    logic emit_tail;

    // The output register can be replaced on the same cycle its current item
    // is accepted, so input throughput is one symbol per cycle under back-to-back
    // ready/valid traffic.
    always_comb begin
        output_slot = !valid || ready;
        bit_ready = busy && (payload_left != 0) && output_slot;
        accept_payload = bit_valid && bit_ready;
        emit_tail = busy && (payload_left == 0) && (tail_left != 0) && output_slot;

        encoder_register = {encoder_state, 1'b0};
        if (accept_payload)
            encoder_register[0] = bit_in;

        next_pair[1] = ^(encoder_register & 7'o171);
        next_pair[0] = ^(encoder_register & 7'o133);

        // 00:+1, 01:+2, 10:-1, 11:-2, with modulo-five node numbering.
        case (next_pair)
            2'b00: node_delta =  4'sd1;
            2'b01: node_delta =  4'sd2;
            2'b10: node_delta = -4'sd1;
            default: node_delta = -4'sd2;
        endcase
        if ((integer'(current_node) + integer'(node_delta)) < 0)
            next_node = 3'(integer'(current_node) + integer'(node_delta) + 5);
        else if ((integer'(current_node) + integer'(node_delta)) >= 5)
            next_node = 3'(integer'(current_node) + integer'(node_delta) - 5);
        else
            next_node = 3'(integer'(current_node) + integer'(node_delta));

        // Round 8192*(cos(pi/2 - n*2*pi/5), sin(...)) to nearest integer.
        // This is the discrete symbol alphabet; no between-symbol samples are
        // implied by these endpoint coordinates.
        case (next_node)
            3'd0: begin next_i =  16'sd0;    next_q =  16'sd8192; end
            3'd1: begin next_i =  16'sd7791; next_q =  16'sd2531; end
            3'd2: begin next_i =  16'sd4815; next_q = -16'sd6627; end
            3'd3: begin next_i = -16'sd4815; next_q = -16'sd6627; end
            default: begin next_i = -16'sd7791; next_q =  16'sd2531; end
        endcase
    end

    always_ff @(posedge clk) begin
        if (reset) begin
            encoder_state <= 6'd0;
            current_node <= 3'd0;
            payload_left <= 9'd0;
            tail_left <= 3'd0;
            iq_i <= 16'sd0;
            iq_q <= 16'sd0;
            node <= 3'd0;
            coded_pair <= 2'd0;
            valid <= 1'b0;
            done <= 1'b0;
            busy <= 1'b0;
            error <= 1'b0;
        end else begin
            done <= 1'b0;

            if (start && !busy) begin
                valid <= 1'b0;
                done <= 1'b0;
                error <= 1'b0;
                if ((payload_count == 0) || (payload_count > 9'd256)) begin
                    busy <= 1'b0;
                    error <= 1'b1;
                end else begin
                    encoder_state <= 6'd0;
                    current_node <= 3'd0;
                    payload_left <= payload_count;
                    tail_left <= 3'd6;
                    busy <= 1'b1;
                end
            end else if (busy) begin
                if (output_slot)
                    valid <= 1'b0;

                if (accept_payload) begin
                    encoder_state <= encoder_register[5:0];
                    payload_left <= payload_left - 9'd1;
                    current_node <= next_node;
                    iq_i <= next_i;
                    iq_q <= next_q;
                    node <= next_node;
                    coded_pair <= next_pair;
                    valid <= 1'b1;
                end else if (emit_tail) begin
                    encoder_state <= encoder_register[5:0];
                    current_node <= next_node;
                    iq_i <= next_i;
                    iq_q <= next_q;
                    node <= next_node;
                    coded_pair <= next_pair;
                    tail_left <= tail_left - 3'd1;
                    valid <= 1'b1;
                end

                if (valid && ready && (payload_left == 0) && (tail_left == 0)) begin
                    valid <= 1'b0;
                    busy <= 1'b0;
                    done <= 1'b1;
                end
            end
        end
    end

endmodule
