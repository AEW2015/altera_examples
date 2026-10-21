#!/usr/bin/env python3
"""Offline original-ESP32 / ESP32-S3 RF SDK comparison; never opens hardware.

Inspect locally installed vendor libraries and the pinned iq-tx checkout. Full
symbol/disassembly evidence stays in ignored cyberether/run/ by default. Missing
symbols are evidence about these archives, not proof of absent silicon features.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
INTEREST = re.compile(r'adctrig|dactrig|dump|dac|txclk|tx.*tone|force.*(iq|tx)|loopback|tx_cont|tx_dig_gain', re.I)
FUNCTIONS = ('adctrig', 'dactrig', 'get_txdumpaddr', 'clear_txdumpmem',
             'force_iq_set', 'force_txon_mode', 'force_txon_en',
             'ram_set_txclk_en', 'ram_start_tx_tone', 'set_tx_dig_gain', 'crypto_encap', 'phy_get_romfunc_addr')
ROM_INTEREST = re.compile(r'adctrig|dactrig|dac_out|dac_rate|txclk|start_tx_tone|txiq_set_reg|loopback|pbus_xpd_tx')


def run(cmd, binary=False):
    r = subprocess.run([str(x) for x in cmd], capture_output=True, check=True, text=not binary)
    return r.stdout


def revision(path):
    try:
        return run(['git', '-C', path, 'rev-parse', 'HEAD']).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def find_tool(name, tools_dir=None):
    direct = shutil.which(name)
    if tools_dir:
        matches = sorted(Path(tools_dir).expanduser().rglob(name))
        if matches:
            return matches[-1]
    if direct:
        return Path(direct)
    roots = [Path(os.environ.get('IDF_TOOLS_PATH', Path.home()/'.espressif')),
             Path.home()/'.espressif-sdr']
    for root in roots:
        matches = sorted((root/'tools').rglob(name)) if (root/'tools').is_dir() else []
        if matches:
            return matches[-1]
    raise FileNotFoundError(f'{name} not found; pass --tools-dir or add its bin directory to PATH')


def symbols(text):
    """Parse GNU nm -A archive member lines, retaining definitions and refs."""
    rows = []
    pattern = re.compile(r'^(.+?\.a):([^:]+):\s*(?:([0-9a-fA-F]+)\s+)?([A-Za-z?])\s+(\S+)\s*$', re.M)
    for match in pattern.finditer(text):
        archive, member, address, kind, name = match.groups()
        rows.append(dict(archive=Path(archive).name, member=member, address=address,
                         kind=kind, name=name, defined=kind.upper() != 'U'))
    return rows


def section(text, name, symbol_size=None):
    marker = f'Disassembly of section .text.{name}:\n'
    if marker in text:
        return marker + text.split(marker, 1)[1].split('Disassembly of section ', 1)[0]
    # Older SDK functions share .iram1/.phyiram sections. Keep only the
    # selected symbol's instruction range; resolved l32r operands remain.
    match = re.search(r'^([0-9a-f]+ <'+re.escape(name)+r'>:)\n', text, re.M)
    if not match:
        return ''
    tail = text[match.start():].split('Disassembly of section ', 1)[0]
    if symbol_size is not None:
        start_address = int(match.group(1).split()[0], 16)
        lines = tail.splitlines(keepends=True)
        for index, line in enumerate(lines[1:], 1):
            address = re.match(r'^\s*([0-9a-f]+):', line)
            if address and int(address[1], 16) >= start_address+symbol_size:
                return ''.join(lines[:index])
    following = re.search(r'^([0-9a-f]+ <[^>]+>:)\n', tail[match.end()-match.start():], re.M)
    if following:
        return tail[:match.end()-match.start()+following.start()]
    return tail.split('Disassembly of section ', 1)[0]


def section_facts(text):
    literals = re.findall(r'^\s*[0-9a-f]+:\s+([0-9a-f]{8})\s*$', text, re.M)
    refs = re.findall(r'R_XTENSA_ASM_EXPAND\s+(\S+)', text)
    resolved = re.findall(r'l32r[^\n]*\(([0-9a-f]{8})\s', text)
    return dict(resolved_l32r_values=sorted(set('0x'+word for word in resolved)), literal_words=sorted(set('0x'+word for word in literals)),
                expanded_symbol_references=sorted(set(refs)))


def investigate(idf_root, tools_dir, upstream_root, output):
    idf_root = Path(idf_root).expanduser().resolve()
    upstream_root = Path(upstream_root).expanduser().resolve()
    output = Path(output).expanduser().resolve()
    libroot = idf_root/'components/esp_phy/lib'
    if not libroot.is_dir():
        raise FileNotFoundError(f'not an ESP-IDF source tree with PHY archives: {idf_root}')
    backend = upstream_root/'firmware/src/targets/esp32s3.c'
    if not backend.is_file():
        raise FileNotFoundError(f'pinned iq-tx S3 backend is missing: {backend}')
    output.mkdir(parents=True, exist_ok=True)
    report = dict(kind='offline SDK analysis; no device access',
                  sdk_revision=revision(idf_root), upstream_revision=revision(upstream_root),
                  backend_sha256=sha(backend), chips={})
    for chip in ('esp32', 'esp32s3'):
        dest = output/chip
        dest.mkdir(exist_ok=True)
        nm = find_tool(f'xtensa-{chip}-elf-nm', tools_dir)
        ar = nm.with_name(nm.name[:-2]+'ar')
        objdump = nm.with_name(nm.name[:-2]+'objdump')
        archives = sorted((libroot/chip).glob('*.a'))
        if not archives:
            raise FileNotFoundError(f'no {chip} archives found')
        rows = []
        archive_info = {}
        window_matches = {}
        for archive in archives:
            text = run([nm, '-A', archive])
            (dest/(archive.name+'.nm.txt')).write_text(text)
            parsed = symbols(text)
            if not parsed:
                raise ValueError(f'cannot parse nm output for {archive}')
            rows.extend(parsed)
            archive_info[archive.name] = dict(sha256=sha(archive), symbol_rows=len(parsed))
            for member in run([ar, 't', archive]).splitlines():
                blob = run([ar, 'p', archive, member], binary=True)
                for address in range(0x60033d50, 0x60033dd0, 4):
                    if struct.pack('<I', address) in blob:
                        window_matches.setdefault(hex(address), []).append(archive.name+':'+member)
        all_text = '\n'.join((dest/(a.name+'.nm.txt')).read_text() for a in archives)
        (dest/'interesting-symbols.txt').write_text('\n'.join(line for line in all_text.splitlines() if INTEREST.search(line))+'\n')
        definitions = [row for row in rows if row['defined']]
        selected = [row for row in definitions if row['name'] in FUNCTIONS]
        extracted = {}
        facts = {}
        with tempfile.TemporaryDirectory(prefix='esp32-tx-offline-') as temporary:
            for row in selected:
                key = (row['archive'], row['member'])
                if key not in extracted:
                    blob = run([ar, 'p', libroot/chip/row['archive'], row['member']], binary=True)
                    obj = Path(temporary)/row['member']
                    obj.write_bytes(blob)
                    dump = run([objdump, '-dr', '-s', obj])
                    (dest/(row['archive']+'--'+row['member']+'.txt')).write_text(dump)
                    sizes = run([nm, '-S', obj])
                    size_map = {name: int(size, 16) for _, size, _, name in re.findall(r'^([0-9a-f]+)\s+([0-9a-f]+)\s+([A-Za-z])\s+(\S+)$', sizes, re.M)}
                    extracted[key] = (dump, size_map)
                dump, size_map = extracted[key]
                text = section(dump, row['name'], size_map.get(row['name']))
                if not text:
                    raise ValueError(f'no function section for {chip} {row["name"]}')
                (dest/(row['name']+'.disasm.txt')).write_text(text)
                facts[row['name']] = dict(archive=row['archive'], member=row['member'], **section_facts(text))
        rom = []
        for ld in sorted((idf_root/'components/esp_rom'/chip/'ld').glob('*.ld')):
            for line in ld.read_text().splitlines():
                if ROM_INTEREST.search(line):
                    rom.append(dict(file=ld.name, text=line.strip()))
        (dest/'rom-symbols.json').write_text(json.dumps(rom, indent=2)+'\n')
        report['chips'][chip] = dict(archives=archive_info,
                                    defined_interesting=[r for r in definitions if INTEREST.search(r['name'])],
                                    has_dactrig_definition=any(r['name'] == 'dactrig' for r in definitions),
                                    function_facts=facts, rom_symbols=rom,
                                    mac_window_literal_matches=window_matches,
                                    literal_scan_note='Raw LE32 byte matches; inspect disassembly before treating as a register reference.',
                                    nm_version=run([nm, '--version']).splitlines()[0])
    text = backend.read_text()
    report['working_s3_backend'] = dict(
        source='firmware/src/targets/esp32s3.c',
        register_definitions=re.findall(r'^#define (?:SRAM_BASE|SRAM_END|OWNER|ADC|PLAY) .+$', text, re.M),
        calls=sorted(set(re.findall(r'\b(?:rom_|esp_phy_|force_txon_mode|stop_tx_tone|set_chanfreq)\w*\s*\(', text))))
    report['conclusion'] = (
        'S3 playback control is evidenced by dactrig and the source backend. '
        'An original-ESP32 equivalent remains unlocated; tone/clock functions and '
        'shared diagnostic SRAM provide investigation leads, not IQ TX proof.')
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


def analyze_wifi_archives(idf_root, tools_dir, output):
    """Optional original-chip packet-library scan, separate from PHY archives.

    Names and literal matches are discovery aids. Selected disassembly lets a
    reviewer distinguish packet headers/statistics from a waveform DAC source.
    No result from this routine is a hardware capability assertion.
    """
    libroot = Path(idf_root).expanduser().resolve()/'components/esp_wifi/lib/esp32'
    if not libroot.is_dir():
        raise FileNotFoundError('ESP32 Wi-Fi archive directory missing: '+str(libroot))
    nm = find_tool('xtensa-esp32-elf-nm', tools_dir)
    ar = nm.with_name(nm.name[:-2]+'ar')
    objdump = nm.with_name(nm.name[:-2]+'objdump')
    folder = Path(output)/'wifi-esp32'
    folder.mkdir(parents=True, exist_ok=True)
    interest = re.compile(r'adctrig|dactrig|waveform|playback|iq_|_iq|dump|dac|txclk|tone|source|src|tx.*(?:test|mem|bank|buf)', re.I)
    selected_names = {'ic_tx_pkt', 'hal_mac_tx_set_ppdu', 'mac_tx_set_plcp0',
                      'mac_tx_set_plcp1', 'mac_tx_set_plcp2', 'mac_tx_set_htsig',
                      'lmacTxFrame', 'wdev_bank_load', 'wdev_bank_store', 'wdev_mac_reg_load', 'wdev_mac_reg_store',
                      'hal_mac_set_csi', 'hal_sniffer_enable', 'hal_sniffer_rx_set_promis',
                      'dbg_lmac_hw_statis_dump', 'dbg_lmac_diag_statis_dump'}
    registers = tuple(range(0x60033d50, 0x60033dd0, 4))+tuple(range(0x3ff73d50, 0x3ff73dd0, 4))
    registers += (0x3ffe8000, 0x3fff8000, 0x6000607c, 0x3ff4607c,
                  0x600060b8, 0x600060bc, 0x3ff460b8, 0x3ff460bc)
    archives, all_rows, functions, matches = {}, [], {}, {}
    with tempfile.TemporaryDirectory(prefix='wifi-tx-offline-') as temporary:
        for archive in sorted(libroot.glob('*.a')):
            listing = run([nm, '-A', archive])
            (folder/(archive.name+'.nm.txt')).write_text(listing)
            rows = symbols(listing)
            all_rows.extend(rows)
            members = run([ar, 't', archive]).splitlines()
            archives[archive.name] = dict(sha256=sha(archive), symbol_rows=len(rows), members=len(members))
            selected = [row for row in rows if row['defined'] and row['name'] in selected_names]
            for member in members:
                blob = run([ar, 'p', archive, member], binary=True)
                key = archive.name+':'+member
                for address in registers:
                    if struct.pack('<I', address) in blob:
                        matches.setdefault(hex(address), []).append(key)
                targets = [row for row in selected if row['member'] == member]
                if not targets:
                    continue
                path = Path(temporary)/member
                path.write_bytes(blob)
                dump = run([objdump, '-dr', '-s', path])
                (folder/(archive.name+'--'+member+'.txt')).write_text(dump)
                sizes = run([nm, '-S', path])
                size_map = {name: int(size, 16) for _, size, _, name in re.findall(r'^([0-9a-f]+)\s+([0-9a-f]+)\s+([A-Za-z])\s+(\S+)$', sizes, re.M)}
                for row in targets:
                    text = section(dump, row['name'], size_map.get(row['name']))
                    if not text:
                        raise ValueError('Missing selected Wi-Fi function section: '+row['name'])
                    (folder/(row['name']+'.disasm.txt')).write_text(text)
                    functions[row['name']] = dict(archive=archive.name, member=member, **section_facts(text))
    interesting = [row for row in all_rows if interest.search(row['name'])]
    (folder/'interesting-symbols.json').write_text(json.dumps(interesting, indent=2)+'\n')
    return dict(archives=archives, scanned_members=sum(a['members'] for a in archives.values()),
                interesting_symbols=interesting, function_facts=functions,
                literal_matches=matches,
                literal_scan_note='Raw LE32 byte matches in both inspected MAC address windows plus known SRAM/NCO addresses; indirect references can be absent.',
                original_iq_helpers={name: any(row['defined'] and row['name'] == name for row in all_rows)
                                     for name in ('adctrig', 'dactrig', 'force_iq_set', 'dac_out')},
                conclusion='Inspected Wi-Fi packet-library helpers configure packet/PLCP/CSI/statistics paths; no arbitrary-IQ playback helper was identified.')


def elf32_sections(path):
    """Read supplied official ELF32-LE sections using only Python stdlib."""
    blob = Path(path).read_bytes()
    if blob[:6] != b'\x7fELF\x01\x01':
        raise ValueError('expected ELF32 little-endian ROM file')
    header = struct.unpack_from('<16sHHIIIIIHHHHHH', blob)
    offset, stride, count, strings_index = header[6], header[11], header[12], header[13]
    if stride < 40 or count < 1 or strings_index >= count:
        raise ValueError('invalid ELF section table')
    raw = [struct.unpack_from('<10I', blob, offset+k*stride) for k in range(count)]
    names_section = raw[strings_index]
    names = blob[names_section[4]:names_section[4]+names_section[5]]
    result = {}
    for entry in raw:
        name = names[entry[0]:].split(b'\0', 1)[0].decode(errors='replace')
        result[name] = dict(address=entry[3], size=entry[5], type=entry[1], flags=entry[2],
                            data=b'' if entry[1] == 8 else blob[entry[4]:entry[4]+entry[5]])
    return result


def analyze_rom(path, tools_dir, output):
    """Resolve the original-chip PHY table and retain actual ROM instructions."""
    path = Path(path).expanduser().resolve()
    sections = elf32_sections(path)
    objdump = find_tool('xtensa-esp32-elf-objdump', tools_dir)
    nm = objdump.with_name(objdump.name[:-7]+'nm')
    listing = run([nm, '-S', path])
    folder = Path(output)/'rom'/path.stem
    folder.mkdir(parents=True, exist_ok=True)
    (folder/'symbols.txt').write_text(listing)
    (folder/'sections.txt').write_text(run([objdump, '-h', path]))
    facts = dict(file=path.name, sha256=sha(path), code_sections=[], function_facts={})
    for name, sec in sections.items():
        if sec['flags'] & 4 and sec['type'] != 8 and sec['data']:
            facts['code_sections'].append(dict(name=name, address=hex(sec['address']), bytes=len(sec['data'])))
    for name in ('phy_get_romfuncs', 'rom_start_tx_tone_step', 'rom_start_tx_tone', 'rom_txiq_set_reg'):
        dump = run([objdump, '-d', '--disassemble='+name, path])
        (folder/(name+'.disasm.txt')).write_text(dump)
        facts['function_facts'][name] = dict(has_disassembly=bool(re.search(r'<'+re.escape(name)+r'>:', dump)), **section_facts(dump))
    data = sections.get('.data_phyrom')
    if data and len(data['data']) >= 4:
        table = struct.unpack_from('<I', data['data'])[0]
        entries = {}
        for offset in (60, 64, 68, 72):
            at = table-data['address']+offset
            if 0 <= at <= len(data['data'])-4:
                entries[str(offset)] = hex(struct.unpack_from('<I', data['data'], at)[0])
        facts['phy_table'] = dict(pointer_location=hex(data['address']), initial_table_pointer=hex(table), entries_by_byte_offset=entries,
                                 provenance='Initial ROM ELF data; live SDK may patch table entries')
    interesting = [line for line in listing.splitlines() if INTEREST.search(line)]
    (folder/'interesting-symbols.txt').write_text('\n'.join(interesting)+'\n')
    return facts


def self_test():
    parsed = symbols('lib.a:mac_common.o:00000088 T adctrig\nlib.a:foo.o:         U dactrig\n')
    assert len(parsed) == 2 and parsed[0]['defined'] and not parsed[1]['defined']
    text = 'Disassembly of section .text.adctrig:\n0: 60033d90\nDisassembly of section .text.next:\n'
    assert section_facts(section(text, 'adctrig'))['literal_words'] == ['0x60033d90']
    assert section(text, 'dactrig') == ''
    shared = 'Disassembly of section .iram1.3:\n00000000 <bank>:\n 0: 004136 entry a1,32\n 3: f01d retw.n\nDisassembly of section .iram1.4:\n00000000 <next>:\n 0: 3ffe8000\n'
    assert '3ffe8000' not in section(shared, 'bank', 5)
    print('Offline parser self-test passed; no SDK or hardware access')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--idf-root', type=Path, default=os.environ.get('IDF_PATH'), help='SDK containing components/esp_phy/lib')
    p.add_argument('--tools-dir', type=Path, help='directory containing or above the Xtensa binutils')
    p.add_argument('--upstream-root', type=Path, default=ROOT/'vendor/esp32-iq-tx')
    p.add_argument('--output', type=Path, default=ROOT/'cyberether/run/esp32-tx-investigation')
    p.add_argument('--rom-elf', action='append', type=Path, default=[], help='optional official original-ESP32 ROM ELF; repeat for chip revisions')
    p.add_argument('--wifi-archives', action='store_true', help='also inspect original-chip esp_wifi packet/HAL archives for IQ-source leads')
    p.add_argument('--self-test', action='store_true')
    args = p.parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    if not args.idf_root:
        p.error('pass --idf-root or set IDF_PATH; analysis never downloads/executes firmware')
    report = investigate(args.idf_root, args.tools_dir, args.upstream_root, args.output)
    if args.wifi_archives:
        report['wifi_esp32'] = analyze_wifi_archives(args.idf_root, args.tools_dir, args.output)
        (args.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    if args.rom_elf:
        report['rom_elfs'] = [analyze_rom(path, args.tools_dir, args.output) for path in args.rom_elf]
        (args.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print('Offline evidence:', args.output.resolve()/'report.json')
    for chip, info in report['chips'].items():
        print(f'{chip}: {len(info["archives"])} archives, dactrig definition={info["has_dactrig_definition"]}, inspected={", ".join(info["function_facts"])}')
    if 'wifi_esp32' in report:
        wifi = report['wifi_esp32']
        print(f'Wi-Fi ESP32: {len(wifi["archives"])} archives, {wifi["scanned_members"]} members; '+wifi['conclusion'])
    print(report['conclusion'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
