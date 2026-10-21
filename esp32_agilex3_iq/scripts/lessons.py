"""Local notebook workflow: theory, real VDS/IP, simulation, programming and live UI."""
import hashlib,json,os,re,signal,socket,subprocess,sys,time,shlex
from pathlib import Path
from common import ROOT,stages,tool_command,tool_path,local_tools,tool_exe
NAMES=['Raw IQ bridge','Nios V transfer monitor','FIR II filtering','Frequency translation and decimation','Digital gain and power meters']
def lan_ip():
 s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
 try:s.connect(('192.0.2.1',80));return s.getsockname()[0]
 except OSError:return '127.0.0.1'
 finally:s.close()
def fingerprint(stage):
 h=hashlib.sha256()
 files=[p for d in('rtl','ip','sw','scripts')for p in(stage/d).glob('*')if p.suffix in('.sv','.tcl','.c','.h','.ld','.S','.json','.sh')and p.name not in('iq_bridge_system_export.tcl','BUILD_RESULT.json')]+[stage/'iq_bridge_vds.sdc']
 for p in sorted(files):h.update(str(p.relative_to(stage)).encode()+p.read_bytes())
 # Preserve device/pin/electrical assignments, ignoring generated VDS cache paths.
 qsf=(stage/'iq_bridge_vds.qsf').read_text().splitlines()
 h.update('\n'.join(sorted(set(re.sub(r'\s+-entity\s+iq_bridge_vds_top\b','',l).strip() for l in qsf if 'set_location_assignment'in l or 'IO_STANDARD'in l or '-name DEVICE 'in l or '-name FAMILY 'in l))).encode())
 return h.hexdigest()
def stop_demo():
 p=ROOT/'cyberether/run/notebook-demo.json'
 if not p.exists():return
 d=json.loads(p.read_text());pid=d['pid'];cmd=Path('/proc')/str(pid)/'cmdline';needle=str(ROOT/'cyberether/start_iq_bridge_lab.py').encode()
 if not cmd.exists()or needle not in cmd.read_bytes().split(b'\0'):return
 os.kill(pid,signal.SIGTERM);end=time.monotonic()+40
 while cmd.exists()and cmd.read_bytes():
  if time.monotonic()>end:raise RuntimeError('Notebook viewer did not release hardware')
  time.sleep(.2)
