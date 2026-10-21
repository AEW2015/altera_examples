"""Progress heartbeats must not mask tool failures or open any hardware."""
import contextlib
import io
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import notebook_progress as ui


class Handle:
    def __init__(self):self.updates=[]
    def update(self,html):self.updates.append(html)


class ProgressTests(unittest.TestCase):
    def frontend(self):
        handle=Handle();initial=[]
        def display(html,display_id=False):
            initial.append(html);return handle
        return handle,initial,(lambda text:text,display)

    def test_live_heartbeat_unknown_percentage_and_completion(self):
        handle,initial,frontend=self.frontend()
        with patch.object(ui,'_notebook_display',return_value=frontend):
            with ui.Activity('Build <FPGA>',interval=.02)as activity:
                time.sleep(.07)
                self.assertTrue(handle.updates)
                self.assertNotIn('value="',initial[0])
                self.assertIn('Build &lt;FPGA&gt;',initial[0])
            self.assertEqual(activity.status,'DONE')
            self.assertIn('value="1"',handle.updates[-1])
            self.assertIn('elapsed',handle.updates[-1])
            self.assertFalse(activity._thread.is_alive())

    def test_failure_cancellation_and_nested_row(self):
        handle,initial,frontend=self.frontend()
        with patch.object(ui,'_notebook_display',return_value=frontend):
            with self.assertRaisesRegex(RuntimeError,'Compiler failed'):
                with ui.progress('Outer')as outer:
                    with ui.progress('Fitter')as inner:
                        self.assertIs(inner,outer)
                        self.assertEqual(outer.phase,'Fitter')
                        raise RuntimeError('Compiler failed')
            self.assertEqual(len(initial),1)
            self.assertIn('FAILED',handle.updates[-1]);self.assertNotIn('value="1"',handle.updates[-1])
            self.assertIsNone(ui._ACTIVE.get())
            with self.assertRaises(KeyboardInterrupt):
                with ui.progress('Interrupted'):raise KeyboardInterrupt()
            self.assertIn('CANCELLED',handle.updates[-1])

    def test_bounded_fresh_log_tail_and_html_escape(self):
        with tempfile.TemporaryDirectory()as directory:
            path=Path(directory)/'build.log'
            path.write_text('old content')
            activity=ui.Activity('Synthesis',logs=[path])
            self.assertNotIn('old content',activity.markup())
            path.write_text('x'*20000+'\n\x1b[32mFitter <route>\x1b[0m\n')
            self.assertIn('Fitter &lt;route&gt;',activity.markup())
            self.assertLess(len(activity.markup()),2000)
            self.assertIn(str(path),activity.markup())

    def test_no_widgets_required_and_display_failure_preserves_result(self):
        def broken(*args,**kwargs):raise RuntimeError('Frontend disconnected')
        with patch.object(ui,'_notebook_display',return_value=(lambda x:x,broken)),contextlib.redirect_stdout(io.StringIO()):
            @ui.task('Export')
            def export():return 'diagram.png'
            self.assertEqual(export(),'diagram.png')
        self.assertFalse(any(t.name=='notebook-progress'for t in threading.enumerate()))

    def test_real_subprocess_with_log_and_nonzero_exit(self):
        from lessons import Lesson
        with tempfile.TemporaryDirectory()as directory,patch.object(ui,'_notebook_display',return_value=None),contextlib.redirect_stdout(io.StringIO()):
            lesson=Lesson(1);log=Path(directory)/'command.log'
            lesson.command([sys.executable,'-c','print("real child output",flush=True)'],log)
            self.assertIn('real child output',log.read_text())
            with self.assertRaisesRegex(RuntimeError,'Command failed'):
                lesson.command([sys.executable,'-c','raise SystemExit(7)'],log)
