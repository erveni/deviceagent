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
    if env.get('RANK_COST_ROLLOUT') == 'copilot-wifi-v1':
        required = ('RANK_COPILOT_OFFLINE_BOOTSTRAP','RANK_COPILOT_WIFI_SETTLE',
                    'RANK_COPILOT_WIFI_ROLLOUT')
        if any(env.get(name) != '1' for name in required):
            raise ValueError('Released ranking requires the settled Copilot Wi-Fi path')
        labels={value.strip() for value in env.get('RANK_COPILOT_WIFI_ROLLOUT_DEVICES','').split(',') if value.strip()}
        if not labels or 'device-125' in labels:
            raise ValueError('Released ranking requires a safe explicit rollout allow-list')
        if 'device-108' in labels and env.get('RANK_ALLOW_QUARANTINED_DEVICE_108') != '1':
            raise ValueError('device-108 requires an explicit quarantine override')
        platforms={value.strip().lower() for value in env.get('PLATFORMS','chatgpt,gemini,copilot').split(',') if value.strip()}
        if 'chatgpt' in platforms and env.get('RANK_CHATGPT_LOW_COST_RELEASED')!='1':
            raise ValueError('ChatGPT ranking is blocked until its low-cost path is released')
        if 'gemini' in platforms and env.get('RANK_GEMINI_LOW_COST_RELEASED')!='1':
            raise ValueError('Gemini ranking is blocked until its low-cost path is released')
        return
    raise ValueError('Ranking cost rollout is not released yet. Refusing the old expensive '
                     'path. Complete measured rollout/device readiness before resuming the queue.')


if __name__=='__main__':
    try:check(os.environ)
    except ValueError as error:
        print(str(error),file=sys.stderr);sys.exit(2)
