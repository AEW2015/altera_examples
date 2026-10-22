// Atum A3 Nano / Agilex 3 standalone internal modem test top.
// The only board pin is the 50 MHz oscillator. Transactions use dedicated JTAG.
module svg_demo_top(input logic CLOCK_50);
`ifdef VERILATOR
    wire config_done = 1'b0;
`else
    wire config_done;
    altera_agilex_config_reset_release_endpoint config_reset_release (
        .conf_reset(config_done)
    );
`endif

    logic [7:0] power_on_count = 8'd0;
    wire system_reset = ~(&power_on_count);

    always_ff @(posedge CLOCK_50 or posedge config_done) begin
        if (config_done)
            power_on_count <= 8'd0;
        else if (system_reset)
            power_on_count <= power_on_count + 8'd1;
    end

    svg_modem_system system (
        .clk_clk(CLOCK_50),
        .reset_reset(system_reset)
    );
endmodule
