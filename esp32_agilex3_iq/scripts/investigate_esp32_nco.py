#!/usr/bin/env python3
"""Offline original-ESP32 NCO ABI evidence and exact register-word model.

Never opens devices, invokes firmware or writes registers. Output is an analysis
artifact, not a TX command. The model intentionally exposes unsafe raw negative
step semantics; use wrapped N-bit frequency codes or the vendor MHz wrapper.
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import tempfile
from pathlib import Path

from investigate_esp32_tx import ROOT, find_tool, run, revision, sha, section


def signed(value, bits):
    value = int(value) & ((1 << bits)-1)
    return value-(1 << bits) if value & (1 << (bits-1)) else value


def wrapper_step(freq_mhz, hires=False):
    """Exact bounded integer-MHz wrapper conversion; truncation toward zero."""
    if type(freq_mhz) is not int or not -80 <= freq_mhz <= 80:
        raise ValueError('analysis model accepts integer MHz from -80 to 80')
    numerator = freq_mhz * (128 if hires else 32)
    quotient = (abs(numerator)//5) * (-1 if numerator < 0 else 1)
    return quotient & (4095 if hires else 1023)


def raw_step_words(enable1, step1, atten1, enable2, step2, atten2,
                   initial1=0x20000000, initial2=0, initial_extension=0):
    """Translate original ROM instructions, including their raw signed-step caveat.

    Six ABI values are bool/u8, sint16, u8, bool/u8, sint16, u8. This
    instruction model deliberately does not sanitize a negative raw step.
    Never apply returned words to hardware merely because the model runs.
    """
    steps = [signed(step1, 16), signed(step2, 16)]
    enabled = [int(enable1) & 255, int(enable2) & 255]
    attenuation = [(-int(atten1)) & 255, (-int(atten2)) & 255]
    hires = bool(initial1 & (1 << 29))
    extension = int(initial_extension) & 0xffffffff
    if hires:
        extension = (extension & ~15) | (steps[0] & 3) | ((steps[1] & 3) << 2)
        steps = [value >> 2 for value in steps]
    words = []
    for initial, enable, step, atten in zip((initial1, initial2), enabled, steps, attenuation):
        words.append(((initial & 0xf0000000) | (step & 0x0fffffff) |
                      (enable << 18) | (atten << 10)) & 0xffffffff)
    return dict(control_words=[f'0x{word:08x}' for word in words], extension_word=f'0x{extension:08x}',
                hires=hires, source='Offline instruction model, no register writes')


def dwarf_nodes(text):
    """Parse readelf's selected structural DWARF attributes, retaining hierarchy."""
    nodes, current = [], None
    for line in text.splitlines():
        match = re.match(r'\s*<(\d+)><([0-9a-f]+)>:.*\((DW_TAG_\w+)\)', line)
        if match:
            depth, address, tag = match.groups()
            current = dict(depth=int(depth), address=address, tag=tag, attrs={})
            nodes.append(current)
        elif current:
            match = re.match(r'.*DW_AT_(\w+)\s*:\s*(.*)', line)
            if match:
                key, value = match.groups()
                if key == 'name':
                    value = value.rsplit(': ', 1)[-1]
                current['attrs'][key] = value
    return nodes


def children(nodes, node):
    index = nodes.index(node)
    out = []
    for candidate in nodes[index+1:]:
        if candidate['depth'] <= node['depth']:
            break
        if candidate['depth'] == node['depth']+1:
            out.append(candidate)
    return out


def type_node(nodes, node):
    value = node['attrs'].get('type', '')
    match = re.search(r'<0x([0-9a-f]+)>', value)
    return next((n for n in nodes if match and n['address'] == match[1]), None)


def extract_abi(nodes):
    wrapper = next(n for n in nodes if n['tag'] == 'DW_TAG_subprogram' and n['attrs'].get('name') == 'ram_start_tx_tone')
    params = []
    for node in children(nodes, wrapper):
        if node['tag'] == 'DW_TAG_formal_parameter':
            typ = type_node(nodes, node)
            params.append(dict(name=node['attrs'].get('name'), type=typ['attrs'].get('name') if typ else None))
    member = next(n for n in nodes if n['tag'] == 'DW_TAG_member' and n['attrs'].get('name') == 'start_tx_tone_step_')
    pointer = type_node(nodes, member)
    routine = type_node(nodes, pointer)
    step_types = []
    for node in children(nodes, routine):
        if node['tag'] == 'DW_TAG_formal_parameter':
            typ = type_node(nodes, node)
            step_types.append(typ['attrs'].get('name') if typ else None)
    return dict(wrapper=wrapper['attrs'].get('name'), wrapper_parameters=params,
                raw_step_table_offset=int(member['attrs']['data_member_location']), raw_step_parameter_types=step_types)


