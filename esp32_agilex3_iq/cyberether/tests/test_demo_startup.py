"""Report the fresh acquisition failure and resolve the UART before launching."""
import contextlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import lessons


class DemoStartup(unittest.TestCase):
    def test_missing_uart_fails_before_stopping_existing_demo_or_spawning(self):
        lesson=object.__new__(lessons.Lesson)
        with patch.object(lessons,'progress',return_value=contextlib.nullcontext(Mock())), \
             patch.object(lessons,'resolve_uart',side_effect=RuntimeError('Set ATUM_UART')), \
             patch.object(lessons,'stop_demo')as stop, \
             patch.object(lessons.subprocess,'Popen')as spawn:
            with self.assertRaisesRegex(RuntimeError,'Set ATUM_UART'):
                lessons.Lesson.start_demo.__wrapped__(lesson,host='127.0.0.1',demo_night=True)
        stop.assert_not_called()
        spawn.assert_not_called()

    def test_timeout_includes_only_current_launch_acquisition_error(self):
        for updated,expected in ((102,True),(99,False)):
            with self.subTest(updated=updated),tempfile.TemporaryDirectory()as directory:
                root=Path(directory)
                run=root/'cyberether/run/iq-bridge-lab'
                run.mkdir(parents=True)
                message='UART read failed: disconnected'
                (run/'state.json').write_text(json.dumps(dict(updated_unix=updated,error=message)))
                lesson=object.__new__(lessons.Lesson)
                lesson.n=5
                lesson.stage=root/'fpga_hub/iq_bridge/vds_demo_05_gain'
                process=Mock(pid=12345)
                process.poll.return_value=None
                with patch.object(lessons,'ROOT',root), \
                     patch.object(lessons,'progress',side_effect=lambda *a,**k:contextlib.nullcontext(Mock())), \
                     patch.object(lessons,'resolve_uart',return_value='/dev/selected-board'), \
                     patch.object(lessons,'stop_demo'), \
                     patch.object(lessons.subprocess,'Popen',return_value=process)as spawn, \
                     patch.object(lessons.time,'time',return_value=100), \
                     patch.object(lessons.time,'monotonic',side_effect=[0,0,101]), \
                     patch.object(lessons.time,'sleep'):
                    with self.assertRaises(RuntimeError)as error:
                        lessons.Lesson.start_demo.__wrapped__(lesson,host='127.0.0.1',demo_night=True)
                self.assertEqual(message in str(error.exception),expected)
                self.assertIn('acquisition.log',str(error.exception))
                self.assertEqual(spawn.call_args.kwargs['env']['ATUM_UART'],'/dev/selected-board')


if __name__=='__main__':
    unittest.main()
