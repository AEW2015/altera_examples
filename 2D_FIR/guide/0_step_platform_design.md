# Setup Platform Design

TODO: Add pictures

## Prepare Target

You will need a Altera FPGA with JTAG, Clock, and Reset.

Start a normal Quartus Project with your chosen HW (optional: Project name as dma_ex).

Open Platform design (optional: as dma_top.qsys) and remove default IP (Different Versions of Quartus Have different defaults.)

## Basic Clock and Reset

Add Clock Bridge Intel FPGA IP and define Clk speed.

Add Reset Bridge Intel FPGA IP and define as active high or low. 

Add Reset Release Intel FPGA IP.

## Basic System.

Add JTAG to Avalon Master Bridge Intel FPGA IP.

Add System ID Peripheral Intel FPGA IP (optional: ID as oxCAFE7AC0).

Add On-Chip Memory II Intel FPGA IP and define size as atleast twice the size of chosen resolution (example: 262144 for 400x320 image).

## Add DMA + 2D FIR

Add 2D-FIR II Intel FPGA IP with following settings:
* Number of Color Planes -> 1
* Number of pixels in parrellel -> 4
* Maximum Frame Width and Height -> Chosen resolution (example: 400 & 320)
* Input/Output bits per pixel per color plane -> 8
* Veritcal/Horiztonal filter taps -> 3
* Run-time control -> yes
* No user packets allowed
* Video has no blanking

Add Modular Scatter-Gatter DMA Intel FPGA IP with following Settings:
* DMA mode -> Memory-Mapped to Streaming
* Maximum Trasfer Length -> 128 KB (or bigger)
* Packet Support Enable -> yes

Add Another Modular Scatter-Gatter DMA Intel FPGA IP with following Settings:
* DMA mode -> Streaming to Memory-Mapped
* Maximum Trasfer Length -> 128 KB (or bigger)
* Packet Support Enable -> yes

## Add Avalon Stream Adapters

This is for latency difference in Stream interfaces

Add Avalon Streaming Adapater Intel FPGA IP with following Settings:
* Symbol Width -> 8
* Use Packet -> yes
* Source Data Width -> 32
* Source Max Channel -> 0
* Source Channel Port Width -> 0
* Source Error Port Width -> 0
* Source Uses Empty Port -> yes
* Source Uses Valid Port -> yes
* Source Uses Ready Port -> yes
* Source Read Latency -> 0
* Sink Data Width -> 32
* Sink Max Channel -> 0
* Sink Channel Port Width -> 0
* Sink Error Port Width -> 0
* Sink Uses Empty Port -> yes
* Sink Uses Valid Port -> yes
* Sink Uses Ready Port -> yes
* Sink Read Latency -> 1

Add Another Avalon Streaming Adapater Intel FPGA IP with following Settings:
* Symbol Width -> 8
* Use Packet -> yes
* Source Data Width -> 32
* Source Max Channel -> 0
* Source Channel Port Width -> 0
* Source Error Port Width -> 0
* Source Uses Empty Port -> yes
* Source Uses Valid Port -> yes
* Source Uses Ready Port -> yes
* Source Read Latency -> 1
* Sink Data Width -> 32
* Sink Max Channel -> 0
* Sink Channel Port Width -> 0
* Sink Error Port Width -> 0
* Sink Uses Empty Port -> yes
* Sink Uses Valid Port -> yes
* Sink Uses Ready Port -> yes
* Sink Read Latency -> 0

## Conections

Connect out_clk to all clock inputs.

Connect out_reset to JTAG MM Master as clk_reset.

Connect JTAG MM master_rest to all other resets.

Connect Reset Release reset to all resets.

Connect JTAG MM Master to all Avalon Memory Mapped Agents.

Connect msgdma_0/1 Avalon mm_read/mm_write to the On-Chip Memory

Connect msgdma_0 st_source to st_adapter0 in_0

Connect st_adapter0 out_o to alt_vip_cl_2dfir_0 din

Connect alt_vip_cl_2dfir_0 dout to st_adapter1 in_0

Connect st_adapter1 out_0 to msgdma_1 st_sink

## Assign Address

Use the System -> Assign Bass Addresses

Example design:
* alt_vip_cl_2dfir_0.control	    0x0004_0000 - 0x0004_07ff		
* intel_onchip_memory_0.s1	        0x0000_0000 - 0x0003_ffff
* msgdma_0.csr	                    0x0004_0820 - 0x0004_083f		
* msgdma_0.descriptor_slave	        0x0004_0850 - 0x0004_085f		
* msgdma_1.csr	                    0x0004_0800 - 0x0004_081f		
* msgdma_1.descriptor_slave	        0x0004_0840 - 0x0004_084f		
* sysid_qsys_0.control_slave	    0x0004_0860 - 0x0004_0867		