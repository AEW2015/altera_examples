#!/usr/bin/env python3
"""Replay real RF recovered BPSK/QPSK symbols into an already-loaded FPGA modem.

Requires checkpoint06. Does not program an image, open the radio UART, or send
RF. Carrier/timing/frame acquisition stays on the host; FPGA soft demapping and
terminated K7 Viterbi decoding operate on the measured recovered symbols.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
from common import ROOT
sys.path.insert(0,str(ROOT/'cyberether'))
from modem_fpga import ModemFPGA
from modem_reference import conv_encode, fixedpoint_soft_demapper, viterbi_decode
from nios_fir import NiosFir
from notebook_progress import task
from rf_bpsk import crc8, frame_bits, int_bits


def select_frames(proof, max_frames=1):
    """Select by sync only: CRC failures must not be excluded from BER checks."""
    if proof.get('kind') not in ('physical_rf_bpsk','physical_rf_qpsk'):
        raise ValueError('Expected physical_rf_bpsk or physical_rf_qpsk capture proof; synthetic inputs are not accepted')
    qpsk = proof['kind']=='physical_rf_qpsk'
    symbol_count = 22 if qpsk else 44
    max_sync_errors = 2 if qpsk else 1
    if not isinstance(max_frames,int) or not 1<=max_frames<=100:
        raise ValueError('max_frames must be1..100')
    selected=[]
    for row_index,row in enumerate(proof.get('rows',[])):
        payload=row.get('config',{}).get('payload')
        frame_bits(payload)  # Contract/range check, before JTAG writes.
        digest=row.get('transport',{}).get('payload_sha256','')
        if len(digest)!=64 or any(x not in '0123456789abcdef' for x in digest.lower()):
            raise ValueError('Missing valid captured CI8 payload SHA-256')
        for candidate_index,frame in enumerate(row.get('report',{}).get('candidates',[])):
            if not isinstance(frame.get('sync_errors'),int) or not 0<=frame['sync_errors']<=max_sync_errors:
                continue
            symbols=np.asarray(frame.get('symbols'),dtype=float)
            if symbols.shape!=(symbol_count,2) or not np.isfinite(symbols).all():
                raise ValueError(f'Expected{symbol_count} finite recovered complex symbols')
            selected.append((row_index,candidate_index,payload,digest,frame,symbols))
            if len(selected)>=max_frames:
                return selected
    if not selected:
        raise ValueError('No sync-acquired complete frames available; nothing sent to FPGA')
    return selected


def check(owner,proof,output=None,max_frames=1,input_path=None):
    selected=select_frames(proof,max_frames)
    mode='QPSK' if proof['kind']=='physical_rf_qpsk' else 'BPSK'
    bps=2 if mode=='QPSK' else 1
    # FPGA QPSK LUT has00=(-I,-Q). RF cardinal Gray00=+I,01=-Q,
    # 11=-I,10=+Q therefore needs a -135deg rotation, not +45deg.
    rotation_radians=-3*np.pi/4 if bps==2 else 0.
    # Constructor reads actual hardware blockID before writes.
    modem=ModemFPGA(owner)
    block_id=modem.read(0)
    results=[]
    for row_index,candidate_index,payload,digest,frame,symbols in selected:
        info=np.r_[int_bits(payload,8),int_bits(crc8(bytes([payload])),8)]
        expected_code=conv_encode(info)
        expected_frame_code=frame_bits(payload)[16:60]
        np.testing.assert_array_equal(expected_code,expected_frame_code)
        started=time.monotonic()
        # Encode configures the actual modem length/modulation mode and golden RAM.
        # The following decode input is measured RF IQ, not this golden IQ.
        tx=modem.encode(info,bps=bps)
        np.testing.assert_array_equal(tx['coded'],expected_code)
        measured_complex=symbols[:,0]+1j*symbols[:,1]
        rotated=measured_complex*np.exp(1j*rotation_radians)
        frontend_symbols=np.column_stack((rotated.real,rotated.imag))
        rounded=np.rint(frontend_symbols*8192.)
        limited=np.clip(rounded,-32767,32767).astype(np.int16)
        quantization_clips=int(np.count_nonzero(rounded!=limited))
        rx=modem.decode(limited)
        wall=time.monotonic()-started
        expected_llr=fixedpoint_soft_demapper(limited,mode)
        np.testing.assert_array_equal(rx['llr'],expected_llr)
        reference_bits=viterbi_decode(expected_llr,soft=True,terminated=True)
        np.testing.assert_array_equal(rx['bits'],reference_bits)
        raw_errors=int(np.count_nonzero((expected_llr<0)!=expected_code))
        info_errors=int(np.count_nonzero(reference_bits!=info))
        if int(rx['raw_errors'])!=raw_errors or int(rx['decoded_errors'])!=info_errors:
            raise AssertionError('FPGA BER counters disagree with independent references')
        received_payload=int(np.packbits(reference_bits[:8])[0])
        received_crc=int(np.packbits(reference_bits[8:])[0])
        crc_valid=received_crc==crc8(bytes([received_payload]))
        payload_errors=int(np.count_nonzero(reference_bits[:8]!=info[:8]))
        result=dict(row_index=row_index,candidate_index=candidate_index,
                    captured_ci8_sha256=digest,start_sample=frame.get('start_sample'),
                    host_sync_score=frame.get('sync_score'),host_sync_errors=frame['sync_errors'],
                    host_crc_ok=frame.get('crc_ok'),known_payload=payload,
                    decoded_payload=received_payload,crc_received=received_crc,crc_ok=crc_valid,
                    coded_errors=raw_errors,coded_bits=44,payload_errors=payload_errors,payload_bits=8,
                    info_errors=info_errors,info_bits=16,fpga_counter_raw_errors=int(rx['raw_errors']),
                    fpga_counter_decoded_errors=int(rx['decoded_errors']),
                    symbol_format='CI16 Q3.13, normalized measured RX late-symbol averages',
                    modulation=mode,bits_per_symbol=bps,measured_symbol_count=len(symbols),
                    host_frontend_rotation_radians=float(rotation_radians),
                    host_frontend_rotation_degrees=float(np.degrees(rotation_radians)),
                    measured_symbols_before_rotation=symbols.tolist(),
                    quantization_clipped_components=quantization_clips,
                    symbols_ci16=limited.tolist(),fpga_llr=np.asarray(rx['llr']).tolist(),
                    fpga_decoded_info=np.asarray(rx['bits']).tolist(),
                    llr_matches_independent_integer_reference=True,
                    bits_match_independent_viterbi_reference=True,
                    encode_cycles=int(tx['cycles']),decode_cycles=int(rx['cycles']),
                    configured_clock_hz=50000000,
                    decode_kernel_seconds=int(rx['cycles'])/50000000.,
                    jtag_transaction_wall_seconds=wall)
        results.append(result)
    result=dict(kind=proof['kind']+'_fpga',status='PASS_FPGA_RF_SYMBOL_REPLAY',
                tested_unix=time.time(),device='Atum A3 Nano / Agilex 3',
                hardware_block_id=f'{block_id:08x}',host_processing='RF carrier/timing/frame acquisition, amplitude normalization and explicit constellation convention rotation',
                frontend_rotation_degrees=float(np.degrees(rotation_radians)),
                modulation=mode,
                fpga_processing=f'{mode} integer soft demapper and terminated K7(171,133) Viterbi',
                transmitted_by_this_check=False,waveform_synchronization_in_fpga=False,
                selection='Sync-acquired candidates, regardless of CRC outcome; no CRC-based BER filtering',
                capture_hash_scope='Copied from transport provenance; this replay does not reacquire RF or rehash raw CI8 files',
                source_proof=str(input_path) if input_path else None,
                frames_checked=len(results),results=results,
                coded_errors=sum(x['coded_errors'] for x in results),coded_bits=44*len(results),
                payload_errors=sum(x['payload_errors'] for x in results),payload_bits=8*len(results),
                crc_failures=sum(not x['crc_ok'] for x in results),
                unobserved_gaps='Only selected captured frames are measured; intervening RF is unobserved')
    if input_path:
        result['source_proof_sha256']=hashlib.sha256(Path(input_path).read_bytes()).hexdigest()
    selection=ROOT/'cyberether/run/active-fpga.json'
    if selection.exists():
        result['program_selection']=json.loads(selection.read_text())
        result['program_selection_scope']='Local programming record; block ID read from hardware; bitstream SHA is not device readback'
    if output:
        target=Path(output)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    return result


@task('Replay recovered RF symbols through FPGA')
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,type=Path,help='Physical capture proof.json from RF BPSK/QPSK harness')
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--max-frames',type=int,default=1,help='Default1 limits slow JTAG transfers; selects by sync, regardless of CRC')
    args=parser.parse_args()
    proof=json.loads(args.input.read_text())
    select_frames(proof,args.max_frames) # Validate before opening the JTAG owner.
    with NiosFir() as owner:
        result=check(owner,proof,args.output,args.max_frames,args.input)
    print(json.dumps(dict(status=result['status'],frames_checked=result['frames_checked'],
                          coded_errors=result['coded_errors'],coded_bits=result['coded_bits'],
                          payload_errors=result['payload_errors'],payload_bits=result['payload_bits'],
                          output=str(args.output)),indent=2))


if __name__=='__main__':
    main()
