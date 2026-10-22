// Standalone internal SVG modem lab. All payload/noise/symbol DSP runs in RTL.
// Receiver sampling uses known edge-end strobes, not recovered unknown timing.
// JTAG/Avalon reads have fixed latency 1 to permit synchronous capture RAMs.
module svg_modem_mm (
    input logic clk, reset,
    input logic [5:0] avs_address,
    input logic avs_read, avs_write,
    input logic [31:0] avs_writedata,
    output logic [31:0] avs_readdata,
    output logic avs_waitrequest
);
    typedef enum logic [2:0] {IDLE,GENERATE,LAUNCH,PROCESS,CHECK,FINISH} state_t;
    state_t state=IDLE;
    logic busy=0,done=0,error=0;
    logic [8:0] payload_count=256;
    logic [14:0] noise_amplitude=10000;
    logic [31:0] seed=7;
    logic arc_mode=1;
    logic [12:0] selected_index=0;
    logic [31:0] cycles=0, symbol_errors=0, payload_errors=0;
    logic source_bits[0:255];
    (* ramstyle="M20K" *) logic [31:0] tx_symbols[0:261],rx_symbols[0:261];
    logic [2:0] tx_nodes[0:261];
    (* ramstyle="M20K" *) logic [31:0] tx_wave[0:4191],rx_wave[0:4191];
    integer gen_index=0, bit_index=0, symbol_index=0, wave_index=0;
    integer check_index=0, received_index=0;
    logic [31:0] data_rng=1,noise_rng_i=1,noise_rng_q=2;
    logic enc_start=0, enc_valid, enc_ready, enc_bit_ready, enc_done,enc_busy,enc_error;
    logic signed [15:0] enc_i,enc_q;
    logic [2:0] enc_node,previous_node=0;
    logic [1:0] enc_pair;
    logic wave_valid,wave_ready,wave_last,wave_error;
    logic signed [15:0] wave_i,wave_q,noisy_i,noisy_q;
    logic dec_start=0,dec_ready,dec_busy,dec_done,dec_error,dec_bit;
    logic [2:0] dec_node;
    logic nearest_valid;
    logic [2:0] nearest_node,nearest_expected;
    logic [8:0] dec_address;
    logic [47:0] dec_metric;
    logic run_reset;

    function automatic logic [31:0] advance(input logic [31:0] rng);
        logic [31:0] x;
        begin x=rng^(rng<<13);x=x^(x>>17);advance=x^(x<<5);end
    endfunction
    function automatic logic signed [15:0] saturate(input integer value);
        if(value>32767)saturate=16'sd32767;
        else if(value< -32768)saturate=-16'sd32768;
        else saturate=16'(value);
    endfunction
    always_comb begin : controls
        integer ni,nq;
        avs_waitrequest=0;
        // One frame-local reset clears waveform error and old decoder done.
        run_reset=reset || state==GENERATE;
        dec_address=state==CHECK ? 9'(check_index) : 9'(selected_index);
        wave_ready=!wave_last || dec_ready;
        ni=($signed(noise_rng_i[31:16])*int'(noise_amplitude))>>>15;
        nq=($signed(noise_rng_q[31:16])*int'(noise_amplitude))>>>15;
        noisy_i=saturate(int'(wave_i)+ni);
        noisy_q=saturate(int'(wave_q)+nq);
    end
    svg_graph_encoder encoder(
        .clk,.reset(run_reset),.start(enc_start),.payload_count,
        .bit_valid(state==PROCESS && bit_index<int'(payload_count)),
        .bit_ready(enc_bit_ready),.bit_in(source_bits[bit_index<256 ? bit_index : 0]),
        .valid(enc_valid),.ready(enc_ready),.iq_i(enc_i),.iq_q(enc_q),
        .node(enc_node),.coded_pair(enc_pair),.done(enc_done),.busy(enc_busy),.error(enc_error)
    );
    svg_edge_waveform #(.ROM_INIT_FILE("rtl/svg_waveform.hex")) waveform(
        .clk,.reset(run_reset),.in_valid(enc_valid),.in_ready(enc_ready),
        .source_node(previous_node),.destination_node(enc_node),.arc_mode,
        .out_valid(wave_valid),.out_ready(wave_ready),.iq_i(wave_i),.iq_q(wave_q),
        .last(wave_last),.error(wave_error)
    );
    svg_graph_decoder decoder(
        .clk,.reset(run_reset),.start(dec_start),.payload_count,
        .sample_valid(wave_valid&&wave_last),.sample_ready(dec_ready),
        .sample_i(noisy_i),.sample_q(noisy_q),.busy(dec_busy),.done(dec_done),.error(dec_error),
        .read_address(dec_address),.decoded_bit(dec_bit),.decoded_node(dec_node),.final_metric(dec_metric),
        .nearest_valid,.nearest_node
    );
    // Fixed-latency Avalon reads, including both capture memories.
    always_ff @(posedge clk) if(avs_read) case(avs_address)
        0:avs_readdata<=32'h53564701;
        1:avs_readdata<={29'b0,error,done,busy};
        2:avs_readdata<=32'(payload_count);
        3:avs_readdata<=32'(noise_amplitude);
        4:avs_readdata<=seed;
        5:avs_readdata<=32'(arc_mode);
        6:avs_readdata<=32'(selected_index);
        7:avs_readdata<=selected_index<262?tx_symbols[selected_index]:0;
        8:avs_readdata<=selected_index<262?rx_symbols[selected_index]:0;
        9:avs_readdata<=selected_index<256?32'(source_bits[selected_index]):0;
        10:avs_readdata<=selected_index<payload_count?32'(dec_bit):0;
        11:avs_readdata<=selected_index<262?32'(tx_nodes[selected_index]):0;
        12:avs_readdata<=selected_index<262?32'(dec_node):0;
        13:avs_readdata<=selected_index<4192?tx_wave[selected_index]:0;
        14:avs_readdata<=selected_index<4192?rx_wave[selected_index]:0;
        15:avs_readdata<=symbol_errors;
        16:avs_readdata<=payload_errors;
        17:avs_readdata<=cycles;
        18:avs_readdata<=32'(payload_count)+6;
        19:avs_readdata<=32'(wave_index);
        20:avs_readdata<=dec_metric[31:0];
        21:avs_readdata<={16'b0,dec_metric[47:32]};
        22:avs_readdata<=320;
        23:avs_readdata<=16;
        default:avs_readdata<=0;
    endcase
    always_ff @(posedge clk) begin
        enc_start<=0;dec_start<=0;
        if(reset)begin
            state<=IDLE;busy<=0;done<=0;error<=0;
            payload_count<=256;noise_amplitude<=10000;seed<=7;arc_mode<=1;
            selected_index<=0;cycles<=0;symbol_errors<=0;payload_errors<=0;
            gen_index<=0;bit_index<=0;symbol_index<=0;wave_index<=0;
            received_index<=0;check_index<=0;previous_node<=0;
            data_rng<=1;noise_rng_i<=1;noise_rng_q<=2;
            nearest_expected<=0;
        end else begin
            if(busy)cycles<=cycles+1;
            if(avs_write && avs_address==6)selected_index<=13'(avs_writedata);
            if(avs_write && !busy)case(avs_address)
                1:if(avs_writedata==1)begin
                    busy<=1;done<=0;error<=0;cycles<=0;
                    symbol_errors<=0;payload_errors<=0;
                    gen_index<=0;bit_index<=0;symbol_index<=0;received_index<=0;
                    wave_index<=0;previous_node<=0;state<=GENERATE;
                    data_rng<=seed;
                    noise_rng_i<=(seed^32'h9e3779b9)==0?1:seed^32'h9e3779b9;
                    noise_rng_q<=(seed^32'h243f6a88)==0?2:seed^32'h243f6a88;
                end
                2:if(avs_writedata>0&&avs_writedata<=256)payload_count<=9'(avs_writedata);else error<=1;
                3:if(avs_writedata<=30000)noise_amplitude<=15'(avs_writedata);else error<=1;
                4:if(avs_writedata!=0)seed<=avs_writedata;else error<=1;
                5:arc_mode<=avs_writedata[0];
                default:begin end
            endcase
            case(state)
                IDLE:begin end
                GENERATE:begin
                    source_bits[gen_index]<=data_rng[0];data_rng<=advance(data_rng);
                    if(gen_index==int'(payload_count)-1)state<=LAUNCH;
                    else gen_index<=gen_index+1;
                end
                LAUNCH:begin enc_start<=1;dec_start<=1;state<=PROCESS;end
                PROCESS:begin
                    // Reuse the decoder distance unit rather than duplicating
                    // ten combinational squarers in the noise-to-counter path.
                    if(nearest_valid && nearest_node!=nearest_expected)symbol_errors<=symbol_errors+1;
                    if(enc_bit_ready && bit_index<int'(payload_count))bit_index<=bit_index+1;
                    if(enc_valid&&enc_ready)begin
                        tx_symbols[symbol_index]<={enc_q,enc_i};
                        tx_nodes[symbol_index]<=enc_node;previous_node<=enc_node;
                        symbol_index<=symbol_index+1;
                    end
                    if(wave_valid&&wave_ready)begin
                        tx_wave[wave_index]<={wave_q,wave_i};rx_wave[wave_index]<={noisy_q,noisy_i};
                        wave_index<=wave_index+1;
                        noise_rng_i<=advance(noise_rng_i);noise_rng_q<=advance(noise_rng_q);
                        if(wave_last)begin
                            rx_symbols[received_index]<={noisy_q,noisy_i};
                            nearest_expected<=tx_nodes[received_index];
                            received_index<=received_index+1;
                        end
                    end
                    if(dec_done)begin
                        if(enc_error||wave_error||dec_error)error<=1;
                        check_index<=0;state<=CHECK;
                    end
                end
                CHECK:begin
                    if(dec_bit!=source_bits[check_index])payload_errors<=payload_errors+1;
                    if(check_index==int'(payload_count)-1)state<=FINISH;
                    else check_index<=check_index+1;
                end
                FINISH:begin busy<=0;done<=1;state<=IDLE;end
                default:begin busy<=0;error<=1;state<=IDLE;end
            endcase
        end
    end
endmodule
