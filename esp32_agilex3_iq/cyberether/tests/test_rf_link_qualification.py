"""Offline qualification dispatch must include nested saved batches, no hardware."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import rf_link_lab


class QualificationDispatchTests(unittest.TestCase):
    def test_recursive_explicit_run_root_passed_to_offline_qualifier(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);run=root/'cyberether/run'
            manager=rf_link_lab.CaptureManager(run/'state.json',root=root)
            with patch.object(rf_link_lab.threading,'Thread') as thread:
                job=manager.qualify({})
                command,output,owner=thread.call_args.kwargs['args']
                try:
                    self.assertTrue(job['busy'])
                    self.assertIn('--proof-dir',command)
                    self.assertEqual(command[command.index('--proof-dir')+1],str(run))
                    self.assertIn('check_rf_ber.py',command[1])
                    self.assertFalse(job['requested']['hardware'])
                    self.assertNotIn('--proof',command) # No one-level glob that loses nested batches.
                finally:owner.close()


if __name__=='__main__':unittest.main()
