#!/usr/bin/env python3
"""Explicit SPIQ0002 FPGA-meter hardware qualification; never programs/flashes hardware."""
import argparse,json,sys,time,hashlib,fcntl
from contextlib import ExitStack
from pathlib import Path
from common import ROOT,resolve_uart
sys.path.insert(0,str(ROOT/'cyberether'))
from spi_ci8 import Capture,PACKET,decode
from spi_meter import decode_summary,verify

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--rf',action='store_true',help='separate fixed-channel8 raw-RX SPI profile; no synthetic comparison');p.add_argument('--port');p.add_argument('--output',type=Path,required=True)
 p.add_argument('--confirm-spi-image',action='store_true',help='required: separate SPI image loaded, PMOD B SPI switch set')
 a=p.parse_args()
 if not a.confirm_spi_image:p.error('load and identify the separate SPI qualification image first; requires --confirm-spi-image')
 a.output.mkdir(parents=True,exist_ok=False)
 import serial
 c=Capture();started=time.monotonic();transactions=0;discarded=0
 lock=ROOT/'cyberether/run/rf-link-capture.lock';lock.parent.mkdir(parents=True,exist_ok=True)
 with ExitStack() as stack:
  lease=stack.enter_context(lock.open('a'))
  try:fcntl.flock(lease.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise RuntimeError('RF acquisition owner busy; stop captures before SPI qualification')
  port=stack.enter_context(serial.Serial(resolve_uart(a.port),2000000,timeout=2,write_timeout=2,exclusive=True))
  port.reset_input_buffer();port.write(b'I')
  if port.read(8)!=b'SPIQ0002':raise RuntimeError('FPGA SPIQ0002 identity missing; use the separate meter SOF')
  port.write(b'M');baseline=decode_summary(port.read(64))
  if a.rf:
   # Force a synthetic boundary first, so an already-armed RF packet from a
   # previous run cannot be mistaken for a newly acquired RF snapshot.
   port.write(b'T');old=decode(port.read(PACKET));transactions+=1;discarded+=1
   if old.source!=2 or old.total!=32760:raise RuntimeError('wrong PMOD B capture profile')

  while not c.complete:
   if transactions>=96:raise RuntimeError('no complete capture within96 bounded transactions')
   port.write(b'R' if a.rf else b'T');raw=port.read(PACKET)
   if raw==bytes(PACKET):raise RuntimeError('ESP32 SPI READY did not assert within FPGA 1s wait')
   chunk=decode(raw);transactions+=1
   if chunk.source!=2 or chunk.total!=32760:raise RuntimeError('wrong PMOD B capture profile')
   if chunk.synthetic==a.rf:
    discarded+=1;c=Capture()
    if discarded>8:raise RuntimeError('SPI firmware did not apply requested synthetic/RF selection')
    continue
   # A DMA packet can remain armed after a previous 5s timeout. Drain it,
   # and explicitly count incomplete captures; never splice their payloads.
   if c.identity is None and chunk.offset:
    discarded+=1;continue
   if c.identity is not None and (chunk.source,chunk.sequence,chunk.total,chunk.synthetic)!=c.identity:
    discarded+=1;c=Capture()
    if chunk.offset:continue
   c.append(raw)
  (a.output/'capture.ci8').write_bytes(c.data)
  port.write(b'M');observed=decode_summary(port.read(64))
  (a.output/'meter-summary.json').write_text(json.dumps(observed,indent=2)+'\n')
  try:meter=verify(observed,c.data,c.identity[1],c.identity[3],baseline['commit_count'])
  except ValueError as error:
   (a.output/'failure.json').write_text(json.dumps(dict(error=str(error),baseline=baseline,observed=observed,sequence=c.identity[1],sha256=hashlib.sha256(c.data).hexdigest()),indent=2)+'\n')
   raise
 elapsed=time.monotonic()-started
 expected=bytes((n*37+11)&255 for n in range(len(c.data)))
 if not a.rf and bytes(c.data)!=expected:raise RuntimeError('synthetic sequence bytes differ')
 (a.output/'capture.ci8').write_bytes(c.data)
 proof=dict(fpga_meter=meter,fpga_identity='SPIQ0002',requested_mode='rf' if a.rf else 'synthetic',fresh_rf_boundary=a.rf,readback_mode='synthetic' if c.identity[3] else 'rf',kind='physical_rf_spi_fpga_meter' if a.rf else 'synthetic_spi_fpga_meter_hardware',source=c.identity[0],sequence=c.identity[1],
   samples=len(c.data)//2,bytes=len(c.data),transactions=transactions,discarded_incomplete_captures_or_chunks=discarded,elapsed_s=elapsed,
   end_to_end_bytes_s=len(c.data)/elapsed,sha256=hashlib.sha256(c.data).hexdigest(),
   payload_exact=None if a.rf else True,channel=8 if a.rf else None,sample_rate_nominal=16000000 if a.rf else None,crc_all_pass=True,spi_hz_nominal=5000000,
   scope='FPGA validates SPI capture and computes power/peak/clip meters; host transports and verifies integer reference; UART egress remains limiting')
 (a.output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))
if __name__=='__main__':main()
