"""Discover local FPGA tools; optional host-to-container compatibility helpers."""
import json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CONTAINER=os.getenv('ATUM_CONTAINER','agilex-xrdp')
def container_root():
    if local_tools():return str(ROOT)
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

def local_tools():
    return os.getenv('ATUM_TOOLS_MODE','local')!='docker'
def tool_command(args,cwd=None,display=None):
    if local_tools():
        return [str(tool_exe(Path(x).name))if str(x).startswith('/opt/altera/')and Path(x).name in('quartus_sh','quartus_pgm','quartus','juart-terminal','vsim')else str(x)for x in args]
    cmd=['docker','exec','-u','dev']
    if display:cmd+=['-e','DISPLAY='+display]
    if cwd:cmd+=['-w',container_root()+'/'+str(Path(cwd).relative_to(ROOT))]
    return cmd+[CONTAINER,*map(str,args)]
def tool_path(p):
    return str(p)if local_tools()else container_root()+'/'+str(Path(p).relative_to(ROOT))

# Local Quartus/Questa discovery works identically on a host or in a container.
def quartus_root():
    import shutil
    explicit=os.getenv('QUARTUS_ROOTDIR')
    if explicit:return Path(explicit).expanduser().resolve()
    found=shutil.which('quartus_sh')
    return Path(found).resolve().parent.parent if found else Path('/opt/altera/quartus')
def altera_root():return Path(os.getenv('ATUM_ALTERA_ROOT',str(quartus_root().parent)))
def tool_exe(name):
    import shutil
    if name in('quartus_sh','quartus_pgm','quartus','juart-terminal'):return quartus_root()/'bin'/name
    if name=='vsim':
        root=os.getenv('QUESTA_ROOT')
        if root:return Path(root)/'bin/vsim'
        found=shutil.which('vsim')
        return Path(found).absolute()if found else altera_root()/'questa_fse/bin/vsim'
    return Path(shutil.which(name)or name)
def tool_env():
    return dict(os.environ,QUARTUS_ROOTDIR=str(quartus_root()),ATUM_ALTERA_ROOT=str(altera_root()),PATH=str(quartus_root()/'bin')+os.pathsep+os.environ.get('PATH',''))
