"""Decode FPGA SPIQ0002 integer-meter summaries and verify against saved CI8."""
import struct,zlib
SUMMARY_BYTES=64
CLOCK_HZ=50_000_000

def decode_summary(raw):
    if len(raw)!=SUMMARY_BYTES:raise ValueError('FPGA meter summary length')
    if zlib.crc32(raw[:60])!=struct.unpack('<I',raw[60:])[0]:raise ValueError('FPGA meter summary CRC')
    (magic,version,flags,error,reserved,sequence,commits,rejects,samples,power,peak,
     clips,components,cycles,total,chunks)=struct.unpack('<4sBBBBIIIIQIIIQII',raw[:60])
    if magic!=b'SPM1' or version!=1 or flags&~3 or reserved:raise ValueError('FPGA meter summary header')
    return dict(valid=bool(flags&1),synthetic=bool(flags&2),last_error=error,
        sequence=sequence,commit_count=commits,reject_count=rejects,samples=samples,
        power_sum=power,peak_power=peak,clip_samples=clips,clip_components=components,
        ingress_cycles=cycles,bytes=total,chunks=chunks)

def integer_reference(ci8):
    if not ci8 or len(ci8)%2:raise ValueError('CI8 must contain complete I,Q pairs')
    power=peak=clips=components=0
    for at in range(0,len(ci8),2):
        i=ci8[at];q=ci8[at+1]
        if i>127:i-=256
        if q>127:q-=256
        p=i*i+q*q;power+=p;peak=max(peak,p)
        ci=i in (-128,127);cq=q in (-128,127)
        clips+=int(ci or cq);components+=int(ci)+int(cq)
    return dict(samples=len(ci8)//2,power_sum=power,peak_power=peak,clip_samples=clips,clip_components=components)

def verify(summary,ci8,sequence,synthetic,previous_commits):
    if not summary['valid'] or summary['last_error']:raise ValueError('FPGA meter has no fresh valid capture')
    if summary['sequence']!=sequence or summary['synthetic']!=synthetic:raise ValueError('FPGA meter capture identity differs')
    advance=(summary['commit_count']-previous_commits)&0xffffffff
    if not 0<advance<0x80000000:raise ValueError('FPGA meter commit did not advance')
    if summary['bytes']!=len(ci8) or summary['chunks']!=32 or not summary['ingress_cycles']:
        raise ValueError('FPGA meter byte/chunk/cycle accounting')
    reference=integer_reference(ci8)
    for key,value in reference.items():
        if summary[key]!=value:raise ValueError(f'FPGA meter {key} differs: {summary[key]} != {value}')
    return dict(**summary,reference_match=True,clock_hz_nominal=CLOCK_HZ,
        ingress_s=summary['ingress_cycles']/CLOCK_HZ,
        ingress_payload_bytes_s=len(ci8)*CLOCK_HZ/summary['ingress_cycles'])
