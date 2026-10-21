#!/usr/bin/env python3
"""Load checkpoint 5 and launch RF Arcade with real acquisition and FPGA DSP controls."""
import argparse,json,time
from common import ROOT
from lessons import Lesson,lan_ip
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host',default=lan_ip());a=p.parse_args()
lesson=Lesson(5);lesson.build();lesson.program();print(lesson.start_demo(a.host,demo_night=True))
print('RF Arcade:',json.loads((ROOT/'cyberether/run/iq-bridge-lab/control-invite.json').read_text())['url'])
print('Open the link, select Showreel, then fullscreen. Stops with lessons.stop_demo().')
