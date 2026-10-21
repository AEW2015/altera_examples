`timescale 1ns/1ps
module tb_iq_spi_fir_pipeline;
 logic clk=0;always #10 clk=~clk;
 logic reset=1,bus_reset=0;
 logic host_valid=0,host_frame_error=0,host_busy=0,host_done=0;logic[7:0]host_byte=0;wire[31:0]host_baud;wire host_start;wire[7:0]host_out;
 wire[2:0]radio_fast,rv,re,ts,tbusy,tdone;wire[23:0]radio_rx_data,radio_tx_data;
 wire mem_write;wire[14:0]mem_waddr,mem_raddr;wire[15:0]mem_wdata,mem_q;
 wire cap_write,cap_commit,cap_bank;wire[14:0]cap_waddr,cap_samples;wire[15:0]cap_wdata;
 wire[31:0]cap_job,cap_crc,cap_rate,cap_frequency;wire[1:0]cap_source;
 wire uart_arm,uart_owned,uart_enable,uart_available,uart_done,uart_fault;wire[13:0]uart_index;wire[15:0]uart_q;wire[31:0]uart_crc,uart_profile;
 wire[15:0]fir_data;wire fir_valid;wire[1:0]fir_error;wire[55:0]fir_result;wire fir_result_valid;wire[1:0]fir_result_error;
 logic[5:0]avs_address=0;logic avs_read=1,avs_write=0;logic[31:0]avs_writedata=0;logic[3:0]avs_byteenable=15;wire[31:0]avs_readdata;wire avs_waitrequest;
 iq_fir_capture filter(.*);
 iq_bridge_controller controller(.clk(clk),.reset(reset),.host_baud(host_baud),.host_valid(host_valid),.host_byte(host_byte),.host_frame_error(host_frame_error),.host_start(host_start),.host_out(host_out),.host_busy(host_busy),.host_done(host_done),
 .radio_fast(radio_fast),.rv(rv),.radio_rx_data(radio_rx_data),.re(re),.ts(ts),.radio_tx_data(radio_tx_data),.tbusy(tbusy),.tdone(tdone),
 .mem_write(mem_write),.mem_waddr(mem_waddr),.mem_wdata(mem_wdata),.mem_raddr(mem_raddr),.mem_q(mem_q),
 .cap_write(cap_write),.cap_waddr(cap_waddr),.cap_wdata(cap_wdata),.cap_commit(cap_commit),.cap_bank(cap_bank),.cap_samples(cap_samples),.cap_job(cap_job),.cap_crc(cap_crc),.cap_rate(cap_rate),.cap_frequency(cap_frequency),.cap_source(cap_source),
 .uart_enable(uart_enable),.uart_available(uart_available),.uart_done(uart_done),.uart_fault(uart_fault),.uart_q(uart_q),.uart_crc(uart_crc),.uart_profile(uart_profile),.uart_arm(uart_arm),.uart_owned(uart_owned),.uart_index(uart_index));
 iq_capture_memory memory(.clk(clk),.reset(reset),.mem_write(mem_write),.mem_waddr(mem_waddr),.mem_wdata(mem_wdata),.mem_raddr(mem_raddr),.mem_q(mem_q));
 logic spi_miso=0,spi_ready=1;wire tx0,tx1;wire rx0=tx0,rx1=tx1;wire spi_mosi,spi_sck,spi_cs_n;
 iq_radio_uarts radios(.*);
 logic[7:0]vectors[0:33791];integer bits=0,packets=0;bit dma_armed=1;
 always @(negedge spi_cs_n)begin
  if(!dma_armed || !spi_ready)$fatal(1,"early CS on stale READY before DMA rearmed");
  bits=0;packets++;
 end
 always @(posedge spi_sck)if(!spi_cs_n)spi_miso=(vectors[((packets-1)%32)*1056+bits/8]>>(7-bits%8))&1;
 always @(negedge spi_sck)if(!spi_cs_n)begin
  if(spi_mosi!==(bits<8?((8'h54>>(7-bits))&1):0))$fatal(1,"MOSI synthetic selector");bits++;
 end
 always @(posedge spi_cs_n)if(packets)begin
  if(bits!=8448)$fatal(1,"SPI fixedlength");dma_armed=0;
  fork begin #10000;spi_ready=0;#4000;dma_armed=1;spi_ready=1;end join_none
 end
 logic[3:0]ca=0;logic cr=0,cw=0;logic[15:0]cd=0;wire[15:0]cq;wire cv,waitreq;
 iq_bridge_system_fir_ii core(.clk(clk),.reset_n(!reset),.ast_sink_data(fir_data),.ast_sink_valid(fir_valid),.ast_sink_error(fir_error),.ast_source_data(fir_result),.ast_source_valid(fir_result_valid),.ast_source_error(fir_result_error),.coeff_in_clk(clk),.coeff_in_areset(!reset),.coeff_in_address(ca),.coeff_in_read(cr),.coeff_out_valid(cv),.coeff_out_waitrequest(waitreq),.coeff_out_data(cq),.coeff_in_we(cw),.coeff_in_data(cd));
 function automatic logic[31:0] crc_byte(input logic[31:0]crc,input logic[7:0]v);
  logic[31:0]c;begin c=crc^v;for(integer n=0;n<8;n++)c=(c>>1)^(c[0]?32'hedb88320:0);return c;end
 endfunction
 task automatic host(input byte b);begin @(negedge clk);host_valid=1;host_byte=b;@(negedge clk);host_valid=0;repeat(3)@(negedge clk);end endtask
 task automatic command(input byte op,input byte source,input integer arg,input integer job,input integer value);
  byte b[0:15];logic[31:0]crc;begin
   b[0]="I";b[1]="Q";b[2]="B";b[3]="C";b[4]=op;b[5]=source;b[6]=8'(arg);b[7]=8'(arg>>8);
   for(integer n=0;n<4;n++)begin b[n+8]=8'(job>>(8*n));b[n+12]=8'(value>>(8*n));end
   crc=~32'd0;for(integer n=0;n<16;n++)begin crc=crc_byte(crc,b[n]);host(b[n]);end
   for(integer n=0;n<4;n++)host(8'((~crc)>>(8*n)));
  end
 endtask
 task automatic text(input string s);begin for(integer n=0;n<s.len();n++)command(1,2,s[n],0,0);end endtask
 task automatic wr(input integer a,input integer d);begin @(negedge clk);avs_address=6'(a);avs_writedata=32'(d);avs_write=1;@(negedge clk);avs_write=0;end endtask
 integer f,bytes=0,captures=0;
 always @(posedge clk)begin host_done<=host_start;
  if(host_start)begin $fwrite(f,"%c",host_out);bytes++;
   if(controller.output_index==67+controller.tx_length && (controller.tx_kind==1 || controller.tx_kind==6))captures++;
  end
 end
 initial begin
  f=$fopen("pipeline.bin","wb");$readmemh("synthetic.hex",vectors);
  repeat(8)@(negedge clk);reset=0;repeat(64)@(negedge clk);
  for(integer i=0;i<16;i++)begin @(negedge clk);ca=4'(i);cd=16'(i==0?16384:i==1?8192:i==2?-4096:0);cw=1;@(negedge clk);cw=0;repeat(5)@(negedge clk);end
  wr(2,1);wr(18,1);wr(19,1);wr(20,0);
  command(2,0,0,2,2000000);repeat(1000)@(negedge clk);
  command(2,1,0,3,2000000);repeat(1000)@(negedge clk);
  command(0,2,0,9,0);repeat(1000)@(negedge clk); // reset metadata is already fixed
  command(4,2,0,10,40000000);repeat(1000)@(negedge clk); // bounded reject, metadata unchanged
  command(5,2,0,11,32'd2417000000);repeat(1000)@(negedge clk);
  command(3,2,0,12,1024);repeat(1000)@(negedge clk);
  if(controller.armed || controller.config_rate[2]!=16000000 || controller.config_frequency[2]!=32'd2447000000)$fatal(1,"fixed SPI profile corrupted by rejected controls");
  command(4,2,0,13,16000000);repeat(1000)@(negedge clk);
  command(5,2,0,14,32'd2447000000);repeat(1000)@(negedge clk);
  // Other radios retain the general UART metadata contract.
  command(4,0,0,15,40000000);repeat(1000)@(negedge clk);
  command(5,1,0,16,32'd2417000000);repeat(1000)@(negedge clk);
  command(3,2,0,32'h12345678,16380);repeat(1000)@(negedge clk);
  text("CAP16 16380 6\n");
  // The two physical UARTs remain functional while source2 SPI is active.
  for(integer n=0;n<6;n++)begin command(1,0,8'("RFS2!\n" >> ((5-n)*8)),0,0);command(1,1,8'("TX A!\n" >> ((5-n)*8)),0,0);end
  wait(captures==2);repeat(100)@(negedge clk);
  if(controller.protocol_errors!=1 || controller.command_errors!=2 || controller.radio_errors || packets!=32)$fatal(1,"pipeline counters");
  if(!radios.spi_proxy.observed_valid || radios.spi_proxy.commits!=1)$fatal(1,"SPI commit");
  $fclose(f);$display("PASS integrated SPI to actual FIR II to paired IQB1 raw/filtered frames, custom coefficients, matching capture descriptor");$finish;
 end
 initial begin #500000000;$fatal(1,"pipeline watchdog captures%0d packets%0d ctrlstate%0d",captures,packets,controller.output_state);end
endmodule
