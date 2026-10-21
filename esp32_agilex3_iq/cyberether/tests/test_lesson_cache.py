"""A generated VDS export must not invalidate an unchanged demonstration SOF."""
import tempfile,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from lessons import fingerprint
class Cache(unittest.TestCase):
 def test_top_entity_annotations_are_normalized_but_electrical_changes_are_not(self):
  with tempfile.TemporaryDirectory()as d:
   p=Path(d);(p/'rtl').mkdir();(p/'rtl/a.sv').write_text('module a; endmodule')
   (p/'scripts').mkdir();(p/'iq_bridge_vds.sdc').write_text('create_clock -period 20 clk')
   qsf=p/'iq_bridge_vds.qsf';line='set_instance_assignment -name IO_STANDARD "3.3-V LVCMOS" -to HOST_*'
   qsf.write_text(line);before=fingerprint(p)
   qsf.write_text(line+' -entity iq_bridge_vds_top\nset_global_assignment -name VDS_FILE generated.vds')
   (p/'scripts/iq_bridge_system_export.tcl').write_text('generated')
   self.assertEqual(before,fingerprint(p))
   qsf.write_text(line.replace('3.3-V','1.8 V'))
   self.assertNotEqual(before,fingerprint(p))
if __name__=='__main__':unittest.main()
