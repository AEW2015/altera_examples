`timescale 1ns/1ps
module tb_iq_spi_abort;
 logic clk=0;always #10 clk=~clk;
 logic reset=1,tx_start=0;logic[7:0]tx_data;wire tx_busy,tx_done,rx_valid,rx_error;wire[7:0]rx_data;
 logic spi_miso=0,spi_ready=1;wire spi_mosi,spi_sck,spi_cs_n;
 iq_spi_radio_proxy #(.READY_TIMEOUT(10000),.CAPTURE_TIMEOUT(1000))dut(.*);
 integer count=0;logic[7:0]reply[0:99];bit saw_cs=0;
 always @(negedge spi_cs_n)saw_cs=1;
 always @(posedge clk)if(rx_valid)begin reply[count]=rx_data;count++;end
 task automatic send(input string s);
  begin for(integer n=0;n<s.len();n++)begin wait(!tx_busy);@(negedge clk);tx_data=s[n];tx_start=1;@(negedge clk);tx_start=0;wait(tx_done);@(negedge clk);end end
 endtask
 task automatic expect_text(input string s);
  begin wait(count>=s.len());repeat(20)@(negedge clk);if(count!=s.len())$fatal(1,"length");
   for(integer n=0;n<s.len();n++)if(reply[n]!==s[n])$fatal(1,"response");count=0;
  end
 endtask
 initial begin repeat(8)@(negedge clk);reset=0;
  send("CAP16 16380 6\n");expect_text("ERR spi_capture_timeout\n");
  if(!saw_cs || !spi_cs_n || spi_sck || dut.observed_valid || dut.commits)$fatal(1,"timedout transaction must releaseCS and publish no capture");
  send("MODE?\n");expect_text("RF_MODE,SDR,baud=2000000,transport=SPI\n");
  send("CAP16 16380 6\n");expect_text("ERR spi_capture_timeout\n");
  if(!spi_cs_n)$fatal(1,"secondtimeout recovery");
  $display("PASS SPI timeout abort: midtransaction CS released, no partial DATA/commit, command recovery and repeat");$finish;
 end
 initial begin #1000000;$fatal(1,"abort watchdog");end
endmodule
