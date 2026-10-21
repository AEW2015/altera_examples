"""Same-capture SPI/FIR reference checks and display data; no hardware I/O.

Display FFT/logarithms run on the host. Validation compares the actual FPGA
output bytes with an independent integer convolution of the captured CI8.
"""
from __future__ import annotations
import hashlib
import time
import zlib
import numpy as np
from nios_fir import fixed_reference,PROFILES


def ci8(raw):
    raw=bytes(raw)
    if not raw or len(raw)%2:
        raise ValueError('nonempty complete signed CI8 pairs required')
    return np.frombuffer(raw,dtype=np.int8).reshape(-1,2)


def verify_fir(raw,filtered,taps,*,nearest,raw_crc=None,filtered_crc=None,reported_clips=None):
    """Input/output of ONE capture; caller must establish capture association."""
    a,b=ci8(raw),ci8(filtered)
    taps=list(taps)
    if a.shape!=b.shape or len(taps)!=16 or any(not isinstance(v,int) or not -32768<=v<=32767 for v in taps):
        raise ValueError('same sample count and sixteen signed Q15 taps required')
    crcs=[zlib.crc32(bytes(raw)),zlib.crc32(bytes(filtered))]
    for supplied,actual in zip((raw_crc,filtered_crc),crcs):
        if supplied is not None and supplied!=actual:
            raise ValueError('FIR raw/filtered payload CRC mismatch')
    expected=fixed_reference(a,taps,round_nearest=nearest)
    error=int(np.max(np.abs(expected.astype(np.int16)-b.astype(np.int16))))
    if error:
        raise AssertionError(f'FPGA FIR differs from independent integer reference by {error}')
    accum=np.column_stack([np.convolve(a[:,lane].astype(np.int64),taps)[:len(a)] for lane in range(2)])
    scaled=(accum+(16384 if nearest else 0))>>15
    clips=int(np.count_nonzero(np.any((scaled>127)|(scaled < -128),axis=1)))
    if reported_clips is not None and reported_clips!=clips:
        raise ValueError('FPGA FIR clip counter disagrees with independent reference')
    return dict(bit_exact=True,max_reference_error=error,raw_crc=crcs[0],filtered_crc=crcs[1],
        raw_crc_valid=True,filtered_crc_valid=True,
        samples=len(a),clips=clips,coefficients=taps,round_nearest=bool(nearest),
        reference_scope='Independent host signed CI8/Q15 convolution, per-capture zero state, rounding and saturation of SAME captured raw bytes')


def display_plots(raw,filtered=None,*,sample_rate_hz=16000000,max_points=1024):
    """Bounded browser plots, coherent-gain-corrected host FFT; not FPGA FFT."""
    if not np.isfinite(sample_rate_hz) or sample_rate_hz<=0 or not 16<=max_points<=2048:
        raise ValueError('positive sample rate and16..2048 display points required')
    inputs=[ci8(raw)]
    if filtered is not None:
        inputs.append(ci8(filtered))
    if any(a.shape!=inputs[0].shape for a in inputs):
        raise ValueError('raw/filtered display sample counts differ')
    n=len(inputs[0]);window=np.hanning(n) if n>2 else np.ones(n)
    f=np.fft.fftshift(np.fft.fftfreq(n,1/sample_rate_hz))/1e6
    # Max pool adjacent FFT bins, retaining narrow peaks across the full range.
    edges=np.linspace(0,n,min(n,max_points)+1,dtype=int)
    x=[float(np.mean(f[lo:hi])) for lo,hi in zip(edges[:-1],edges[1:])]
    spec=dict(x=x,x_label='Baseband frequency (MHz)',x_unit='MHz',y_label='Peak FFT bin (dBFS)',
        processing='Host FFT/logarithm, Hann coherent gain corrected, full scale complex amplitude128; max pooled for display')
    # Consecutive samples retain waveform timing; striding a full burst would
    # alias its displayed oscillation even while the full FFT stayed correct.
    indices=np.arange(min(n,384,max_points))
    waveform=dict(sample=indices.tolist(),x_label='Sample index',y_label='Signed CI8 code',
        scope='First consecutive samples; full capture used for spectrum and verification')
    for name,a in zip(('raw','filtered'),inputs):
        z=a[:,0].astype(float)+1j*a[:,1].astype(float)
        magnitude=np.abs(np.fft.fftshift(np.fft.fft(z*window)))/(128*np.sum(window))
        db=20*np.log10(np.maximum(magnitude,1e-12))
        spec[name]=[float(np.max(db[lo:hi])) for lo,hi in zip(edges[:-1],edges[1:])]
        waveform[name+'_i']=a[indices,0].tolist();waveform[name+'_q']=a[indices,1].tolist()
    return dict(spectrum=spec,time=waveform)


def snapshot(raw,filtered,*,kind,requested,readback,verification,timing,provenance):
    """Explicit origin is required: software fixtures can never imply RF tests."""
    if kind not in ('physical_rf_spi_fir','synthetic_spi_fir_hardware','synthetic_spi_fir_simulation'):
        raise ValueError('explicit RF/hardware-fixture/software-fixture origin required')
    provenance=dict(provenance)
    provenance.update(raw_sha256=hashlib.sha256(bytes(raw)).hexdigest(),
        filtered_sha256=hashlib.sha256(bytes(filtered)).hexdigest(),
        host_processing='Transport/reference verification and display FFT/logarithms',raw_uploaded=False)
    if kind=='synthetic_spi_fir_simulation':
        provenance['fpga_processing']='Not hardware tested; software fixture only'
        provenance['raw_uploaded']=None
    return dict(schema='spi-pipeline-v1',status='PASS',updated_at=time.time(),kind=kind,
        requested=dict(requested),readback=dict(readback),verification=dict(verification),
        timing=dict(timing),provenance=provenance,
        plots=display_plots(raw,filtered,sample_rate_hz=requested.get('sample_rate_hz',16000000)))


def verify_restoration(actual_status,actual_taps,original_status,original_taps,*,expected_profile=None):
    """Restore commands alone are insufficient: require resulting settings."""
    if actual_status.get('pair')!=0:
        raise ValueError('FIR cleanup did not disable paired streaming')
    for key in ('configured_round','configured_profile'):
        expected=expected_profile if key=='configured_profile' and expected_profile is not None else original_status.get(key,0)
        if actual_status.get(key)!=expected:
            raise ValueError(f'FIR cleanup setting readback mismatch: {key}')
    if list(actual_taps)!=list(original_taps):
        raise ValueError('FIR cleanup coefficient readback mismatch')
    return True


def restoration_plan(original_status,original_taps):
    """Preserve exact coefficients; an inconsistent preset label becomes custom.

    COEFF intentionally marks profile0. PRESET must only be used when the saved
    coefficient bank really equals that named profile, otherwise it changes data.
    """
    original_profile=original_status.get('configured_profile',0)
    canonical=original_profile in PROFILES and list(original_taps)==PROFILES[original_profile]
    expected_profile=original_profile if canonical else 0
    return dict(method='preset' if canonical else 'coefficients',profile=expected_profile,
        profile_label_preserved=expected_profile==original_profile,
        normalized_profile_from=original_profile if expected_profile!=original_profile else None,
        reason='Exact original coefficient values restored; inconsistent preset label normalized to custom0' if expected_profile!=original_profile else 'Exact coefficient values and profile label restored')
