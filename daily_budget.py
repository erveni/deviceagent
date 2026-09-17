"""Account-meter admission guard shared across daily retry rounds.

Stops NEW jobs on budget/floor/read failure. Already-running jobs finish, so this
is not a hard billing cap; meter lag and in-flight traffic can overshoot it.
"""
import json
import math
import os
from pathlib import Path
import threading
import time
from tools.measure_evomi_targeting import balance


class DailyBudget:
    def __init__(self, *, env=os.environ, read=balance):
        self.limit=float(env['DAILY_BUDGET_MB']);self.floor=float(env['DAILY_BALANCE_FLOOR_MB'])
        if not all(map(math.isfinite,(self.limit,self.floor))) or self.limit<=0 or self.floor<0:
            raise ValueError('Invalid daily budget/floor')
        self.path=Path(env['DAILY_METER_LEDGER']);self.read=read
        self.deadline=float(env.get('DAILY_ADMISSION_DEADLINE_EPOCH','inf'))
        self.lock=threading.Lock();self.last_at=0;self.stopped=False;self.reason=''
        if env.get('PROXY_PROVIDER')!='evomi':raise ValueError('Daily meter guard requires Evomi')
        if self.path.exists():
            first=json.loads(self.path.read_text().splitlines()[0])
            if first['budget_mb']!=self.limit or first['floor_mb']!=self.floor:
                raise ValueError('Daily ledger budget mismatch')
            self.before=first['balance_mb']
        else:
            self.before=self._read_meter()
            with self.path.open('x') as stream:
                stream.write(json.dumps(dict(at=time.time(),phase='initial',balance_mb=self.before,
                    budget_mb=self.limit,floor_mb=self.floor))+'\n')

    def _read_meter(self):
        last_error = None
        for attempt in range(3):
            try:
                value = self.read()
                if not math.isfinite(value):
                    raise ValueError('Invalid meter balance')
                return value
            except Exception as error:
                last_error = error
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
        raise last_error

    def admit(self):
        with self.lock:
            if self.stopped:return False
            if time.time()>=self.deadline:
                self.stopped=True;self.reason='Daily admission deadline reached'
                print('DAILY SPEND GUARD: '+self.reason,flush=True);return False
            if time.monotonic()-self.last_at<20:return True
            try:
                value=self._read_meter()
                used=self.before-value
                with self.path.open('a') as stream:
                    stream.write(json.dumps(dict(at=time.time(),phase='admission',balance_mb=value,used_mb=used))+'\n')
                if used < -.01:raise ValueError('Balance increased; attribution changed')
                if used>=self.limit or value<=self.floor:raise ValueError('Daily budget or balance floor reached')
                self.last_at=time.monotonic()
                return True
            except Exception as error:
                self.stopped=True;self.reason=str(error)
                print('DAILY SPEND GUARD: no new jobs; '+self.reason,flush=True)
                return False
