"""Resolve the example's bind mount rather than assuming a host checkout path."""
import json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CONTAINER=os.getenv('ATUM_CONTAINER','agilex-xrdp')
def container_root():
    if os.getenv('ATUM_CONTAINER_ROOT'):return os.environ['ATUM_CONTAINER_ROOT'].rstrip('/')
    mounts=json.loads(subprocess.check_output(['docker','inspect','--format','{{json .Mounts}}',CONTAINER],text=True))
    for m in sorted(mounts,key=lambda x:len(x['Source']),reverse=True):
        try:rel=ROOT.relative_to(m['Source'])
        except ValueError:continue
        return str(Path(m['Destination'])/rel)
    raise RuntimeError('Example is not mounted in '+CONTAINER+'; set ATUM_CONTAINER_ROOT after adding its bind mount')
def env():
    return dict(os.environ,ATUM_CONTAINER_ROOT=container_root(),ATUM_CONTAINER=CONTAINER)
def stages():return sorted((ROOT/'fpga_hub/iq_bridge').glob('vds_demo_0*'))
