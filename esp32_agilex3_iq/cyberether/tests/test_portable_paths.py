"""A nested bind mount must resolve correctly without a workstation path."""
import json,os,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import common
class Paths(unittest.TestCase):
 def test_longest_matching_mount(self):
  mounts=[dict(Source='/host',Destination='/broad'),dict(Source='/host/repo',Destination='/example')]
  with patch.object(common,'ROOT',Path('/host/repo/esp32_agilex3_iq')),patch.dict(os.environ,{},clear=True),patch('common.subprocess.check_output',return_value=json.dumps(mounts)):
   self.assertEqual(common.container_root(),'/example/esp32_agilex3_iq')
 def test_override_needs_no_docker_and_missing_mount_is_actionable(self):
  with patch.dict(os.environ,{'ATUM_CONTAINER_ROOT':'/custom/example/'},clear=True),patch('common.subprocess.check_output',side_effect=AssertionError):
   self.assertEqual(common.container_root(),'/custom/example')
  with patch.dict(os.environ,{},clear=True),patch('common.subprocess.check_output',return_value='[]'):
   with self.assertRaisesRegex(RuntimeError,'ATUM_CONTAINER_ROOT'):common.container_root()
if __name__=='__main__':unittest.main()
