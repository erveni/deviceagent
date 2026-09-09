"""Produce the priority deliverable automatically after rollback; no phone/network actions."""
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'ranking_yokl_20260909'


def main():
    report=RUN/'direct/report.json'
    started=time.monotonic()
    while not report.exists():
        if time.monotonic()-started > 3*3600:
            raise RuntimeError('YOKL wrapper did not finish within three hours; no export')
        time.sleep(30)
    result=json.loads(report.read_text())
    state={'wrapper_status':result.get('status'),'exported':False}
    try:
        done=subprocess.run([sys.executable,str(ROOT/'tools/export_yokl_0909.py')],
                            cwd=ROOT,capture_output=True,text=True,timeout=120)
        state['export_exit_code']=done.returncode
        state['exported']=done.returncode==0
        state['details']=done.stdout.strip() if done.returncode==0 else done.stderr[-2000:]
    finally:
        (RUN/'delivery_state.json').write_text(json.dumps(state,indent=2))
    print(json.dumps(state),flush=True)


if __name__=='__main__':main()