class Lesson:
 def __init__(self,n):
  if n not in range(1,6):raise ValueError('Checkpoint 1–5 required')
  self.n=n;self.name=NAMES[n-1];self.stage=stages()[n-1];self.out=self.stage/'results/notebook';self.out.mkdir(parents=True,exist_ok=True)
 def command(self,args,log,cwd=None,timeout=1800):
  with Path(log).open('w')as f:
   p=subprocess.run(list(map(str,args)),cwd=cwd or ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
  tail='\n'.join(Path(log).read_text(errors='replace').splitlines()[-8:]);print(tail)
  if p.returncode:raise RuntimeError(f'Command failed ({p.returncode}); inspect {log}')
 def generate(self):
  self.command([sys.executable,ROOT/'scripts/build.py',self.n,'--generate-only','--display',os.getenv('DISPLAY',':0')],self.out/'generate.log')
  return self.diagram()
 def diagram(self):
  export=self.stage/'scripts/iq_bridge_system_export.tcl'
  if not export.exists():raise RuntimeError('Generate the native VDS system first')
  cells={};edges=[]
  for line in export.read_text().splitlines():
   if line.startswith('vds::create_cell '):
    words=line.split();name=words[1]if not words[1].startswith('-')else words[-1];kind=re.search(r'-vlnv (\S+)',line)
    cells[name]=kind[1].split(':')[-2]if kind else'RTL'
   if line.startswith(('vds::connect_net ','vds::connect_interface_net ')):
    a=re.search(r'-src (\S+)',line);b=re.search(r'-dest (\S+)',line)
    if a and b:edges.append((a[1],b[1]))
  expected=[6,11,13,16,17][self.n-1];assert len(cells)==expected,(cells,expected)
  quote=lambda value:json.dumps(value,ensure_ascii=False)
  lines=['digraph G {','rankdir=LR; bgcolor="#0b121e";','node [shape=box,style="rounded,filled",fillcolor="#142234",color="#52dfdd",fontcolor="white",fontname="DejaVu Sans"];','edge [color="#9ab2c9",fontcolor="#9ab2c9",fontsize=9];']
  for name,kind in cells.items():lines.append(quote(name)+' [label='+quote(name+'\n'+kind)+'];')
  for a,b in edges:
   x,_,port=a.partition('|');y,_,dest=b.partition('|')
   if x in cells and y in cells and x!=y:
    if x in('clock50','reset_bridge','cpu_reset'):continue
    lines.append(quote(x)+' -> '+quote(y)+' [label='+quote(port+' → '+dest)+'];')
  lines+=['label='+quote(f'{self.n} · {self.name} · {expected} actual native VDS blocks\nClock/reset fanout hidden; topology from Quartus-exported Tcl')+';fontcolor="white";labelloc=t;','}']
  dot=self.out/'block_diagram.dot';dot.write_text('\n'.join(lines))
  for ext in('svg','png'):subprocess.run(['dot','-T'+ext,str(dot),'-o',str(self.out/('block_diagram.'+ext))],check=True)
  (self.out/'block_diagram.json').write_text(json.dumps(dict(origin='Quartus native VDS export',cells=cells,connections=edges,clock_reset_edges_hidden=True),indent=2))
  from IPython.display import SVG,display
  display(SVG(filename=str(self.out/'block_diagram.svg')))
  return self.out/'block_diagram.png'
 def simulate(self):
  self.command([sys.executable,ROOT/'scripts/simulate_lesson.py',self.n],self.out/'simulation-command.log',timeout=900)
  result=json.loads((self.out/'simulation/result.json').read_text());assert result['status']=='PASS';return result
 def simulation_plot(self):
  from notebook_plots import simulation_plot
  return simulation_plot(self)
 def build(self,force=False):
  p=self.stage/'BUILD_RESULT.json';sof=self.stage/'iq_bridge_vds.sof';sig=fingerprint(self.stage)
  if not force and p.exists()and sof.exists():
   d=json.loads(p.read_text())
   if d.get('source_fingerprint')==sig and d.get('sha256')==hashlib.sha256(sof.read_bytes()).hexdigest():
    print('Reusing source-matched cached SOF:',d['sha256'][:16],'; set FORCE_REBUILD=True to compile again.');return d
  self.command([sys.executable,ROOT/'scripts/build.py',self.n,'--display',os.getenv('DISPLAY',':0')],self.out/'build-command.log')
  d=json.loads(p.read_text());d['source_fingerprint']=fingerprint(self.stage);p.write_text(json.dumps(d,indent=2)+'\n');return d
 def program(self):
  stop_demo()
  self.command([sys.executable,ROOT/'scripts/run.py','load','--checkpoint',self.n],self.out/'program.log')
 def start_demo(self,host=None):
  stop_demo();host=host or lan_ip();run=ROOT/'cyberether/run';run.mkdir(exist_ok=True)
  env=dict(os.environ,ATUM_LESSON=str(self.n),ATUM_CONTAINER_ROOT=tool_path(ROOT))
  launched=time.time()
  log=(run/'notebook-launch.log').open('a')
  args=[sys.executable,str(ROOT/'cyberether/start_iq_bridge_lab.py'),'--host',host]
  p=subprocess.Popen(args,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);log.close()
  (run/'notebook-demo.json').write_text(json.dumps(dict(pid=p.pid,lesson=self.n,host=host)))
  end=time.monotonic()+100
  while time.monotonic()<end:
   if p.poll()is not None:raise RuntimeError('Viewer exited; inspect cyberether/run/notebook-launch.log')
   state=run/'iq-bridge-lab/state.json'
   if state.exists():
    s=json.loads(state.read_text())
    if s.get('completed',0)>0 and s.get('fpga',{}).get('stage_relative')==str(self.stage.relative_to(ROOT))and s.get('updated_unix',0)>=launched and s.get('updated_unix',0)>time.time()-4:break
   time.sleep(.3)
  else:raise RuntimeError('No live result; inspect the acquisition log')
  invite=run/'iq-bridge-lab/control-invite.json';self.url=json.loads(invite.read_text())['url']
  from IPython.display import HTML,display
  import html
  display(HTML('<a target="_blank" href="'+html.escape(self.url,quote=True)+'">Open '+str(self.n)+' · '+self.name+' in CyberEther</a>'))
  return dict(status=s['status'],results=s['completed'],checkpoint=self.n)
 def theory(self):
  from notebook_plots import theory
  return theory(self.n)
 def questa_gui(self):
  p=self.out/'simulation'
  print(f"Desktop terminal (on the machine running the tools):\ncd {shlex.quote(str(p))}\n{shlex.quote(str(tool_exe('vsim')))} -gui -view wave.wlf -do view.do")
