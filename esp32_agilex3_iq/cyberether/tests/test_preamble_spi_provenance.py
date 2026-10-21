"""Passive capture acceptance must reflect fresh physical SPI data, not mode ACKs."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'cyberether'))
from check_preamble import verify_passive_spi


class PassiveSpiProvenanceTests(unittest.TestCase):
    def fixture(self):
        frame = SimpleNamespace(kind=1, source=2, samples=16380,
                                rate=16000000, frequency=2447000000)
        before = dict(valid=True, requested_synthetic=False, synthetic=False,
                      sequence=71, commit_count=100, ingress_cycles=123)
        after = dict(before, sequence=72, commit_count=101, ingress_cycles=812345)
        return frame, before, after

    def test_fresh_physical_capture_accepted_even_when_rejects_advance(self):
        frame, before, after = self.fixture()
        before['reject_count'] = 6
        after['reject_count'] = 8  # Partial mode-boundary drains are not stale captures.
        verify_passive_spi(frame, before, after)

    def test_each_physical_profile_field_is_required(self):
        for name, wrong in [('kind', 6), ('source', 3), ('samples', 16384),
                            ('rate', 8000000), ('frequency', 2442000000)]:
            with self.subTest(field=name):
                frame, before, after = self.fixture()
                setattr(frame, name, wrong)
                with self.assertRaisesRegex(ValueError, 'profile'):
                    verify_passive_spi(frame, before, after)

    def test_mode_ack_does_not_override_invalid_or_synthetic_observation(self):
        for patch in [dict(valid=False), dict(synthetic=True),
                      dict(requested_synthetic=True), dict(ingress_cycles=0)]:
            with self.subTest(observed=patch):
                frame, before, after = self.fixture()
                after.update(patch)
                with self.assertRaisesRegex(ValueError, 'fresh committed non-synthetic'):
                    verify_passive_spi(frame, before, after)

    def test_commit_must_advance_not_freeze_go_backward_or_jump_half_range(self):
        for delta in [0, -1, 0x80000000]:
            with self.subTest(delta=delta):
                frame, before, after = self.fixture()
                after['commit_count'] = (before['commit_count'] + delta) & 0xffffffff
                with self.assertRaisesRegex(ValueError, 'fresh committed'):
                    verify_passive_spi(frame, before, after)

    def test_valid_baseline_sequence_must_also_advance(self):
        for delta in [0, -1, 0x80000000]:
            with self.subTest(delta=delta):
                frame, before, after = self.fixture()
                after['sequence'] = (before['sequence'] + delta) & 0xffffffff
                with self.assertRaisesRegex(ValueError, 'sequence did not advance'):
                    verify_passive_spi(frame, before, after)

    def test_counter_wrap_is_forward_progress(self):
        frame, before, after = self.fixture()
        before.update(sequence=0xffffffff, commit_count=0xffffffff)
        after.update(sequence=0, commit_count=0)
        verify_passive_spi(frame, before, after)

    def test_first_valid_capture_can_have_sequence_zero_but_still_needs_commit(self):
        frame, before, after = self.fixture()
        before.update(valid=False, sequence=0)
        after['sequence'] = 0
        verify_passive_spi(frame, before, after)
        after['commit_count'] = before['commit_count']
        with self.assertRaisesRegex(ValueError, 'fresh committed'):
            verify_passive_spi(frame, before, after)


if __name__ == '__main__':
    unittest.main()
