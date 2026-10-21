"""Small reloadable 16-tap Q15 lesson filters; no SciPy or device access required."""
import hashlib
import struct
import numpy as np
from nios_fir import PROFILES


def validate_coefficients(values):
    if not isinstance(values,list)or len(values)!=16 or any(type(x)is not int or not -32768<=x<=32767 for x in values):
        raise ValueError('Provide exactly 16 signed Q15 integers (-32768..32767)')
    return values.copy()


def q15(values):
    """Quantize 1..16 real taps, pad with zeros; reject overflow, never normalize silently."""
    if np.iscomplexobj(values):raise ValueError('Real coefficients shared by I and Q are required')
    h=np.asarray(values,dtype=float)
    if h.ndim!=1 or not 1<=len(h)<=16 or not np.all(np.isfinite(h)):
        raise ValueError('Provide 1..16 finite real taps')
    h=np.rint(h*32768)
    if np.any(h < -32768)or np.any(h > 32767):
        raise ValueError('Q15 overflow; scale the coefficients explicitly before quantizing')
    return np.pad(h.astype(int),(0,16-len(h))).tolist()


def coefficient_hash(coefficients):
    return hashlib.sha256(struct.pack('<16h',*validate_coefficients(coefficients))).hexdigest()


def lowpass(cutoff):
    if not np.isfinite(cutoff)or not 0<cutoff<.5:raise ValueError('Cutoff must be between 0 and 0.5 cycles/sample')
    n=np.arange(15)-7
    h=2*cutoff*np.sinc(2*cutoff*n)*np.hamming(15)
    return h/h.sum()


def peak_normalize(h):
    return h/max(1.,float(np.max(np.abs(np.fft.fft(h,8192)))))


def _entry(name,title,description,values,profile=0):
    coefficients=validate_coefficients(values)
    return dict(id=name,title=title,description=description,coefficients=coefficients,profile=profile,
        sha256=coefficient_hash(coefficients),taps=16,dc_gain=sum(coefficients)/32768,
        l1_gain=sum(abs(v)for v in coefficients)/32768)


def _catalog():
    entries=[]
    def add(name,title,description,values,profile=0):entries.append(_entry(name,title,description,values,profile))
    add('hamming','Hamming low-pass (16 taps)','Existing broad low-pass; compare with the averaging filters.',PROFILES[2],2)
    add('boxcar','Moving average (16 samples)','Strong smoothing and regularly spaced spectral zeros.',PROFILES[1],1)
    add('identity','Identity / near-unity','One tap at 32767/32768; useful for verifying the reload path.',[32767]+[0]*15)
    add('delay-7','Seven-sample delay','Moves the waveform seven samples; magnitude response stays nearly flat.',[0]*7+[32767]+[0]*8)
    add('average-4','Moving average (4 samples)','Less smoothing, less delay than the 16-sample average.',q15([.25]*4))
    add('binomial-5','Binomial smoother (5 taps)','Weights 1:4:6:4:1; gentle smoothing and a Nyquist zero.',q15(np.array([1,4,6,4,1])/16))
    gaussian=np.exp(-.5*((np.arange(15)-7)/2)**2);gaussian/=gaussian.sum()
    add('gaussian','Gaussian smoother (15 taps)','A bell-shaped impulse response with gradual frequency roll-off.',q15(gaussian))
    add('lowpass-narrow','Narrow low-pass (0.08 Fs)','Keeps the −0.5 MHz FIR test tone; suppresses the +4 MHz test tone at Fs=16 MHz.',q15(lowpass(.08)))
    add('lowpass-wide','Wide low-pass (0.20 Fs)','A wider passband; compare the transition region with narrow low-pass.',q15(lowpass(.20)))
    high=-lowpass(.20);high[7]+=1
    add('highpass','High-pass (0.20 Fs)','Suppresses low frequencies and preserves the high-frequency test tone.',q15(peak_normalize(high)))
    band=lowpass(.43)-lowpass(.22)
    add('bandpass','Band-pass (0.22–0.43 Fs)','Passes the +4 MHz FIR test tone at Fs=16 MHz; attenuates the −0.5 MHz tone.',q15(peak_normalize(band)))
    add('notch-4mhz','Notch at 0.25 Fs (4 MHz @16 MS/s)','Removes the +4 MHz FIR test tone while retaining the −0.5 MHz tone.',q15([.5,0,.5]))
    notch=np.array([1,-2*np.cos(2*np.pi*.375),1]);notch/=notch.sum()
    add('notch-6mhz','Notch at 0.375 Fs (6 MHz @16 MS/s)','Targets a 6 MHz baseband offset at 16 MS/s; the FIR quick test instead has a 4 MHz tone.',q15(notch))
    add('dc-blocker','DC blocker / first difference','Half-scaled current minus previous sample; constant input vanishes.',q15([.5,-.5]))
    add('echo-comb','Echo / comb (8-sample spacing)','Mix current input and an eight-sample-delayed copy; produces repeated notches.',q15([.5]+[0]*7+[.5]))
    return {e['id']:e for e in entries}

