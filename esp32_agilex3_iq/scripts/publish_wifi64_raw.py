#!/usr/bin/env python3
"""Validate a closed raw-IQ/Nios OTA proof; publish only with --publish.

File integrity and device-telemetry checks only. Never opens hardware, starts
RF, or computes synchronization, FFT, demapping, FEC or BER.
"""
from __future__ import annotations
import argparse,hashlib,json,math,os,re,sys,tempfile,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RUN_DIR=ROOT/'cyberether/run'
LATEST=RUN_DIR/'wifi64-raw-latest.json'
KIND='bounded native Wi-Fi -> raw RFS2 -> Nios receiver'
SOURCE='ota-native-wifi64-raw-iq'
sys.path.insert(0,str(ROOT/'cyberether'))
from wifi64_records import Wifi64MonitorJoiner,expected_packet_map


def checked_path(path):
    p=Path(path);p=(p if p.is_absolute() else ROOT/p).resolve(strict=True)
    p.relative_to(RUN_DIR.resolve())
    if not p.is_file():raise ValueError('Proof/archive must be a file inside cyberether/run')
    return p


def require(condition,message):
    if not condition:raise ValueError(message)


def kv(line):
    return dict(piece.split('=',1) for piece in line.split(',') if '=' in piece)


def monitor_audit(attempt):
    """Audit recorded B telemetry only; never construct a native OTA proof."""
    cfg=kv(attempt['configuration']);run=attempt['run'];count=int(cfg['count']);seed=int(cfg['seed'])
    joiner=Wifi64MonitorJoiner(expected=expected_packet_map(run,count,seed));lines=[]
    for row in attempt.get('observed_radio_lines',[]):
        if row.get('source')==2 and row.get('line','').startswith('WIFI64_MON,'):
            lines.append(row['line']);joiner.feed(row['line'])
    audit=joiner.audit();audit['joined']=list(audit['joined'].values())
    audit['duplicates']=[{'run':key[0],'packet':key[1],'types':value} for key,value in audit['duplicates'].items()]
    good=[row for row in audit['joined'] if row.get('qualified') and row.get('channel')==attempt['channel'] and row.get('length')==92]
    return {'source':'recorded PMOD B native PHY telemetry inside raw proof',
            'native_proof_created':False,'expected_count':count,'qualified_packets':len(good),
            'all_requested_packets_observed':len(good)==count,'lines':lines,'audit':audit}


def cleanup_valid(row):
    return all(row.get(k) is True for k in ('tx_idle_verified','monitor_stop_verified','mirror_cancel_verified'))


def validate_attempt(row):
    require(all(row.get(k) is True for k in ('completed','ota64_confirmed','tx_start_requested','tx_success','known_a_identity','device_decode_accepted','raw_known_a_decode_confirmed','raw_transferred_for_transport_only')),'Attempt lacks qualified device/raw/TX evidence')
    require(row.get('host_dsp') is False and row.get('ber_measured') is False,'Host-DSP/BER scope invalid')
    require(row.get('tx_job_cancelled') is False and kv(row['tx_terminal']).get('job')==kv(row['tx_start']).get('job') and row['tx_terminal'].startswith('WIFI64_TX,DONE,'),'TX job did not finish normally')
    require(cleanup_valid(row['cleanup']),'Attempt cleanup not verified')
    cfg=kv(row['configuration']);channel=row['channel'];freq=(2412+5*(channel-1))*1000000
    require(type(channel) is int and 1<=channel<=11 and cfg.get('ch')==str(channel) and row['requested_frequency']==freq,'Channel/frequency mismatch')
    count=int(cfg['count']);seed=int(cfg['seed']);run=row['run']
    require(1<=count<=16 and 0<=run<=0xffffffff and 0<=seed<=0xffffffff and cfg.get('run')==str(run),'Invalid bounded TX identity')
    require(all(int(row['submitted'].get(k,-1))==v for k,v in {'accepted':count,'rejected':0}.items()) and all(int(row['counters'].get(k,-1))==v for k,v in {'done':count,'failed':0,'rate54':count,'other':0}.items()),'TX counter mismatch')
    raw=row['raw_transport'];decoder=row['decoder'];device=decoder['device_result'];initial=decoder['initial_status'];final=decoder['final_status']
    require(raw['kind']==1 and raw['source']==0 and raw['rate']==40000000 and raw['frequency']==freq and raw['samples'] in (8192,16380) and raw['length']==2*raw['samples'] and raw['error']==0,'Invalid raw capture profile')
    require(decoder.get('source')=='fpga-capture-ram' and decoder.get('completed') is True and decoder.get('decode_requested') is True and decoder.get('device_decode_accepted') is True and decoder.get('capture_ram_changed_after_copy') is False,'Invalid Nios decode provenance')
    require(decoder.get('ber_measured') is False and decoder.get('raw_iq_transferred_to_host') is False,'Decoder scope mismatch')
    for snapshot in (device,initial,final):
        require(all(snapshot.get(k)==raw[k] for k in ('job','source','rate','frequency','raw_crc')),'Raw/decoder capture identity mismatch')
        require(snapshot.get('conjugate_q')==row.get('conjugate_q'),'Conjugation mode mismatch')
    require(all(device.get(k)==v for k,v in {'valid':1,'status':0,'stage':5,'accepted':1,'rate_code':12,'mbps':54,'length':92,'points':192,'symbols':4,'packet_status':0,'signal_status':0,'acquisition_status':0}.items()),'Device header/FCS decode not accepted')
    require(device['received_crc']==device['fcs_crc'],'Device FCS counters disagree')
    points=decoder['constellation'];require(len(points)==192 and all(p.get('index')==i and p.get('scale')==8192 and type(p.get('i')) is int and type(p.get('q')) is int for i,p in enumerate(points)),'Incomplete actual constellation')
    packet=bytes.fromhex(decoder['decoded_psdu_hex']);bytes_rows=decoder['decoded_bytes']
    require(len(packet)==92 and int.from_bytes(packet[-4:],'little')==device['received_crc'],'Decoded FCS bytes/device counter mismatch')
    require(len(packet)==92 and len(bytes_rows)==92 and all(b.get('index')==i and b.get('value')==packet[i] and b.get('packet_status')==0 for i,b in enumerate(bytes_rows)),'Decoded-byte telemetry mismatch')
    require(packet[24:32]==b'W64A\x01\x36\x40\x00' and int.from_bytes(packet[32:36],'little')==run and int.from_bytes(packet[36:40],'little')<count and int.from_bytes(packet[40:44],'little')==seed and packet[10:16]==bytes.fromhex(row['transmitter']['mac'].replace(':','')),'Known transmitter/body identity mismatch')
    archive=row['saved_raw'];path=checked_path(archive['path']);payload=path.read_bytes();sha=hashlib.sha256(payload).hexdigest()
    require(len(payload)==raw['length']==archive['bytes'] and sha==archive['sha256']==raw['payload_sha256'] and zlib.crc32(payload)==raw['raw_crc'],'Raw archive integrity mismatch')
    require(archive.get('host_dsp') is False and archive.get('sample_format')=='ci8','Archive scope invalid')
    return {'run':run,'channel':channel,'job':raw['job'],'raw_archive':str(path.relative_to(ROOT.resolve())),
            'raw_sha256':sha,'device_points':192,'device_fcs':device['fcs_crc'],'monitor':monitor_audit(row)}


