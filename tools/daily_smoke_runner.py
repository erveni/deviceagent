"""Same daily dispatcher; add local-only screenshots after each terminal result."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import run_rolling_plan as runner
original=runner._run_session
artifacts=Path(os.environ['DAILY_SMOKE_ARTIFACTS'])

def observed(job,index,device,serial,spec,wave):
    if device!='device-104' or '149145555W002883' not in serial:
        raise RuntimeError('Smoke escaped selected device')
    row=original(job,index,device,serial,spec,wave)
    platform=job['platform']
    try:
        with (artifacts/(platform+'.png')).open('xb') as stream:
            shot=subprocess.run(['adb','-s',serial,'exec-out','screencap','-p'],stdout=stream,
                                stderr=subprocess.PIPE,timeout=15)
        screenshot_exit=shot.returncode
    except Exception as error:
        screenshot_exit=type(error).__name__ # Never lose a valid row over evidence capture.
    (artifacts/(platform+'.json')).write_text(json.dumps(dict(platform=platform,
        status=row['status'],duration_s=row['duration_s'],error=row.get('error'),
        daily_slot_id=job['daily_slot_id'],screenshot_exit=screenshot_exit),indent=2))
    return row

runner._run_session=observed
runner.main()
