// Temporary clockless UART routing. TARGET: 0 RFS2, 1 Pmod A, 2 Pmod B.
// ROM_MODE=1 uses the Pmod's J2 GPIO1/3 and holds only its GPIO0 low.
// Runtime mode uses J1 GPIO17/16 and releases both GPIO0 signals.
module esp32_programmer #(
    parameter integer TARGET = 0,
    parameter integer ROM_MODE = 1
)(
    input wire HOST_RX, output wire HOST_TX,
    input wire RFS2_TX, output wire RFS2_RX,
    input wire PMOD0_TX, PMOD1_TX,
    output wire PMOD0_RX, PMOD1_RX,
    input wire A_TX, B_TX, output wire A_RX, B_RX,
    inout wire A_GPIO0, B_GPIO0
);
    assign RFS2_RX = TARGET == 0 ? HOST_RX : 1'b1;
    assign PMOD0_RX = TARGET == 1 && !ROM_MODE ? HOST_RX : 1'b1;
    assign PMOD1_RX = TARGET == 2 && !ROM_MODE ? HOST_RX : 1'b1;
    assign A_RX = TARGET == 1 && ROM_MODE ? HOST_RX : 1'b1;
    assign B_RX = TARGET == 2 && ROM_MODE ? HOST_RX : 1'b1;
    assign HOST_TX = TARGET == 0 ? RFS2_TX :
                     TARGET == 1 ? (ROM_MODE ? A_TX : PMOD0_TX) :
                                   (ROM_MODE ? B_TX : PMOD1_TX);
    assign A_GPIO0 = TARGET == 1 && ROM_MODE ? 1'b0 : 1'bz;
    assign B_GPIO0 = TARGET == 2 && ROM_MODE ? 1'b0 : 1'bz;
endmodule
