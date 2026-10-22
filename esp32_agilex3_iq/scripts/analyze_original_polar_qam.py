#!/usr/bin/env python3
"""Offline 64-QAM polar requirements; never accesses a radio or registers.

This is geometry and an instruction-derived bitfield model, NOT a calibrated
transmitter. No computed attenuation or phase value is a firmware command.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path


def attenuation_word_model(original: int, code: int) -> int:
    """Preserve every field except the ROM's negated-u8 attenuation field.

    Derived from original-chip rom_start_tx_tone_step; hardware transfer,
    phase continuity, update latency and settling are deliberately unclaimed.
    """
    if type(original) is not int or not 0 <= original <= 0xffffffff:
        raise ValueError('original must be an unsigned 32-bit word')
    if type(code) is not int or not 0 <= code <= 255:
        raise ValueError('code must be an unsigned byte')
    return (original & ~(255 << 10)) | ((-code & 255) << 10)


def requirements() -> dict:
    levels = (-7, -5, -3, -1, 1, 3, 5, 7)
    states = []
    for q in levels:
        for i in levels:
            radius2 = i*i + q*q
            # Reduced integer directions avoid float-equality in phase counting.
            divisor = math.gcd(abs(i), abs(q))
            states.append(dict(i=i, q=q, radius_squared=radius2,
                               radius_relative_to_peak=math.sqrt(radius2/98),
                               phase_degrees=math.degrees(math.atan2(q, i)),
                               direction=[i//divisor, q//divisor]))
    return dict(kind='offline geometry and bitfield model; no device access',
                rf_qualified=False, firmware_commands_generated=False,
                normalization='mean symbol energy = 42; peak squared radius = 98',
                state_count=len(states),
                distinct_radii_squared=sorted({s['radius_squared'] for s in states}),
                distinct_phase_count=len({tuple(s['direction']) for s in states}),
                radial_dynamic_range_db=10*math.log10(98/2),
                states=states,
                required_measurements=['attenuation-code to measured RF amplitude and AM/PM',
                                       'gain-update phase continuity and settling',
                                       'all polar states in one chronological RF capture',
                                       'all 4096 directed state transitions or explicit bounded subset',
                                       'time-varying frame EVM, CRC and BER'])


def self_test():
    mask = 255 << 10
    for initial in (0, 0xffffffff, 0x20040000, 0xa5a5a5a5):
        for code in range(256):
            word = attenuation_word_model(initial, code)
            assert (word & ~mask) == (initial & ~mask)
            assert (-((word >> 10) & 255) & 255) == code
    for value in (-1, 256, True):
        try:
            attenuation_word_model(0, value)
        except ValueError:
            pass
        else:
            raise AssertionError('invalid code accepted')
    r = requirements()
    assert r['state_count'] == 64
    assert len(r['distinct_radii_squared']) == 9
    assert r['distinct_phase_count'] == 52
    assert abs(r['radial_dynamic_range_db']-16.9019608) < 1e-6
    return dict(passed=True, exhaustive_attenuation_cases=1024,
                scope='offline model only; not an RF or register test')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path)
    p.add_argument('--self-test', action='store_true')
    args = p.parse_args()
    report = requirements()
    if args.self_test:
        report['self_test'] = self_test()
    report['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    data = json.dumps(report, indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(data)
        print(args.output)
    else:
        print(data, end='')


if __name__ == '__main__':
    main()
