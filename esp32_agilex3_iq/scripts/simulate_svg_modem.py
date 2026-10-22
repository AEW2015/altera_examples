#!/usr/bin/env python3
"""Questa tests of actual SVG encoder/decoder RTL; no hardware access.

Generates independent integer-coordinate expectations using the Python graph
reference, exercises stream stalls, and compares every decoded bit/node/metric.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
import numpy as np
from common import ROOT, tool_exe, tool_env, tool_path
from svg_modem import encode, decode, load_graph

STAGE = ROOT / 'fpga_hub/iq_bridge/svg_modem'
OUT = STAGE / 'results/simulation'


def memory(path, values, digits):
    path.write_text(''.join(f'{int(x):0{digits}x}\n' for x in values))


def build_vectors():
    points = np.rint(np.column_stack((load_graph().real, load_graph().imag)) * 8192).astype(np.int64)
    constellation = points[:, 0] + 1j * points[:, 1]
    rng = np.random.default_rng(991)
    cases = []
    for name, count, snr in [('one_bit', 1, None), ('max_frame', 256, None),
                              ('noisy_corrected', 256, 7), ('severe_noise', 256, -6),
                              ('signed_extremes', 256, 'extreme')]:
        bits = rng.integers(0, 2, count, dtype=np.uint8)
        tx = encode(bits)
        clean = points[tx['node_path'][1:]]
        if snr is None:
            received = clean.copy()
        elif snr == 'extreme':
            received = rng.choice([-32768, 32767], size=clean.shape)
        else:
            sigma = 8192 * np.sqrt(0.5 * 10 ** (-snr / 10))
            received = np.clip(np.rint(clean + rng.normal(0, sigma, clean.shape)), -32768, 32767).astype(np.int64)
        rx = decode(received[:, 0] + 1j * received[:, 1], points=constellation)
        bit_errors = int(np.count_nonzero(bits != rx['decoded_bits']))
        hard_errors = int(np.count_nonzero(np.argmin(abs(received[:, 0, None] + 1j * received[:, 1, None] - constellation) ** 2, axis=1) != tx['node_path'][1:]))
        if name == 'noisy_corrected' and not (hard_errors > 0 and bit_errors == 0):
            raise AssertionError('Noisy correction fixture did not contain genuine corrected errors')
        if name in ('severe_noise', 'signed_extremes') and bit_errors == 0:
            raise AssertionError('Severe impairment fixture must expose decoder failures')
        files = {key: OUT / f'{name}-{key}.hex' for key in ('bits', 'pairs', 'nodes', 'iq', 'rx', 'decoded', 'decodednodes', 'nearest')}
        memory(files['bits'], bits, 1)
        memory(files['pairs'], tx['coded_pairs'], 1)
        memory(files['nodes'], tx['node_path'][1:], 1)
        packed = lambda iq: ((iq[:, 1].astype(np.int64) & 0xffff) << 16) | (iq[:, 0].astype(np.int64) & 0xffff)
        memory(files['iq'], packed(clean), 8)
        memory(files['rx'], packed(received), 8)
        memory(files['decoded'], rx['decoded_bits'], 1)
        memory(files['decodednodes'], rx['node_path'][1:], 1)
        memory(files['nearest'], np.argmin(abs(received[:, 0, None] + 1j * received[:, 1, None] - constellation) ** 2, axis=1), 1)
        cases.append({'name': name, 'payload_bits': count, 'symbols': count + 6,
                      'hard_symbol_errors': hard_errors, 'decoded_payload_errors': bit_errors,
                      'expected_metric': int(rx['metric']), 'files': files})
    return cases


TB = r'''`timescale 1ns/1ps
module tb_svg_modem;
reg clk=0; always #5 clk=~clk;
reg reset=1, estart=0, dstart=0;
reg [8:0] payload_count=0;
reg bit_valid=0, bit_in=0, ready=0;
wire bit_ready, valid, edone, ebusy, eerror;
wire signed [15:0] iq_i,iq_q;
wire [2:0] node;
wire [1:0] coded_pair;
reg sample_valid=0;
wire sample_ready,dbusy,ddone,derror;
reg signed [15:0] sample_i=0,sample_q=0;
reg [8:0] read_address=0;
wire decoded_bit, nearest_valid;
wire [2:0] decoded_node, nearest_node;
wire [47:0] final_metric;
svg_graph_encoder enc(.clk(clk),.reset(reset),.start(estart),.payload_count(payload_count),
.bit_valid(bit_valid),.bit_ready(bit_ready),.bit_in(bit_in),.valid(valid),.ready(ready),
.iq_i(iq_i),.iq_q(iq_q),.node(node),.coded_pair(coded_pair),.done(edone),.busy(ebusy),.error(eerror));
svg_graph_decoder dec(.clk(clk),.reset(reset),.start(dstart),.payload_count(payload_count),
.sample_valid(sample_valid),.sample_ready(sample_ready),.sample_i(sample_i),.sample_q(sample_q),
.busy(dbusy),.done(ddone),.error(derror),.read_address(read_address),
.decoded_bit(decoded_bit),.decoded_node(decoded_node),.final_metric(final_metric),
.nearest_valid(nearest_valid),.nearest_node(nearest_node));
reg bits[0:255], expected_bits[0:255];
reg [1:0] pairs[0:261];
reg [2:0] nodes[0:261], expected_nodes[0:261], expected_nearest[0:261];
integer nearest_cycles[0:261], nearest_count;
reg previous_nearest;
reg [31:0] iq[0:261], samples[0:261];
integer count, sent, received, cycle, k;
reg stalled;
reg [36:0] held_output;
initial begin
repeat(4) @(negedge clk);reset=0;
__CASES__
// Invalid frame lengths must not enter a stream operation.
foreach_invalid(0);foreach_invalid(257);
$display("PASS actual SVG encoder and 320-state decoder RTL: all bits, nodes, integer metrics, stream stalls, invalid counts");
$finish;
end

task automatic foreach_invalid(input integer n);
begin
 @(negedge clk);payload_count=9'(n);estart=1;dstart=1;
 @(negedge clk);estart=0;dstart=0;
 if(!eerror || ebusy || !derror || dbusy) $fatal(1,"invalid count %0d accepted",n);
end
endtask

task automatic run_case(input string name, input integer n, input logic[47:0] expected_metric);
begin
 count=n;
 @(negedge clk);payload_count=9'(n);estart=1;
 @(negedge clk);estart=0;
 sent=0;received=0;cycle=0;stalled=0;
 while(!edone && cycle<10000) begin
  bit_valid=(sent<n && cycle%3!=0); bit_in=sent<n ? bits[sent] : 0;
  ready=(cycle%5!=0 && cycle%5!=1);
  @(posedge clk);
  if(stalled && {node,coded_pair,iq_q,iq_i} !== held_output) $fatal(1,"encoder output changed under backpressure");
  stalled=valid && !ready;held_output={node,coded_pair,iq_q,iq_i};
  if(bit_valid && bit_ready)sent=sent+1;
  if(valid && ready)begin
   if(received>=n+6)$fatal(1,"extra encoder symbol");
   if(node!==nodes[received] || coded_pair!==pairs[received] || {iq_q,iq_i}!==iq[received])
    $fatal(1,"encoder mismatch %s symbol%0d gotnode%0d expected%0d",name,received,node,nodes[received]);
   received=received+1;
  end
  @(negedge clk);cycle=cycle+1;
 end
 bit_valid=0;ready=0;
 if(cycle>=10000 || sent!=n || received!=n+6 || eerror || ebusy)$fatal(1,"encoder completion %s",name);
 dstart=1;
 @(negedge clk);dstart=0;sent=0;cycle=0;nearest_count=0;previous_nearest=0;
 while(!ddone && cycle<500000)begin
  sample_valid=(sent<n+6 && cycle%7!=0 && cycle%7!=1);
  if(sent<n+6)begin sample_i=samples[sent][15:0];sample_q=samples[sent][31:16];end
  @(posedge clk);
  if(nearest_valid)begin
   if(previous_nearest || nearest_count>=sent)$fatal(1,"extra or widened nearest pulse");
   if(nearest_node!==expected_nearest[nearest_count])$fatal(1,"nearest node mismatch %s symbol%0d",name,nearest_count);
   if(cycle-nearest_cycles[nearest_count]!=6)$fatal(1,"nearest latency %s",name);
   nearest_count=nearest_count+1;
  end
  previous_nearest=nearest_valid;
  if(sample_valid && sample_ready)begin nearest_cycles[sent]=cycle;sent=sent+1;end
  @(negedge clk);cycle=cycle+1;
 end
 sample_valid=0;
 if(nearest_count!=n+6)$fatal(1,"nearest pulse count %s",name);
 if(cycle>=500000 || sent!=n+6 || derror || dbusy)$fatal(1,"decoder completion %s",name);
 if(final_metric!==expected_metric)$fatal(1,"metric %s got%0d expected%0d",name,final_metric,expected_metric);
 for(k=0;k<n+6;k=k+1)begin
  read_address=9'(k);#1;
  if(decoded_node!==expected_nodes[k])$fatal(1,"decoded node %s index%0d got%0d expected%0d",name,k,decoded_node,expected_nodes[k]);
  if(k<n && decoded_bit!==expected_bits[k])$fatal(1,"decoded bit %s index%0d",name,k);
  @(negedge clk);
 end
 $display("PASS case %s payload%0d metric%0d cycles%0d",name,n,final_metric,cycle);
end
endtask
initial begin #100000000;$fatal(1,"testbench timeout");end
endmodule
'''



def advance(value):
    value = (value ^ (value << 13)) & 0xffffffff
    value ^= value >> 17
    return (value ^ (value << 5)) & 0xffffffff


def wrapper_vectors():
    # Independent NumPy geometry; do not import the ROM generator under test.
    angles = np.pi / 2 - np.arange(5) * (2 * np.pi / 5)
    rounded = lambda x: np.copysign(np.floor(np.abs(x) + 0.5), x).astype(np.int64)
    vertices = rounded(np.column_stack((np.cos(angles), np.sin(angles))) * 8192)
    rom = []
    t = np.arange(1, 17)[:, None] / 16
    for a in range(5):
        for b in range(5):
            line = rounded(vertices[a] + (vertices[b] - vertices[a]) * t)
            delta = (b - a) % 5
            if delta in (1, 4):
                sweep = (-1 if delta == 1 else 1) * 2 * np.pi / 5
                angle = angles[a] + sweep * t[:, 0]
                arc = rounded(np.column_stack((np.cos(angle), np.sin(angle))) * 8192)
            else:
                arc = line.copy()
            line[-1] = arc[-1] = vertices[b]
            for (i, q), (ai, aq) in zip(line, arc):
                rom.append((int(aq & 65535) << 48) | (int(ai & 65535) << 32) | (int(q & 65535) << 16) | int(i & 65535))
    stored = [int(line.split('//')[0].strip(), 16) for line in
              (STAGE / 'rtl/svg_waveform.hex').read_text().splitlines() if line.split('//')[0].strip()]
    if rom != stored:
        raise AssertionError('Checked-in waveform ROM differs from independent geometry')
    memory(OUT / 'svg_waveform.hex', rom, 16)
    (OUT / 'rtl').mkdir(exist_ok=True)
    (OUT / 'rtl/svg_waveform.hex').write_bytes((STAGE / 'rtl/svg_waveform.hex').read_bytes())
    points = np.rint(np.column_stack((load_graph().real, load_graph().imag)) * 8192).astype(np.int64)
    signed = lambda x: x - 65536 if x & 32768 else x
    cases = []
    for amplitude in (0, 6000, 10000, 30000):
        seed, count = 7, 256
        rng = seed
        bits = []
        for _ in range(count):
            bits.append(rng & 1)
            rng = advance(rng)
        tx = encode(bits)
        words = []
        for a, b in zip(tx['node_path'][:-1], tx['node_path'][1:]):
            words.extend(rom[(int(a) * 5 + int(b)) * 16:(int(a) * 5 + int(b) + 1) * 16])
        clean = np.array([[signed((w >> 32) & 65535), signed((w >> 48) & 65535)] for w in words])
        i_rng, q_rng = seed ^ 0x9e3779b9, seed ^ 0x243f6a88
        received = []
        for i, q in clean:
            ni, nq = signed(i_rng >> 16) * amplitude // 32768, signed(q_rng >> 16) * amplitude // 32768
            received.append([np.clip(i + ni, -32768, 32767), np.clip(q + nq, -32768, 32767)])
            i_rng, q_rng = advance(i_rng), advance(q_rng)
        received = np.asarray(received, dtype=np.int64)
        rx_symbols = received[15::16]
        rx = decode(rx_symbols[:, 0] + 1j * rx_symbols[:, 1], points=points[:, 0] + 1j * points[:, 1])
        nearest = np.argmin(abs(rx_symbols[:, 0, None] + 1j * rx_symbols[:, 1, None] - (points[:, 0] + 1j * points[:, 1])) ** 2, axis=1)
        packed = lambda iq: ((iq[:, 1].astype(np.int64) & 65535) << 16) | (iq[:, 0].astype(np.int64) & 65535)
        name = f'wrapper{amplitude}'
        values = {'bits': bits, 'decoded': rx['decoded_bits'], 'nodes': tx['node_path'][1:],
                  'decodednodes': rx['node_path'][1:], 'iq': packed(clean[15::16]),
                  'rx': packed(rx_symbols), 'txwave': packed(clean), 'rxwave': packed(received)}
        files = {}
        for key, a in values.items():
            files[key] = OUT / f'{name}-{key}.hex'
            memory(files[key], a, 8 if key in ('iq', 'rx', 'txwave', 'rxwave') else 1)
        cases.append({'noise_amplitude': amplitude, 'seed': seed,
                      'symbol_errors': int(np.count_nonzero(nearest != tx['node_path'][1:])),
                      'payload_errors': int(np.count_nonzero(rx['decoded_bits'] != bits)),
                      'final_metric': int(rx['metric']), 'files': files})
    return cases


WRAPPER_TB = r'''`timescale 1ns/1ps
module tb_svg_wrapper;
reg clk=0;always #5 clk=~clk;
reg reset=1;
reg [5:0] avs_address=0;
reg avs_read=0,avs_write=0;
reg [31:0] avs_writedata=0;
wire [31:0] avs_readdata;
wire avs_waitrequest;
svg_modem_mm dut(.*);
reg expected_bits[0:255],expected_decoded[0:255];
reg [2:0] expected_nodes[0:261],expected_decodednodes[0:261];
reg [31:0] expected_iq[0:261],expected_rx[0:261],expected_txwave[0:4191],expected_rxwave[0:4191];
reg [31:0] value,low_metric,high_metric;
integer k,cycle;
initial begin
 repeat(4)@(negedge clk);reset=0;
 read_reg(0,value);if(value!==32'h53564701)$fatal(1,"wrapper ID");
 __WRAPPER_CASES__
 $display("PASS actual SVG Avalon wrapper payload/noise/waveforms/decoder/counters");$finish;
end

task automatic write_reg(input logic[5:0] addr,input logic[31:0] data);
begin
 @(negedge clk);avs_address=addr;avs_writedata=data;avs_write=1;
 @(negedge clk);avs_write=0;
end
endtask

task automatic read_reg(input logic[5:0] addr,output logic[31:0] data);
begin
 @(negedge clk);avs_address=addr;avs_read=1;
 @(negedge clk);data=avs_readdata;avs_read=0;
 if(avs_waitrequest)$fatal(1,"unexpected waitrequest");
end
endtask

task automatic expect_reg(input logic[5:0] addr,input logic[31:0] expected);
begin
 read_reg(addr,value);
 if(value!==expected)$fatal(1,"wrapper reg%0d index%0d got%0d expected%0d",addr,k,value,expected);
end
endtask

task automatic wrapper_case(input integer amplitude,input integer symbol_errors,input integer payload_errors,input logic[47:0] metric);
begin
 write_reg(2,256);write_reg(3,amplitude);write_reg(4,7);write_reg(5,1);write_reg(1,1);
 cycle=0;
 read_reg(1,value);
 while(value[0] && cycle<500000)begin
  repeat(10)@(negedge clk);cycle=cycle+10;read_reg(1,value);
 end
 if(cycle>=500000 || value!==2)$fatal(1,"wrapper status amplitude%0d status%0d",amplitude,value);
 expect_reg(15,symbol_errors);expect_reg(16,payload_errors);expect_reg(18,262);expect_reg(19,4192);
 expect_reg(20,metric[31:0]);expect_reg(21,{16'b0,metric[47:32]});expect_reg(22,320);expect_reg(23,16);
 for(k=0;k<262;k=k+1)begin
  write_reg(6,k);expect_reg(7,expected_iq[k]);expect_reg(8,expected_rx[k]);
  expect_reg(11,expected_nodes[k]);expect_reg(12,expected_decodednodes[k]);
  if(k<256)begin expect_reg(9,expected_bits[k]);expect_reg(10,expected_decoded[k]);end
 end
 for(k=0;k<4192;k=k+1)begin
  write_reg(6,k);expect_reg(13,expected_txwave[k]);expect_reg(14,expected_rxwave[k]);
 end
 $display("PASS wrapper amplitude%0d symbolerrors%0d payloaderrors%0d metric%0d",amplitude,symbol_errors,payload_errors,metric);
end
endtask
initial begin #100000000;$fatal(1,"wrapper timeout");end
endmodule
'''

WAVEFORM_TB = r'''module tb_svg_edge_waveform;
  logic clk=0, reset=1, in_valid=0, in_ready;
  logic [2:0] source_node=0, destination_node=0;
  logic arc_mode=0, out_valid, out_ready=0;
  logic signed [15:0] iq_i, iq_q;
  logic last, error;
  logic [63:0] expected[0:399];
  integer s,d,m,k,idx,hold;
  logic signed [15:0] exp_i,exp_q;
  svg_edge_waveform dut(.*);
  always #5 clk=~clk;
  initial begin #2000000; $fatal(1,"waveform timeout"); end
  initial begin
    $readmemh("svg_waveform.hex", expected);
    repeat(3) @(negedge clk); reset=0;
    for (m=0;m<2;m=m+1) begin
      for (s=0;s<5;s=s+1) begin
        for (d=0;d<5;d=d+1) begin
          @(negedge clk); while(!in_ready) @(negedge clk);
          source_node=s[2:0]; destination_node=d[2:0]; arc_mode=m[0]; in_valid=1;
          @(posedge clk); @(negedge clk); in_valid=0;
          for(k=0;k<16;k=k+1) begin
            while(!out_valid) @(negedge clk);
            idx=(s*5+d)*16+k;
            if(m==0) begin exp_i=$signed(expected[idx][15:0]); exp_q=$signed(expected[idx][31:16]); end
            else begin exp_i=$signed(expected[idx][47:32]); exp_q=$signed(expected[idx][63:48]); end
            if(iq_i!==exp_i || iq_q!==exp_q || last!==(k==15)) begin
              $display("FAIL edge=%0d->%0d arc=%0d k=%0d got=(%0d,%0d,last=%0b) expected=(%0d,%0d,last=%0b)",s,d,m,k,iq_i,iq_q,last,exp_i,exp_q,(k==15));
              $fatal(1);
            end
            hold=(s+d+k)%4;
            if(hold==0) begin
              repeat(2) begin @(posedge clk); if(!out_valid || iq_i!==exp_i || iq_q!==exp_q || last!==(k==15)) $fatal(1,"unstable under backpressure"); end
            end
            @(negedge clk); out_ready=1;
            @(posedge clk); @(negedge clk); out_ready=0;
          end
        end
      end
    end
    if(error) $fatal(1,"unexpected sticky error");
    $display("PASS 25 edges x 16 samples in both modes; backpressure stable");
    $finish;
  end
endmodule
'''

# Explicit scalar/vector probes avoid logging decoded/survivor/metric RAM arrays.
PROBES = {
    'modem': [f'/tb_svg_modem/{name}' for name in
              ('clk', 'reset', 'estart', 'dstart', 'payload_count', 'bit_valid', 'bit_ready',
               'valid', 'ready', 'iq_i', 'iq_q', 'node', 'coded_pair', 'sample_valid',
               'sample_ready', 'sample_i', 'sample_q', 'dbusy', 'ddone', 'derror',
               'read_address', 'decoded_bit', 'decoded_node', 'final_metric', 'nearest_valid', 'nearest_node')] +
             [f'/tb_svg_modem/dec/{name}' for name in
              ('state', 'step_index', 'scan', 'trace_joint', 'trace_index', 'best_metric',
               'metric_address', 'metric_write', 'metric_write_address', 'metric_write_data')],
    'waveform': [f'/tb_svg_edge_waveform/{name}' for name in
                 ('clk', 'reset', 'in_valid', 'in_ready', 'source_node', 'destination_node',
                  'arc_mode', 'out_valid', 'out_ready', 'iq_i', 'iq_q', 'last', 'error')],
    'wrapper': [f'/tb_svg_wrapper/{name}' for name in
                ('clk', 'reset', 'avs_address', 'avs_read', 'avs_write', 'avs_writedata',
                 'avs_readdata', 'avs_waitrequest')] +
               [f'/tb_svg_wrapper/dut/{name}' for name in
                ('state', 'busy', 'done', 'error', 'noise_amplitude', 'arc_mode',
                 'enc_valid', 'enc_ready', 'enc_node', 'enc_pair', 'enc_i', 'enc_q',
                 'wave_valid', 'wave_ready', 'wave_i', 'wave_q', 'wave_last', 'noisy_i',
                 'noisy_q', 'dec_ready', 'dec_busy', 'dec_done', 'dec_error',
                 'dec_address', 'dec_bit', 'dec_node', 'dec_metric', 'symbol_errors',
                 'payload_errors', 'nearest_valid', 'nearest_node', 'nearest_expected', 'symbol_index', 'received_index', 'wave_index', 'cycles')] +
               [f'/tb_svg_wrapper/dut/decoder/{name}' for name in
                ('state', 'step_index', 'scan', 'trace_joint', 'trace_index', 'best_metric',
                 'metric_address', 'metric_write', 'metric_write_address', 'metric_write_data')],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gui', action='store_true',
                        help='After passing tests, open the recorded wrapper waveform in Questa GUI')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    cases = build_vectors()
    blocks = []
    names = {'bits': 'bits', 'pairs': 'pairs', 'nodes': 'nodes', 'iq': 'iq',
             'rx': 'samples', 'decoded': 'expected_bits', 'decodednodes': 'expected_nodes', 'nearest': 'expected_nearest'}
    for case in cases:
        for key, array in names.items():
            limit = case['payload_bits'] if key in ('bits', 'decoded') else case['symbols']
            blocks.append(f'$readmemh("{tool_path(case["files"][key])}",{array},0,{limit - 1});')
        blocks.append(f'run_case("{case["name"]}",{case["payload_bits"]},48\'d{case["expected_metric"]});')
    tb = OUT / 'tb_svg_modem.sv'
    tb.write_text(TB.replace('__CASES__', '\n'.join(blocks)))
    sources = [STAGE / 'rtl/svg_graph_encoder.sv', STAGE / 'rtl/svg_graph_decoder.sv', tb]
    script = OUT / 'run.do'
    wrapper_cases = wrapper_vectors()
    blocks = []
    names = {'bits': 'expected_bits', 'decoded': 'expected_decoded', 'nodes': 'expected_nodes',
             'decodednodes': 'expected_decodednodes', 'iq': 'expected_iq', 'rx': 'expected_rx',
             'txwave': 'expected_txwave', 'rxwave': 'expected_rxwave'}
    for case in wrapper_cases:
        for key, array in names.items():
            blocks.append(f'$readmemh("{tool_path(case["files"][key])}",{array});')
        blocks.append(f'wrapper_case({case["noise_amplitude"]},{case["symbol_errors"]},{case["payload_errors"]},48\'d{case["final_metric"]});')
    wrapper_tb = OUT / 'tb_svg_wrapper.sv'
    wrapper_tb.write_text(WRAPPER_TB.replace('__WRAPPER_CASES__', '\n'.join(blocks)))
    waveform_tb = OUT / 'tb_svg_edge_waveform.sv'
    waveform_tb.write_text(WAVEFORM_TB)
    sources += [STAGE / 'rtl/svg_edge_waveform.sv', STAGE / 'rtl/svg_modem_mm.sv', wrapper_tb, waveform_tb]
    commands = ['onerror {quit -force -code 1}', 'vlib work', 'vmap work work',
                'vlog -sv ' + ' '.join('{' + tool_path(s) + '}' for s in sources)]
    for name, top in [('modem', 'tb_svg_modem'), ('waveform', 'tb_svg_edge_waveform'),
                      ('wrapper', 'tb_svg_wrapper')]:
        commands += [f'vsim -wlf {name}.wlf -voptargs=+acc work.{top}',
                     'onfinish stop', 'log ' + ' '.join(PROBES[name]), 'run -all']
    commands += ['quit -force -code 0']
    script.write_text('\n'.join(commands) + '\n')
    log = OUT / 'questa.log'
    with log.open('w') as stream:
        subprocess.run([str(tool_exe('vsim')), '-c', '-do', str(script)], cwd=OUT,
                       env=tool_env(), stdout=stream, stderr=subprocess.STDOUT,
                       check=True, timeout=300)
    if 'PASS actual SVG encoder and 320-state decoder RTL' not in log.read_text():
        raise RuntimeError('Actual RTL assertions did not pass; inspect ' + str(log))
    if 'PASS actual SVG Avalon wrapper' not in log.read_text() or 'PASS 25 edges' not in log.read_text():
        raise RuntimeError('Waveform/wrapper assertions did not pass')
    recordings = {}
    for name in PROBES:
        path = OUT / (name + '.wlf')
        if not path.is_file() or path.stat().st_size < 1024:
            raise RuntimeError('Missing or empty waveform recording: ' + str(path))
        recordings[name] = {'path': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size,
                            'signals': PROBES[name]}
    gui_script = OUT / 'view_wrapper.do'
    gui_script.write_text('view wave\n' +
                          '\n'.join('add wave ' + ('-radix decimal ' if probe.rsplit('/', 1)[-1] in ('enc_i', 'enc_q', 'wave_i', 'wave_q', 'noisy_i', 'noisy_q') else '') + '{' + probe + '}' for probe in PROBES['wrapper']) +
                          '\nconfigure wave -namecolwidth 280\nwave zoom full\n')
    proof = {'passed': True, 'hardware_access': False, 'actual_rtl': True,
             'waveform_recordings': recordings,
             'scope': 'encoder/waveform ROM/noise/Avalon capture/joint decoder; ideal timing, no FPGA fit or RF',
             'wrapper_cases': [{k: v for k, v in c.items() if k != 'files'} for c in wrapper_cases],
             'source_sha256': {str(s.relative_to(ROOT)): hashlib.sha256(s.read_bytes()).hexdigest() for s in [*sources, STAGE / 'rtl/svg_waveform.hex']},
             'cases': [{k: v for k, v in c.items() if k != 'files'} for c in cases],
             'tests': ['independent 171/133 encoding', 'signed CI16 exact endpoints',
                       'input pauses and ready/valid output backpressure', '1-bit and 256-bit frames',
                       'noisy correction and severe-noise failures', 'extreme CI16 path metric overflow',
                       'all decoded payload bits and all selected nodes', 'exact integer final path metrics', 'registered nearest-node pulses: all nodes, exact count and6-cycle latency',
                       'invalid zero and257 payload rejection', 'all25 edge waveforms in both modes',
                       'full Avalon readback of4192 TX/RX samples at each of4 noise levels']}
    (OUT / 'validation.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof, indent=2))
    if args.gui:
        gui_log = OUT / 'questa-gui.log'
        with gui_log.open('w') as stream:
            process = subprocess.Popen([str(tool_exe('vsim')), '-gui', '-view',
                                        str(OUT / 'wrapper.wlf'), '-do', str(gui_script)],
                                       cwd=OUT, env=tool_env(), stdout=stream,
                                       stderr=subprocess.STDOUT)
        print(f'Questa waveform viewer launched (PID{process.pid}); log: {gui_log}')


if __name__ == '__main__':
    main()
