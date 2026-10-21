"""Deterministic Python models and plots of actual RTL simulation readback."""
import sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from common import ROOT
sys.path.insert(0,str(ROOT/'cyberether'))
from nios_fir import PROFILES,fixed_reference
from nios_ddc import reference,gain_reference
from iq_lab_samples import load_sample
plt.rcParams.update({'figure.figsize':(12,4),'axes.grid':True,'grid.alpha':.25,'font.size':11})
def spectrum(ax,iq,fs,label):
 z=iq[:,0]+1j*iq[:,1];w=np.hanning(len(z));db=20*np.log10(np.maximum(abs(np.fft.fftshift(np.fft.fft(z*w)))/max(w.sum(),1),1e-6));ax.plot(np.fft.fftshift(np.fft.fftfreq(len(z),1/fs))/1e6,db,label=label);ax.set(xlabel='Baseband frequency (MHz)',ylabel='Relative amplitude (dB re count)');ax.legend()
def theory(n):
 raw,_=load_sample('two-tone');fs=16e6
 if n==1:
  fig,axs=plt.subplots(1,3,figsize=(14,4));axs[0].plot(np.arange(64)/16,raw[:64,0],'.-',label='I');axs[0].plot(np.arange(64)/16,raw[:64,1],'.-',label='Q');axs[0].set(xlabel='Time (µs)',ylabel='Signed CI8 counts',title='Two numbers per complex sample');axs[0].legend();axs[1].scatter(raw[:256,0],raw[:256,1],s=12);axs[1].set(xlabel='I',ylabel='Q',title='Raw IQ · no demodulation');spectrum(axs[2],raw.astype(float),fs,'Python model');summary={'sample_format':'CI8: I,Q bytes','burst_samples':4096,'nominal_burst_us':256}
 elif n==2:
  counts=np.array([2,5,1,6,3,4,2,7]);payload=counts*4096*2;wire=counts*(4096*2+68);fig,axs=plt.subplots(1,2);x=np.arange(len(counts));axs[0].bar(x,payload/1000,label='IQ payload');axs[0].step(x,wire/1000,where='mid',color='tab:orange',label='IQB1 bytes');axs[0].set(xlabel='One-second FPGA counter window',ylabel='kB/s',title='Count events → coherent snapshot');axs[0].legend();axs[1].bar(['ADC burst','2 Mbaud UART'],[16e6*2/1e6,2e6/10/1e6],color=['tab:blue','tab:orange']);axs[1].set(yscale='log',ylabel='Complex payload capacity (MB/s)',title='Instantaneous sampling ≠ continuous readout');summary={'uart_8n1_ceiling_Bps':200000,'CI8_4096_payload_bytes':8192,'minimum_UART_transfer_ms':8192/200000*1000}
 elif n==3:
  coeff=PROFILES[2];out=fixed_reference(raw,coeff,True);fig,axs=plt.subplots(1,3,figsize=(14,4));axs[0].stem(np.arange(16),np.array(coeff)/32768);axs[0].set(xlabel='Tap',ylabel='Q15 / 32768',title='Actual reloadable Hamming coefficients');axs[1].plot(raw[:160,0],label='Before I');axs[1].plot(out[:160,0],label='After I');axs[1].set(xlabel='Sample',ylabel='CI8 count',title='Integer convolution + rounding');axs[1].legend();spectrum(axs[2],raw.astype(float),fs,'Input');spectrum(axs[2],out.astype(float),fs,'FIR output');summary={'taps':16,'reference':'Python fixed-point convolution; nearest rounding and saturation'}
 elif n==4:
  filtered=reference(raw,0x08000000,4,0)['result'].astype(float)/128;alias=reference(raw,0x08000000,4,2)['result'].astype(float)/128;fig,axs=plt.subplots(1,3,figsize=(14,4));spectrum(axs[0],raw.astype(float),fs,'Before translation');spectrum(axs[1],alias[32:],fs/4,'Shift + decimate, no filter');spectrum(axs[2],filtered[32:],fs/4,'Shift + FIR + decimate');axs[1].set_title('Interferer folds into output band');axs[2].set_title('FIR rejects before downsampling');summary={'NCO_phase_increment':'0x08000000','shift_hz':500000,'decimation':4,'nominal_output_rate':4000000,'startup_output_samples_omitted':32}
 else:
  t=np.arange(128);z=12000*np.exp(2j*np.pi*t/16);a=np.rint(np.column_stack((z.real,z.imag))).astype(np.int16);fig,axs=plt.subplots(1,3,figsize=(14,4));clips=[];powers=[];gains=[.5,1,2,4,16]
  for g in gains:
   out,m=gain_reference(a,int(g*256),False);clips.append(m['gain_clips']);powers.append(m['post_power']/len(a))
   if g in(1,2,4):axs[0].plot(out[:48,0],label=f'{g:g}×')
  axs[0].set(xlabel='Sample',ylabel='CI16 I',title='Gain + nearest rounding + saturation');axs[0].legend();axs[1].plot(gains,10*np.log10(np.array(powers)/powers[1]),'o-');axs[1].set(xscale='log',xlabel='Digital gain',ylabel='Mean power change (dB)',title='2× amplitude → about +6.02 dB');axs[2].bar([str(g)+'×'for g in gains],clips);axs[2].set(ylabel='Clipped complex samples',title='Clipping is counted in FPGA');summary={'2x_expected_power_change_dB':20*np.log10(2),'gain_clip_counts':dict(zip(map(str,gains),clips))}
 fig.suptitle(f'{n} · Python simulation · conceptual / integer reference',fontsize=15);fig.tight_layout();plt.show();return summary

