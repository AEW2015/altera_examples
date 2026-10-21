"""Notebook FIR controls through the running CyberEther owner's authenticated API.
No second UART or JTAG client is created. Importing this module performs no I/O.
"""
import json
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit
from fir_filters import CATALOG,resolve_filter,validate_coefficients
from notebook_progress import progress

ROOT=Path(__file__).resolve().parents[1]


class FIRControls:
    def __init__(self,run=None):
        self.run=Path(run)if run else ROOT/'cyberether/run/iq-bridge-lab'
        try:invite=json.loads((self.run/'control-invite.json').read_text())['url']
        except (OSError,KeyError):raise RuntimeError('Start this notebook’s CyberEther demo first')from None
        url=urlsplit(invite);self._base=url.scheme+'://'+url.netloc;self._token=url.fragment
        if url.scheme!='http'or not self._token:raise ValueError('Invalid local demo invite')

    def _api(self,path,body=None):
        request=urllib.request.Request(self._base+'/api/'+path,data=json.dumps(body).encode()if body is not None else None,
            headers={'X-Lab-Token':self._token,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=8)as response:return json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError(json.load(error).get('error',str(error)))from None

    def state(self):return self._api('state')

    def examples(self):
        return [dict(id=e['id'],title=e['title'],description=e['description'])for e in CATALOG.values()]

    def apply(self,name=None,*,coefficients=None,input_kind='fpga-tones',timeout=100):
        if coefficients is not None:
            if name not in (None,'custom'):raise ValueError('Supply either a named example or custom coefficients')
            coefficients=validate_coefficients(coefficients);name='custom'
        elif name not in CATALOG:raise ValueError('Choose an example name or supply 16 Q15 coefficients')
        if input_kind not in ('live','fpga-impulse','fpga-tones'):raise ValueError('Unknown FIR input')
        spec=resolve_filter(dict(view='custom',fir_filter=name,fir_coefficients=coefficients))
        with progress('Apply FIR and verify the FPGA result')as feedback:
            started=time.time()
            self._api('control',dict(fir_filter=name,fir_coefficients=coefficients,input_kind=input_kind,once=True))
            end=time.monotonic()+timeout
            while time.monotonic()<end:
                state=self.state();proof=self._api('evidence')
                feedback.message(proof['status']+': '+proof['reason'])
                if state.get('error'):raise RuntimeError(state['error'])
                result=state.get('latest',{}).get('custom',{})
                if result.get('captured_unix',0)>started and proof['status']in ('VERIFIED','HELD')and all(r['ok']is True for r in proof['rows']):
                    if result.get('fir_coefficient_sha256')!=spec['sha256']:raise RuntimeError('Another control changed the filter during verification')
                    return dict(filter=spec['id'],title=spec['title'],coefficient_sha256=spec['sha256'],
                        readback_verified=result.get('fir_coefficients_readback')==spec['coefficients'],
                        max_reference_error=result['max_reference_error'],clipped_samples=result['clips'],proof_status=proof['status'])
                time.sleep(.3)
            raise TimeoutError('No fresh matching FPGA filter result; inspect the CyberEther evidence panel')

    def show_gui(self,height=1050):
        """Embed the existing controls; output contains a private invite, like the launch cell."""
        from IPython.display import IFrame,display
        display(IFrame(self._base+'/#'+self._token,width='100%',height=height))