CATALOG=_catalog()


def catalog():
    return [dict(e,coefficients=e['coefficients'].copy())for e in CATALOG.values()]


def resolve_filter(config):
    view=config.get('view','hamming')
    name=view if view in ('boxcar','hamming')else config.get('fir_filter','hamming')
    if name=='custom':return _entry('custom','Custom Q15 filter','User-supplied real coefficients; shared by I and Q.',validate_coefficients(config.get('fir_coefficients')))
    if name not in CATALOG:raise ValueError('Unknown FIR example')
    e=CATALOG[name]
    return dict(e,coefficients=e['coefficients'].copy())


def plot_filter(name='notch-4mhz',rate=16000000,coefficients=None):
    """Offline educational response; never opens serial or changes the FPGA."""
    import matplotlib.pyplot as plt
    spec=resolve_filter(dict(view='custom',fir_filter='custom'if coefficients is not None else name,fir_coefficients=coefficients))
    h=np.array(spec['coefficients'])/32768
    f=np.fft.fftshift(np.fft.fftfreq(4096,1/rate))/1e6
    db=20*np.log10(np.maximum(abs(np.fft.fftshift(np.fft.fft(h,4096))),1e-6))
    fig,axes=plt.subplots(1,2,figsize=(11,3.5))
    axes[0].stem(np.arange(16),h);axes[0].set(xlabel='Tap index',ylabel='Q15 / 32768',title='Quantized impulse response')
    axes[1].plot(f,db);axes[1].set(xlabel='Baseband frequency (MHz)',ylabel='Magnitude (dB)',ylim=(-90,5),title='Host coefficient response')
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle(spec['title']+' · software preview');fig.tight_layout();plt.show()
    return dict(name=spec['id'],sha256=spec['sha256'],dc_gain=spec['dc_gain'],l1_gain=spec['l1_gain'])

def plot_catalog(rate=16000000):
    """Compare the whole library offline, with identical frequency/dB axes."""
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(4,4,figsize=(15,10),sharex=True,sharey=True)
    f=np.fft.fftshift(np.fft.fftfreq(2048,1/rate))/1e6
    for ax,spec in zip(axes.flat,CATALOG.values()):
        h=np.array(spec['coefficients'])/32768
        db=20*np.log10(np.maximum(abs(np.fft.fftshift(np.fft.fft(h,2048))),1e-6))
        ax.plot(f,db,color='#138d98');ax.set(title=spec['id'],ylim=(-90,5));ax.grid(alpha=.2)
    for ax in list(axes.flat)[len(CATALOG):]:ax.axis('off')
    fig.supxlabel('Baseband frequency (MHz)');fig.supylabel('Quantized response magnitude (dB)')
    fig.suptitle('15 reloadable FIR examples · host coefficient previews');fig.tight_layout();plt.show()
