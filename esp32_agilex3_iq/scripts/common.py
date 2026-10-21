"""Discover local FPGA tools; optional host-to-container compatibility helpers."""
import json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CONTAINER=os.getenv('ATUM_CONTAINER','agilex-xrdp')
def resolve_uart(port=None):
    """Resolve the Atum UART without opening it; never guess among USB serial ports."""
    requested=port if port is not None else os.getenv('ATUM_UART')
    if requested is not None:
        requested=os.fspath(requested)
        if not requested or not Path(requested).exists():
            raise RuntimeError(f'Configured UART {requested!r} does not exist. Set ATUM_UART to the board UART exposed in this environment.')
        return requested
    candidates={}
    for path in sorted(Path('/dev/serial/by-id').glob('usb-TERASIC_Atum_A3_Nano_*-if01-port0')):
        if path.exists():candidates[path.resolve()]=str(path)
    from serial.tools import list_ports
    for info in list_ports.comports():
        if (info.vid,info.pid)!=(0x09fb,0x6022):continue
        # The Atum's FTDI interface 0 is JTAG; interface 1 is the sample UART.
        if info.location and not info.location.endswith(':1.1'):continue
        path=Path(info.device)
        if path.exists():candidates.setdefault(path.resolve(),str(path))
    if len(candidates)==1:return next(iter(candidates.values()))
    if candidates:
        raise RuntimeError('Multiple Atum A3 Nano UARTs detected: '+', '.join(sorted(candidates.values()))+'. Set ATUM_UART explicitly.')
    raise RuntimeError('No Atum A3 Nano UART detected. Connect/expose the board USB UART or set ATUM_UART explicitly.')

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
def stages():return sorted((ROOT/'fpga_hub/iq_bridge').glob('vds_demo_0[1-5]_*'))

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