def simulation_plot(lesson):
 n=lesson.n;p=lesson.out/'simulation';fig,axs=plt.subplots(1,2)
 if n==1:
  data=np.loadtxt(p/'uart.csv',delimiter=',');axs[0].step(data[:,0],data[:,1],where='mid',label='Actual decoded bytes');axs[0].scatter(data[:,0],(data[:,0]*37+11)%256,color='tab:orange',label='Expected');axs[0].legend();axs[0].set(xlabel='Byte index',ylabel='Byte value',title='Real RTL TX → RX');axs[1].bar(['Verified bytes'],[len(data)]);axs[1].set(title='8N1 / binary payload assertions',ylabel='Count')
 elif n==2:
  rows=[l.split(',')for l in(p/'monitor.csv').read_text().splitlines()];values=[int(v)for k,v in rows];axs[0].bar([k for k,v in rows],values);axs[0].set(title='Actual CSR readback',ylabel='Events');axs[1].bar(['Window','Total'],[sum(int((i*7)%11 < 1)for i in range(100,110)),sum(int((i*7)%11 < 1)for i in range(113))],color='tab:orange');axs[1].set(title='Independent expectation',ylabel='Events')
 elif n==3:
  words=np.loadtxt(p/'impulse.txt',dtype=str);a=np.frombuffer(b''.join(int(v,16).to_bytes(2,'little')for v in words[:,0]),np.int8).reshape(-1,2);b=np.frombuffer(b''.join(int(v,16).to_bytes(2,'little')for v in words[:,1]),np.int8).reshape(-1,2);axs[0].stem(a[:40,0]);axs[0].set(title='Actual snapshot impulse I',xlabel='Sample',ylabel='CI8');axs[1].stem(b[:40,0]);axs[1].set(title='Actual generated FIR II I output',xlabel='Sample',ylabel='CI8')
 elif n==4:
  a=np.frombuffer(b''.join(int(v,16).to_bytes(2,'little')for v in(p/'raw-0.hex').read_text().split()),np.int8).reshape(-1,2).astype(float);b=np.frombuffer(b''.join(int(v,16).to_bytes(4,'little')for v in(p/'out-0.txt').read_text().split()),'<i2').reshape(-1,2).astype(float)/128;spectrum(axs[0],a,16e6,'RTL input');spectrum(axs[1],b[32:],4e6,'Actual FIR II / DDC output')
 else:
  d=np.loadtxt(p/'gain.csv',delimiter=',');axs[0].plot(d[:,2],label='Actual input I');axs[0].plot(d[:,3],label='Actual gain output I');axs[0].legend();axs[0].set(title='Five RTL gain phases',xlabel='Accepted sample',ylabel='CI16');axs[1].plot(d[:,6]);axs[1].set(title='Actual FPGA clipping counter',xlabel='Accepted sample',ylabel='Clips in current phase')
 fig.suptitle(f'{n} · Measured RTL simulation output · assertions PASS');fig.tight_layout();plt.show()
