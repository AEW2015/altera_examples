#!/usr/bin/env python3
"""Verify the already-loaded checkpoint06 modem with real FPGA symbol transactions.

Does not program/flash the board, open radio UART, or transmit RF. Stop any other
JTAG/acquisition owner first. The image ID is checked before writing test data.
"""
import argparse,json,sys,time
from pathlib import Path
import numpy as np
from common import ROOT
sys.path.insert(0,str(ROOT/'cyberether'))
from modem_fpga import ModemFPGA
from modem_reference import BITS_PER_SYMBOL,conv_encode,map_bits,viterbi_decode,fixedpoint_soft_demapper
from nios_fir import NiosFir
from notebook_progress import progress

def check(owner,output=None,payload_bits=32):
    modem=ModemFPGA(owner);results=[]
    for mode,bps in BITS_PER_SYMBOL.items():
        with progress('Verify FPGA modem: '+mode):
            bits=np.random.default_rng(123+bps).integers(0,2,payload_bits,dtype=np.uint8)
            tx=modem.encode(bits,bps=bps)
            np.testing.assert_array_equal(tx['coded'],conv_encode(bits))
            coded=tx['coded'];padded=np.pad(coded,(0,(-len(coded))%bps))
            expected=np.rint(np.column_stack((map_bits(padded,mode).real,map_bits(padded,mode).imag))*8192).astype(np.int16)
            np.testing.assert_array_equal(tx['iq'],expected)
            rx=modem.decode(tx['iq']);np.testing.assert_array_equal(rx['bits'],bits)
            expected_llr=fixedpoint_soft_demapper(tx['iq'],mode)[:len(coded)]
            np.testing.assert_array_equal(rx['llr'],expected_llr)
            assert rx['raw_errors']==0 and rx['decoded_errors']==0
            results.append(dict(mode=mode,case='noiseless_symbol_loopback',payload_bits=len(bits),coded_bits=len(coded),symbols=len(expected),raw_errors=rx['raw_errors'],decoded_errors=rx['decoded_errors'],encode_cycles=tx['cycles'],decode_cycles=rx['cycles']))
            if bps==6:
                noisy=np.clip(tx['iq'].astype(np.int64)+np.rint(np.random.default_rng(405).normal(0,850,tx['iq'].shape)),-32768,32767).astype(np.int16)
                rx=modem.decode(noisy)
                np.testing.assert_array_equal(rx['llr'],fixedpoint_soft_demapper(noisy,mode)[:len(coded)])
                expected_bits=viterbi_decode(rx['llr'],soft=True)
                np.testing.assert_array_equal(rx['bits'],expected_bits)
                errors=int(np.count_nonzero(rx['bits']!=bits))
                assert rx['decoded_errors']==errors and rx['raw_errors']>0 and errors==0
                results.append(dict(mode=mode,case='host_added_symbol_noise_on_FPGA_decoder',payload_bits=len(bits),coded_bits=len(coded),raw_errors=rx['raw_errors'],decoded_errors=errors,decode_cycles=rx['cycles'],noise_sigma_q313=850))
    result=dict(status='PASS_HARDWARE_SYMBOL_MODEM',tested_unix=time.time(),image_id='4d440601',device='Atum A3 Nano / Agilex 3',source='Host test bits and symbol impairments; FPGA encoding/mapping/demapping/Viterbi',rf_transmitted=False,waveform_synchronization_in_fpga=False,results=results)
    selection=ROOT/'cyberether/run/active-fpga.json'
    if selection.exists():
        result['program_selection']=json.loads(selection.read_text())
        result['program_selection_scope']='Local programming record; block ID is read from hardware; bitstream SHA is not device readback'
    if output:
        path=Path(output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,indent=2)+'\n')
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'cyberether/run/modem-hardware-proof.json');p.add_argument('--payload-bits',type=int,choices=[32,256],default=32,help='32-bit integration check or slower full-capacity stress case');a=p.parse_args()
    with NiosFir()as owner:result=check(owner,a.output,a.payload_bits)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
