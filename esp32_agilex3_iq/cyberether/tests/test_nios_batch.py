"""Pipelined JTAG controls retain per-request acknowledgement integrity."""
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nios_fir import NiosFir


class NiosBatchTests(unittest.TestCase):
    def client(self,lines):
        c=NiosFir.__new__(NiosFir);c.request=40;c.process=SimpleNamespace(stdin=io.StringIO());it=iter(lines)
        def line(deadline):
            try:return next(it)
            except StopIteration:raise TimeoutError('No further replies')
        c.line=line;return c

    def test_reordered_replies_match_ids_and_unrelated_logger_is_ignored(self):
        c=self.client(['IQMON,seq=4','FIR,39,OK,OLD,written=0','FIR,42,OK,PLOAD,written=32','FIR,41,OK,PLOAD,written=16'])
        result=c.commands([('PLOAD',0,'0102'),('PLOAD',16,'0304')])
        self.assertEqual([r['written'] for r in result],[16,32])
        self.assertEqual(c.process.stdin.getvalue(),'FIR 41 PLOAD 0 0102\nFIR 42 PLOAD 16 0304\n')

    def test_wrong_verb_error_duplicate_and_missing_reply_refused(self):
        for lines in [['FIR,41,ERR,PLOAD'],['FIR,41,OK,OTHER'],['FIR,41,OK,PLOAD,written=16','FIR,41,OK,PLOAD,written=16'],[]]:
            with self.subTest(lines=lines):
                c=self.client(lines)
                with self.assertRaises((RuntimeError,TimeoutError)):c.commands([('PLOAD',0,'0102'),('PLOAD',16,'0304')])

    def test_batch_bound_and_single_line_framing_required_before_write(self):
        for calls in [[],[('PLOAD',0,'00')]*17,[('PLOAD',0,'00\nFIR 5 PCLEAR')]]:
            c=self.client([])
            with self.assertRaises(ValueError):c.commands(calls)
            self.assertEqual(c.process.stdin.getvalue(),'')


if __name__=='__main__':unittest.main()