def validate_proof(path):
    path=checked_path(path);payload=path.read_bytes();require(len(payload)<=4*1024*1024,'Proof exceeds bounded size')
    proof=json.loads(payload)
    require(proof.get('kind')==KIND and proof.get('source')==SOURCE,'Requires raw-IQ/Nios OTA proof kind/source')
    require(all(proof.get(k) is True for k in ('completed','ota64_confirmed','tx_start_requested','transport_clean')),'Proof incomplete or unqualified')
    require(proof.get('host_dsp') is False and proof.get('ber_measured') is False,'Proof processing scope invalid')
    finish=proof.get('finished_unix');require(type(finish) in (int,float) and math.isfinite(finish) and finish>0,'Proof not closed')
    require(cleanup_valid(proof['final_cleanup']) and not any(proof['transport_error_deltas'].values()),'Cleanup/transport not clean')
    attempts=proof['attempts'];require(1<=len(attempts)<=3 and all(row.get('completed') is True and cleanup_valid(row['cleanup']) for row in attempts),'Unfinished attempt exists')
    good=[validate_attempt(row) for row in attempts if row.get('ota64_confirmed') is True];require(bool(good),'No accepted raw OTA attempt')
    provenance=proof['artifact_provenance']
    for field in ('fpga_sof_sha256','fpga_source_fingerprint','expected_capture_elf_sha256'):
        require(re.fullmatch('[0-9a-f]{64}',provenance.get(field,'')) is not None,'Missing artifact provenance hash')
    return {'validated':True,'source':SOURCE,'proof':str(path.relative_to(ROOT.resolve())),
            'proof_sha256':hashlib.sha256(payload).hexdigest(),'published':False,'host_dsp':False,
            'device_elf_hash_verified':provenance.get('device_elf_hash_verified',False),'attempts':good}


def publish(path):
    report=validate_proof(path);pointer=LATEST.absolute();pointer.parent.resolve().relative_to(RUN_DIR.resolve())
    require(not pointer.is_symlink(),'Latest pointer must not be a symlink')
    fd,temporary=tempfile.mkstemp(prefix='.wifi64-raw-latest.',suffix='.tmp',dir=pointer.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump({'path':report['proof']},stream);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        require(hashlib.sha256(checked_path(path).read_bytes()).hexdigest()==report['proof_sha256'],'Proof changed during publication')
        os.replace(temporary,pointer)
    finally:
        try:os.unlink(temporary)
        except FileNotFoundError:pass
    report.update(published=True,pointer=str(pointer.relative_to(ROOT.resolve())))
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('proof',type=Path)
    parser.add_argument('--publish',action='store_true',help='atomically update raw-only latest pointer after validation')
    args=parser.parse_args(argv)
    try:report=publish(args.proof) if args.publish else validate_proof(args.proof)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({'validated':False,'published':False,'error':str(exc)}),file=sys.stderr);return 2
    print(json.dumps(report,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
