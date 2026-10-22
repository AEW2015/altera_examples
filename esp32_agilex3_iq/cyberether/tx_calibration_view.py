"""Read-only calibration telemetry; no UART, JTAG, subprocess or RF access."""
import json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'cyberether/run'
def read(pointer=None):
    pointer=Path(pointer) if pointer is not None else RUN/'tx-lab-calibration-active.json'
    result={'state':'waiting','levels':[],'observations':0,'qualified_captures':0,'plot':False,'host_dsp':True,'qam_qualified':False}
    try:
        if not pointer.exists():return result,None
        meta=json.loads(pointer.read_text());path=(ROOT/meta['status']).resolve()
        path.relative_to(RUN.resolve())
        if path.name!='status.json' or path.stat().st_size>4*1024*1024:raise ValueError('Invalid calibration report')
        data=json.loads(path.read_text(),parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite calibration value')))
        rows=data.get('observations',[])
        result.update(state=data['state'],calibration_state=data.get('calibration_state','waiting'),levels=data.get('summary',{}).get('levels',[]),
                      observations=len(rows),qualified_captures=sum(r.get('qualified') is True for r in rows),started_unix=data.get('started_unix'),updated_unix=data.get('updated_unix'),
                      native_checks=len(data.get('native_checks',[])),error=data.get('error'),gated_code=data.get('gated_code'))
        image=path.parent/'amplitude-calibration.png';image=image.resolve();image.relative_to(RUN.resolve())
        result['plot']=image.is_file();return result,image if result['plot'] else None
    except (OSError,ValueError,KeyError,TypeError) as error:
        result.update(state='telemetry_error',error=str(error));return result,None
