`timescale 1ns/1ps
module tb_programmer;
    reg host, rfs, pa, pb, a, b;
    wire [5:0] tx, rr, ar, br, pr0, pr1;
    tri [5:0] ag, bg;
    for (genvar i=0; i<6; i=i+1) begin:g
        pullup(ag[i]); pullup(bg[i]);
        esp32_programmer #(.TARGET(i/2),.ROM_MODE(i%2)) dut(
            .HOST_RX(host),.HOST_TX(tx[i]),.RFS2_TX(rfs),.RFS2_RX(rr[i]),
            .PMOD0_TX(pa),.PMOD1_TX(pb),.PMOD0_RX(pr0[i]),.PMOD1_RX(pr1[i]),
            .A_TX(a),.B_TX(b),.A_RX(ar[i]),.B_RX(br[i]),.A_GPIO0(ag[i]),.B_GPIO0(bg[i]));
    end
    initial begin
        for(integer v=0;v<64;v=v+1) begin
            {host,rfs,pa,pb,a,b}=v; #1;
            for(integer i=0;i<6;i=i+1) begin
                if(tx[i] !== (i/2==0 ? rfs : i/2==1 ? (i%2 ? a:pa) : (i%2 ? b:pb))) $fatal(1,"host route");
                if(rr[i] !== (i/2==0 ? host:1'b1)) $fatal(1,"RFS2 isolation");
                if(ar[i] !== (i==3 ? host:1'b1) || br[i] !== (i==5 ? host:1'b1)) $fatal(1,"ROM isolation");
                if(pr0[i] !== (i==2 ? host:1'b1) || pr1[i] !== (i==4 ? host:1'b1)) $fatal(1,"runtime isolation");
                if(ag[i] !== (i==3 ? 1'b0:1'b1) || bg[i] !== (i==5 ? 1'b0:1'b1)) $fatal(1,"GPIO0 pull-up/release");
            end
        end
        $display("PASS: 6 routes x 64 combinations; GPIO0 low/Z and inactive isolation");
        $finish;
    end
endmodule
