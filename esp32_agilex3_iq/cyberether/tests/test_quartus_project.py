"""A linked Quartus project must include constraints and every leaf-IP input."""
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from quartus_project import check_project, prepare_project


class ProjectClosure(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stage = self.root / 'lesson'
        self.stage.mkdir()
        for name, data in {
            'iq_bridge_vds.qpf': 'PROJECT_REVISION = "iq_bridge_vds"',
            'iq_bridge_vds.qsf': 'set_global_assignment -name SDC_FILE iq_bridge_vds.sdc\nset_global_assignment -name SYSTEMVERILOG_FILE rtl/top.sv\nset_global_assignment -name VDS_FILE src/design.vds\n',
            'iq_bridge_vds.sdc': 'create_clock -period 20 [get_ports CLOCK1_50]',
            'rtl/top.sv': 'module top; endmodule',
            'src/design.vds': 'native diagram fixture',
            'gen/vds/iq_bridge_system/iq_bridge_system.qip': 'set_global_assignment -name VERILOG_FILE [file join $::quartus(qip_path) "system.v"]',
            'gen/vds/iq_bridge_system/system.v': 'module system; endmodule',
            'gen/vds/iq_bridge_system/ip/clock/clock.qip': 'set_global_assignment -name VERILOG_FILE [file join $::quartus(qip_path) "clock.v"]',
            'gen/vds/iq_bridge_system/ip/clock/clock.v': 'module clock; endmodule',
        }.items():
            p = self.stage / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(data)

    def test_extracted_zip_has_sdc_and_leaf_ip_inputs_without_symlinks(self):
        export = self.root / 'output'
        archive = self.root / 'project.zip'
        prepare_project(self.stage, export, archive)
        with zipfile.ZipFile(archive) as z:
            z.extractall(self.root / 'fresh location')
        copied = self.root / 'fresh location/lesson'
        required = check_project(copied)
        self.assertIn('iq_bridge_vds.sdc', required)
        self.assertIn('gen/vds/iq_bridge_system/ip/clock/clock.qip', required)
        self.assertFalse(any(p.is_symlink() for p in copied.rglob('*')))
        self.assertNotIn('-name VDS_FILE', (copied / 'iq_bridge_vds.qsf').read_text())

    def test_missing_constraint_is_an_export_error(self):
        (self.stage / 'iq_bridge_vds.sdc').unlink()
        with self.assertRaises(FileNotFoundError):
            prepare_project(self.stage, self.root / 'output')

    def test_missing_leaf_hdl_is_an_export_error(self):
        (self.stage / 'gen/vds/iq_bridge_system/ip/clock/clock.v').unlink()
        with self.assertRaisesRegex(ValueError, 'missing/external'):
            prepare_project(self.stage, self.root / 'output')

    def test_old_gui_wrapper_symlinks_become_independent_copies(self):
        export = self.root / 'old_gui_project'
        export.mkdir()
        (export / 'rtl').symlink_to(self.stage / 'rtl', target_is_directory=True)
        prepare_project(self.stage, export)
        self.assertFalse((export / 'rtl').is_symlink())
        self.assertEqual((export / 'rtl/top.sv').read_bytes(), (self.stage / 'rtl/top.sv').read_bytes())
