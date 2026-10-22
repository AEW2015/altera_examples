// Five-node, symbol-edge waveform lookup.
// Each accepted node pair emits 16 samples, k=1..16. arc_mode selects
// constant-radius phase sweeps for adjacent circle edges; all other edges
// use their stored straight interpolation. This is a waveform generator only.
module svg_edge_waveform #(
    parameter ROM_INIT_FILE = "svg_waveform.hex"
) (
    input  logic               clk,
    input  logic               reset,
    input  logic               in_valid,
    output logic               in_ready,
    input  logic        [2:0]  source_node,
    input  logic        [2:0]  destination_node,
    input  logic               arc_mode,
    output logic               out_valid,
    input  logic               out_ready,
    output logic signed [15:0] iq_i,
    output logic signed [15:0] iq_q,
    output logic               last,
    output logic               error
);

    logic [63:0] waveform_rom [0:399];
    logic [63:0] rom_word;
    logic [8:0] edge_base;
    logic [3:0] sample_index;
    logic arc_mode_q;

    typedef enum logic [1:0] {IDLE, FETCH, PRESENT} state_t;
    state_t state;

    initial begin
        $readmemh(ROM_INIT_FILE, waveform_rom);
    end

    always_comb begin
        in_ready = (state == IDLE);
        if (arc_mode_q) begin
            iq_i = $signed(rom_word[47:32]);
            iq_q = $signed(rom_word[63:48]);
        end else begin
            iq_i = $signed(rom_word[15:0]);
            iq_q = $signed(rom_word[31:16]);
        end
    end

    always_ff @(posedge clk) begin
        if (reset) begin
            state <= IDLE;
            edge_base <= 9'd0;
            sample_index <= 4'd0;
            arc_mode_q <= 1'b0;
            rom_word <= 64'd0;
            out_valid <= 1'b0;
            last <= 1'b0;
            error <= 1'b0;
        end else begin
            case (state)
                IDLE: begin
                    out_valid <= 1'b0;
                    last <= 1'b0;
                    if (in_valid && in_ready) begin
                        if ((source_node >= 3'd5) ||
                            (destination_node >= 3'd5)) begin
                            // Drop malformed node IDs. Error is sticky until reset.
                            error <= 1'b1;
                        end else begin
                            edge_base <= 9'((integer'(source_node) * 5 +
                                             integer'(destination_node)) * 16);
                            sample_index <= 4'd0;
                            arc_mode_q <= arc_mode;
                            state <= FETCH;
                        end
                    end
                end

                FETCH: begin
                    // Registered read gives a one-cycle ROM latency. The output
                    // register then holds the selected word for any backpressure.
                    rom_word <= waveform_rom[edge_base + {5'd0, sample_index}];
                    out_valid <= 1'b1;
                    last <= (sample_index == 4'd15);
                    state <= PRESENT;
                end

                PRESENT: begin
                    if (out_valid && out_ready) begin
                        out_valid <= 1'b0;
                        last <= 1'b0;
                        if (sample_index == 4'd15) begin
                            state <= IDLE;
                        end else begin
                            sample_index <= sample_index + 4'd1;
                            state <= FETCH;
                        end
                    end
                end

                default: begin
                    state <= IDLE;
                    out_valid <= 1'b0;
                    last <= 1'b0;
                end
            endcase
        end
    end

endmodule