def self_test():
    for hires in (False, True):
        mask = 4095 if hires else 1023
        for frequency in range(-80, 81):
            value = frequency * (128 if hires else 32)
            mul_high = (value*0x66666667) >> 32
            instruction_divide = (mul_high >> 1) - (value >> 31)
            assert wrapper_step(frequency, hires) == instruction_divide & mask
        base = 0x20000000 if hires else 0
        code = wrapper_step(-1, hires)
        result = raw_step_words(1, code, 96, 0, 0, 0, base)
        word = int(result['control_words'][0], 16)
        assert (word >> 18) & 255 == 1
        assert (word >> 10) & 255 == 160
        assert word & 1023 == (code >> 2 if hires else code)
    bad = int(raw_step_words(1, -1, 96, 0, 0, 0)['control_words'][0], 16)
    assert (bad >> 18) & 255 == 255 and (bad >> 10) & 255 == 255
    print('Offline NCO wrapper/register-model self-tests PASS; no hardware accessed')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--idf-root', type=Path)
    p.add_argument('--tools-dir', type=Path)
    p.add_argument('--upstream-root', type=Path, default=ROOT/'vendor/esp32-sdr-trx')
    p.add_argument('--output', type=Path, default=ROOT/'cyberether/run/nco-investigation')
    p.add_argument('--self-test', action='store_true')
    args = p.parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    if not args.idf_root:
        p.error('--idf-root required for SDK evidence')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    nm = find_tool('xtensa-esp32-elf-nm', args.tools_dir)
    ar, objdump, readelf = [nm.with_name(nm.name[:-2]+suffix) for suffix in ('ar', 'objdump', 'readelf')]
    libroot = args.idf_root.resolve()/'components/esp_phy/lib/esp32'
    phy, rftest = libroot/'libphy.a', libroot/'librftest.a'
    with tempfile.TemporaryDirectory(prefix='nco-abi-offline-') as temporary:
        obj = Path(temporary)/'phy_chip_v7.o'
        obj.write_bytes(run([ar, 'p', phy, 'phy_chip_v7.o'], binary=True))
        debug = run([readelf, '--debug-dump=info', obj])
        (out/'phy_chip_v7.debug.txt').write_text(debug)
        abi = extract_abi(dwarf_nodes(debug))
    functions = {}
    targets = ('ram_start_tx_tone', 'get_path_loss_offset', 'set_freq_test', 'rfcal_txiq',
               'test_tx_vdd33', 'get_rx_tone_pwr', 'run_rftest_case')
    for archive in (phy, rftest):
        dump = run([objdump, '-dr', archive])
        (out/(archive.name+'.disasm.txt')).write_text(dump)
        for name in targets:
            text = section(dump, name)
            if text:
                (out/(name+'.disasm.txt')).write_text(text)
                functions[name] = dict(archive=archive.name, evidence_file=name+'.disasm.txt')
    upstream = args.upstream_root.resolve()
    files = ('firmware/src/radio.c', 'src/espdr/txmodes.py', 'docs/research/TX-RESEARCH.md')
    source = {name: sha(upstream/name) for name in files if (upstream/name).is_file()}
    report = dict(source='Offline original ESP32 NCO analysis; no hardware access',
                  sdk_revision=revision(args.idf_root), sdk_archives={a.name: sha(a) for a in (phy, rftest)},
                  abi=abi, inspected_functions=functions,
                  upstream=dict(repository='https://github.com/jochenhammes/esp32-sdr-trx',
                                revision=revision(upstream), source_sha256=source, chip='ESP32-S3; not original-chip measurements'),
                  examples={str(hires): {str(f): dict(wrapped_step=wrapper_step(f, hires),
                               words=raw_step_words(1, wrapper_step(f, hires), 96, 0, 0, 0, 0x20000000 if hires else 0))
                               for f in (-1, 0, 1, 5)} for hires in (False, True)},
                  conclusion='Two NCO tone generators with attenuation fields; neither frequency parameters nor enable fields are Cartesian I/Q samples. Original-chip attenuation response and NCO offset still require bounded independent RF measurement.')
    (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    self_test()
    print(json.dumps(abi, indent=2))
    print('Evidence:', out/'report.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
