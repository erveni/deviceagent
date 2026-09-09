"""Fail closed until the next ranking run has an explicitly verified cost profile.

Metered comparison harnesses opt out explicitly; normal/stale queue launchers do
not. This is a safety gate, not evidence that the rollout is already complete.
"""
import os
import sys


def check(env):
    active_bootstrap=(env.get('COST_COPILOT_BOOTSTRAP')=='1' and
                      env.get('COST_DRIVER')=='reframe_single' and env.get('MAX_JOBS')=='1')
    if env.get('RANK_COST_MEASUREMENT')=='1' or active_bootstrap:
        if env.get('RANK_RETRY_ROUNDS')!='0' or not env.get('GOST_COST_LEDGER'):
            raise ValueError('Measured ranking requires zero retry rounds and a cost ledger')
        try:
            jobs = int(env.get('MAX_JOBS', '0'))
        except ValueError:
            jobs = 0
        if not 1 <= jobs <= 20:
            raise ValueError('Measured ranking requires MAX_JOBS between 1 and 20')
        return
    raise ValueError('Ranking cost rollout is not released yet. Refusing the old expensive '
                     'path. Complete measured rollout/device readiness before resuming the queue.')


if __name__=='__main__':
    try:check(os.environ)
    except ValueError as error:
        print(str(error),file=sys.stderr);sys.exit(2)
