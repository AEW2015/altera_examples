"""Notebook facade for checkpoint07; construction never accesses hardware."""
import os
from pathlib import Path
from notebook_progress import task
from spi_pipeline import STAGE, build


class SPILesson:
    stage = STAGE

    def project(self, project):
        from IPython.display import FileLink, display
        prepared = self.stage / 'results/quartus_project/iq_bridge_vds.qpf'
        archive = self.stage / 'results' / (self.stage.name + '-quartus-project.zip')
        if not prepared.exists() or not archive.exists():
            raise RuntimeError('Build/generate must export the complete Quartus project first')
        display(FileLink(os.path.relpath(prepared, Path.cwd()), result_html_prefix='Quartus project: '))
        display(FileLink(os.path.relpath(archive, Path.cwd()), result_html_prefix='Complete project ZIP: '))
        return prepared

    @task('Generate SPI/FIR VDS design and actual GUI diagram')
    def generate(self):
        from vds_gui_export import export_gui
        self.project(build(generate_only=True))
        return export_gui(self.stage, self.stage / 'results/notebook', 13)

    @task('Compile SPI/FIR FPGA design')
    def build(self):
        return self.project(build(generate_only=False))
