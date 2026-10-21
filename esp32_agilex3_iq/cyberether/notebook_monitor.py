"""Read real checkpoint-2 Nios V transfer counters through JTAG UART."""
import json,os,signal,subprocess,threading,time
from pathlib import Path
from nios_fir import ROOT,CABLE,tool_command,tool_path
class PassiveMonitor:
 def __init__(self,run):
  self.value={};self.pidfile=run/'monitor.pid'
  self.process=subprocess.Popen(tool_command(['/opt/altera/quartus/bin/juart-terminal','-q','-c',CABLE,'-d','1','-i','0','--no-quit-on-ctrl-d','--write-pid',tool_path(self.pidfile)]),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
  def read():
   for row in self.process.stdout:
    if not row.startswith('IQMON,'):continue
    data={}
    for field in row.strip().split(',')[1:]:
     key,_,value=field.partition('=')
     try:data[key]=int(value,16 if key.startswith('total')or key=='ticks'else 10)
     except ValueError:continue
    self.value=dict(data,received_unix=time.time())
  self.thread=threading.Thread(target=read,daemon=True);self.thread.start()
 def close(self):
  if self.pidfile.exists():
   cleanup="import os,signal,sys;from pathlib import Path;p=Path(sys.argv[1]);pid=int(p.read_text());q=Path('/proc')/str(pid)/'cmdline';exec(\"if q.exists() and b'juart-terminal' in q.read_bytes():os.kill(pid,signal.SIGTERM)\")"
   subprocess.run(tool_command(['python3','-c',cleanup,tool_path(self.pidfile)]),capture_output=True)
  if self.process.stdin:self.process.stdin.close()
  try:self.process.wait(timeout=5)
  except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
  self.thread.join(timeout=1)
