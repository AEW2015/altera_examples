"""Export the real Quartus 26.1 VDS drawing through File > Export, then rasterize to PNG.

A private Xvfb display isolates GUI automation from the presenter's desktop.
No FPGA programming, synthesis, diagram reconstruction or GUI source edits occur.
"""
import json,os,select,shutil,signal,subprocess,time
from pathlib import Path
from common import tool_exe,tool_env,local_tools

def export_gui(stage,out,expected_cells):
 if not local_tools():raise RuntimeError('Run GUI export beside the installed Quartus tools (ATUM_TOOLS_MODE=local).')
 for name in('Xvfb','xdotool','scrot','pdftoppm','pdfinfo','pdftotext'):
  if not shutil.which(name):raise RuntimeError(f'Missing {name}; run bash scripts/install_local.sh --system')
 stage=Path(stage).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
 system=stage/'src/vds/iq_bridge_system/iq_bridge_system.vds'
 if not system.exists():raise RuntimeError('Generate the native VDS system first.')
 ready=out/'vds-gui-cells.txt';pdf=out/'vds_diagram.pdf';png=out/'vds_diagram.png'
 for p in(ready,pdf,png,out/'vds_gui_window.png',out/'vds_gui_error.png'):p.unlink(missing_ok=True)
 # A separate project wrapper prevents locks or focus changes in an already-open user project.
 work=out/'gui_project';work.mkdir(exist_ok=True)
 from quartus_project import prepare_project
 prepare_project(stage,work)
 gui_system=work/'src/vds/iq_bridge_system/iq_bridge_system.vds'
 log=(out/'vds-gui.log').open('w');read_fd,write_fd=os.pipe();server=None;gui=None
 try:
  server=subprocess.Popen(['Xvfb','-displayfd',str(write_fd),'-screen','0','3200x2000x24','-nolisten','tcp'],pass_fds=(write_fd,),stdout=log,stderr=log,start_new_session=True)
  os.close(write_fd);write_fd=None
  if not select.select([read_fd],[],[],10)[0]:raise RuntimeError('Private X display did not start.')
  display=':'+os.read(read_fd,64).decode().strip()
  env=dict(tool_env(),DISPLAY=display,QT_SCALE_FACTOR='1',QT_AUTO_SCREEN_SCALE_FACTOR='0',QT_FONT_DPI='100')
  def x(*args):return subprocess.run(['xdotool',*map(str,args)],env=env,check=True,text=True,capture_output=True).stdout
  def window(prefix,timeout=30):
   end=time.monotonic()+timeout
   while time.monotonic()<end:
    p=subprocess.run(['xdotool','search','--onlyvisible','--name','^'+prefix],env=env,text=True,capture_output=True)
    if p.returncode==0 and p.stdout.strip():return p.stdout.splitlines()[0]
    if gui.poll()is not None:raise RuntimeError('Quartus GUI exited; inspect '+str(out/'vds-gui.log'))
    time.sleep(.25)
   raise TimeoutError('Missing GUI window: '+prefix)
  def focus(w):
   x('windowmove',w,0,0);x('windowsize',w,3200,2000);x('windowfocus','--sync',w);time.sleep(.3)
  def menu(name):
   # Native menu mnemonics; seven Up presses wrap from the first item to the
   # VDS launcher / drawing Export action in Quartus 26.1, independent of DPI.
   x('key','Escape');x('key','alt+'+name);time.sleep(.5)
   for _ in range(7):x('key','Up');time.sleep(.12)
   x('key','Return')
  gui=subprocess.Popen([str(tool_exe('quartus')),str(work/'iq_bridge_vds.qpf')],cwd=work,env=env,stdout=log,stderr=log,start_new_session=True)
  main=window('Quartus Prime.*gui_project',90);focus(main);time.sleep(8);menu('t')
  vds=window('Visual Designer Studio',45);focus(vds)
  # A source command is executed by VDS's own Tcl console. Braced paths handle spaces.
  script=out/'vds-open-for-export.tcl'
  script.write_text('vds::open_system {'+str(gui_system)+'}\nset f [open {'+str(ready)+'} w]\nputs $f [vds::get_cells]\nclose $f\n')
  x('mousemove',700,1938,'click',1);x('type','--clearmodifiers','--delay','1','source {'+str(script)+'}');x('key','Return')
  end=time.monotonic()+120
  while not ready.exists():
   if time.monotonic()>end:raise TimeoutError('VDS did not finish opening the diagram; see vds-gui.log.')
   time.sleep(.25)
  cells=ready.read_text().split()
  if len(cells)!=expected_cells:raise RuntimeError(f'Wrong GUI system: {len(cells)} cells, expected {expected_cells}.')
  x('mousemove',1800,600,'click',1);x('key','ctrl+alt+w');time.sleep(1)
  subprocess.run(['scrot',str(out/'vds_gui_window.png')],env=env,check=True)
  menu('f');dialog=window('Export as',10);x('windowfocus','--sync',dialog)
  x('key','alt+n');x('type','--clearmodifiers','--delay','1',str(pdf));x('key','Return')
  end=time.monotonic()+30;previous=-1
  while True:
   size=pdf.stat().st_size if pdf.exists()else 0
   if size>1000 and size==previous:break
   if time.monotonic()>end:raise TimeoutError('Native VDS PDF export did not complete.')
   previous=size;time.sleep(.4)
  info=subprocess.check_output(['pdfinfo',str(pdf)],text=True)
  labels=subprocess.check_output(['pdftotext',str(pdf),'-'],text=True)
  if 'Nlview'not in info or any(c not in labels for c in cells):raise RuntimeError('Native GUI PDF is missing expected cell labels.')
  subprocess.run(['pdftoppm','-png','-singlefile','-scale-to','4000',str(pdf),str(png.with_suffix(''))],check=True)
  from PIL import Image
  with Image.open(png)as image:dimensions=list(image.size)
  (out/'vds_gui_export.json').write_text(json.dumps(dict(origin='Quartus Visual Designer Studio GUI File > Export (native Nlview PDF)',project=str(stage/'iq_bridge_vds.qpf'),gui_project=str(work/'iq_bridge_vds.qpf'),system=str(system),gui_system=str(gui_system),cells=cells,cell_count=len(cells),png=png.name,pdf=pdf.name,png_size=dimensions,gui_screenshot='vds_gui_window.png',created_unix=time.time()),indent=2)+'\n')
  print('Native VDS GUI export:',len(cells),'blocks →',png)
  return png
 except Exception:
  if 'env'in locals():
   try:subprocess.run(['scrot',str(out/'vds_gui_error.png')],env=env,timeout=5,capture_output=True)
   except Exception:pass
  raise
 finally:
  for p in(gui,server):
   if p is not None and p.poll()is None:
    try:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=8)
    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
    except ProcessLookupError:pass
  os.close(read_fd)
  if write_fd is not None:os.close(write_fd)
  log.close()
